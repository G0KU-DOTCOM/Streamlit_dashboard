"""Read-only, bounded MongoDB access and plots for curated cross-border flows."""
from datetime import datetime, timezone
import json
import math
from pathlib import Path
from zoneinfo import ZoneInfo

from bson import BSON
from matplotlib.figure import Figure
import matplotlib.dates as mdates
import numpy as np
import pandas as pd
from pymongo import MongoClient
from pymongo.server_api import ServerApi
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
DATABASE = 'ind320_energy'
COLLECTION = 'hourly_flows'
MAX_DOCUMENTS = 8784  # A complete leap year for one connection.
MAX_BSON_BYTES = 2 * 1024**2
CACHE_SECONDS = 24 * 60 * 60
OSLO = ZoneInfo('Europe/Oslo')
FLOW_COLUMNS = ['import_mwh', 'export_mwh', 'import_coverage_minutes', 'export_coverage_minutes']
PROJECTION = {'_id': 0, 'connection': 1, 'time_utc': 1, **{name: 1 for name in FLOW_COLUMNS}}
COLORS = ['#1976b8', '#dc7835']


class FlowDataError(RuntimeError):
    """A safe message with no connection details or raw server response."""


def project_plan():
    return json.loads((ROOT/'entsoe_plan.json').read_text())


def year_window(connection, year):
    """Intersect Norwegian calendar-year boundaries with the frozen snapshot."""
    plan = project_plan()
    if connection not in [item['connection'] for item in plan['connections']]:
        raise FlowDataError('Unknown connection.')
    start = datetime.fromisoformat(plan['period']['start_inclusive'])
    end = datetime.fromisoformat(plan['period']['end_exclusive'])
    if isinstance(year, bool) or not isinstance(year, int) or not start.year <= year <= end.year:
        raise FlowDataError('Year outside the project snapshot.')
    calendar_start = datetime(year, 1, 1, tzinfo=OSLO)
    calendar_end = datetime(year + 1, 1, 1, tzinfo=OSLO)
    lower, upper = max(start, calendar_start), min(end, calendar_end)
    if lower >= upper:
        raise FlowDataError('No snapshot data in this year.')
    return lower.astimezone(timezone.utc), upper.astimezone(timezone.utc), (
        lower == calendar_start and upper == calendar_end)


def prepare_flows(documents, connection, year):
    """Validate source records and keep missing/incomplete hours distinct from zero."""
    start, end, full_year = year_window(connection, year)
    expected = pd.date_range(start, end, freq='h', inclusive='left', name='time_utc')
    rows = []
    seen = set()
    size = 0
    for document in documents:
        size += len(BSON.encode(document))
        if len(rows) >= MAX_DOCUMENTS or size > MAX_BSON_BYTES:
            raise FlowDataError('The MongoDB result exceeded the read budget.')
        stamp = document.get('time_utc')
        if isinstance(stamp, datetime) and stamp.tzinfo is not None:
            stamp = stamp.astimezone(timezone.utc)
        if (document.get('connection') != connection or not isinstance(stamp, datetime)
                or stamp.tzinfo is None or not start <= stamp < end
                or stamp.minute or stamp.second or stamp.microsecond or stamp in seen):
            raise FlowDataError('The MongoDB result has invalid or duplicate hours.')
        seen.add(stamp)
        row = {'time_utc': stamp}
        for direction in ('import', 'export'):
            energy = document.get(f'{direction}_mwh')
            coverage = document.get(f'{direction}_coverage_minutes')
            if (isinstance(coverage, bool) or not isinstance(coverage, (int, float))
                    or not math.isfinite(coverage) or not 0 <= coverage <= 60):
                raise FlowDataError('The MongoDB result has invalid coverage.')
            if energy is not None and (isinstance(energy, bool)
                    or not isinstance(energy, (int, float)) or not math.isfinite(energy) or energy < 0):
                raise FlowDataError('The MongoDB result has invalid energy.')
            # A partially covered hour cannot be shown as a full-hour mean MW.
            row[f'{direction}_mwh'] = energy if coverage == 60 else None
            row[f'{direction}_coverage_minutes'] = coverage
        rows.append(row)
    frame = pd.DataFrame(rows, columns=['time_utc'] + FLOW_COLUMNS).set_index('time_utc')
    frame.index = pd.to_datetime(frame.index, utc=True)
    frame = frame.reindex(expected)
    for column in FLOW_COLUMNS:
        frame[column] = pd.to_numeric(frame[column], errors='raise').astype(float)
    frame.attrs.update(
        documents=len(rows), bson_bytes=size, full_year=full_year,
        start=start.isoformat(), end_exclusive=end.isoformat(),
        fetched_at=datetime.now(timezone.utc).isoformat(timespec='seconds'),
    )
    return frame


def read_year(collection, connection, year):
    """One indexed, projected query; no inserts, index creation or full scans."""
    start, end, _ = year_window(connection, year)
    cursor = None
    try:
        cursor = (collection.find(
            {'connection': connection, 'time_utc': {'$gte': start, '$lt': end}},
            PROJECTION, max_time_ms=10000,
        ).hint([('connection', 1), ('time_utc', 1)])
          .sort('time_utc', 1).limit(MAX_DOCUMENTS + 1).batch_size(200))
        return prepare_flows(cursor, connection, year)
    except FlowDataError:
        raise
    except Exception:
        raise FlowDataError('MongoDB could not be read. Check the connection and prepared data.') from None
    finally:
        if cursor is not None:
            try:
                cursor.close()
            except Exception:
                raise FlowDataError('MongoDB cursor cleanup failed; connection details hidden.') from None


@st.cache_resource(max_entries=1, show_spinner=False)
def mongo_client():
    # A shared PyMongo client is thread-safe. The small pool is per server;
    # the driver's monitoring connections are separate from this pool.
    try:
        return MongoClient(
            st.secrets['mongo']['uri'], server_api=ServerApi('1'),
            maxPoolSize=2, maxConnecting=1, waitQueueTimeoutMS=5000,
            serverSelectionTimeoutMS=10000, connectTimeoutMS=10000,
            socketTimeoutMS=15000, retryReads=False, retryWrites=False,
            tz_aware=True, tzinfo=timezone.utc,
        )
    except Exception:
        raise FlowDataError('MongoDB is not configured. Add [mongo] uri in Streamlit Secrets.') from None


@st.cache_data(ttl=CACHE_SECONDS, max_entries=27, show_spinner='Reading selected MongoDB data…')
def load_flows(connection, year):
    # 9 connections × 3 years. Month changes never call MongoDB again.
    # Cache safe failures too, so reruns cannot repeatedly hammer a failed service.
    try:
        year_window(connection, year)
        frame = read_year(mongo_client()[DATABASE][COLLECTION], connection, year)
        return {'frame': frame, 'error': None}
    except FlowDataError as exc:
        return {'frame': None, 'error': str(exc)}


def complete_hours(frame):
    return (frame[['import_coverage_minutes', 'export_coverage_minutes']].eq(60).all(axis=1)
            & frame[['import_mwh', 'export_mwh']].notna().all(axis=1))


def period_totals(frame):
    # Never turn the small pilot or a missing direction into an annual total.
    if frame.empty or not complete_hours(frame).all():
        return None
    return frame[['import_mwh', 'export_mwh']].sum()


def month_options(frame):
    return sorted(set(frame.index.tz_convert(OSLO).month))


def month_lines(frame, months):
    """Preserve the hourly UTC axis and NaN gaps between non-adjacent months."""
    lines = frame[['import_mwh', 'export_mwh']].copy()
    chosen = lines.index.tz_convert(OSLO).month.isin(months)
    lines.loc[~chosen, :] = np.nan
    if not chosen.any():
        return lines.iloc[:0]
    positions = np.flatnonzero(chosen)
    return lines.iloc[positions[0]:positions[-1] + 1]


def pie_figure(totals):
    figure = Figure(figsize=(5, 4), layout='constrained')
    axis = figure.subplots()
    axis.pie(totals, labels=['Import to Norway', 'Export from Norway'],
             autopct='%1.1f%%', pctdistance=.65, colors=COLORS, startangle=90)
    axis.set_aspect('equal')
    return figure


def line_figure(frame, months):
    lines = month_lines(frame, months)
    figure = Figure(figsize=(7, 4), layout='constrained')
    axis = figure.subplots()
    for column, label, color in zip(['import_mwh', 'export_mwh'], ['Import to Norway', 'Export from Norway'], COLORS):
        # A complete one-hour MWh value divided by one hour is mean MW.
        axis.plot(lines.index.to_pydatetime(), lines[column], label=label, color=color, linewidth=.8)
    locator = mdates.AutoDateLocator(tz=OSLO, minticks=3, maxticks=7)
    axis.xaxis.set_major_locator(locator)
    axis.xaxis.set_major_formatter(mdates.ConciseDateFormatter(locator, tz=OSLO))
    if len(lines):
        # Keep missing trailing hours visible instead of zooming to the pilot.
        axis.set_xlim(lines.index[0], lines.index[-1] + pd.Timedelta(hours=1))
    axis.set_xlabel('Date and time (Europe/Oslo)')
    axis.set_ylabel('Hourly mean power (MW)')
    axis.legend(loc='upper right')
    axis.grid(alpha=.2)
    return figure

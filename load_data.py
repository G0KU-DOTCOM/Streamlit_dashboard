"""Shared, bounded NVE API reads for the Streamlit pages."""

import json
from datetime import datetime, timezone

import pandas as pd
import requests
import streamlit as st

API_BASE = "https://biapi.nve.no/magasinstatistikk/api/Magasinstatistikk/"
MAX_HISTORY_BYTES = 8 * 1024 * 1024
MAX_AREA_BYTES = 128 * 1024
CACHE_SECONDS = 24 * 60 * 60
ENGLISH_NAMES = {
    "dato_Id": "observation_date",
    "omrType": "area_type",
    "omrnr": "area_number",
    "iso_aar": "iso_year",
    "iso_uke": "iso_week",
    "fyllingsgrad": "filling_fraction",
    "kapasitet_TWh": "capacity_twh",
    "fylling_TWh": "stored_energy_twh",
    "neste_Publiseringsdato": "next_publication_date",
    "fyllingsgrad_forrige_uke": "previous_week_filling_fraction",
    "endring_fyllingsgrad": "weekly_filling_change",
}


class NVEDataError(Exception):
    """A download or data-format problem that can be shown without a traceback."""


def fetch_json(endpoint, max_bytes):
    # Like D2D's REST notebook, I use requests.get and decode the JSON response.
    # Streaming also lets me stop an oversized response before loading it all.
    # iter_content counts decoded bytes, including when HTTP compression is used.
    body = bytearray()
    try:
        with requests.get(
            API_BASE + endpoint, stream=True, timeout=(10, 45)
        ) as response:
            response.raise_for_status()
            for chunk in response.iter_content(chunk_size=8192):
                if len(body) + len(chunk) > max_bytes:
                    raise NVEDataError("The NVE response exceeded the download size limit.")
                body.extend(chunk)
        return json.loads(body), len(body)
    except (requests.RequestException, ValueError, UnicodeError) as exc:
        raise NVEDataError("NVE data could not be downloaded or decoded. Try again later.") from exc


def prepare_history(records):
    # I preserve the eleven Part 1 columns and the meaning of the year-1 sentinel.
    if not isinstance(records, list) or not records:
        raise NVEDataError("NVE returned an empty or unexpected history response.")
    try:
        reservoirs = pd.DataFrame(records)
        reservoirs = reservoirs[list(ENGLISH_NAMES)].rename(columns=ENGLISH_NAMES)
        reservoirs["observation_date"] = pd.to_datetime(
            reservoirs["observation_date"], errors="raise"
        )
        reservoirs["next_publication_date"] = pd.to_datetime(
            reservoirs["next_publication_date"].replace("0001-01-01T00:00:00", None),
            errors="raise",
        )
        numeric_columns = set(ENGLISH_NAMES.values()) - {
            "observation_date", "next_publication_date", "area_type"
        }
        for column in numeric_columns:
            reservoirs[column] = pd.to_numeric(reservoirs[column], errors="raise")
        required = reservoirs.drop(columns="next_publication_date")
        if required.isna().any().any():
            raise ValueError("Missing observation fields")
        if not reservoirs["area_type"].isin(["EL", "NO", "VASS"]).all():
            raise ValueError("Unexpected area type")
        if not reservoirs["area_type"].eq("NO").any():
            raise ValueError("No national observations")
        if reservoirs.duplicated(["observation_date", "area_type", "area_number"]).any():
            raise ValueError("Duplicate observations")
        # Values above 100% are retained, as in the notebook investigation.
        return reservoirs.sort_values(
            ["observation_date", "area_type", "area_number"]
        ).reset_index(drop=True)
    except (KeyError, ValueError, TypeError) as exc:
        raise NVEDataError("NVE history does not match the expected data format.") from exc


@st.cache_data(ttl=CACHE_SECONDS, max_entries=1, show_spinner="Loading NVE reservoir history…")
def load_data():
    # D2D's cache_data pattern shares one download between pages and users.
    # Selection widgets are deliberately not arguments: they filter locally.
    records, byte_count = fetch_json("HentOffentligData", MAX_HISTORY_BYTES)
    reservoirs = prepare_history(records)
    reservoirs.attrs["download_bytes"] = byte_count
    reservoirs.attrs["fetched_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    return reservoirs


@st.cache_data(ttl=7 * CACHE_SECONDS, max_entries=1, show_spinner=False)
def load_areas():
    records, _ = fetch_json("HentOmråder", MAX_AREA_BYTES)
    try:
        areas = pd.DataFrame([
            area for group in records
            for key in ("land", "elspot", "vassdrag") for area in group[key]
        ])
        return areas[["omrType", "omrnr", "navn", "beskrivelse"]].rename(columns={
            "omrType": "area_type", "omrnr": "area_number",
            "navn": "name", "beskrivelse": "description",
        })
    except (KeyError, TypeError, ValueError) as exc:
        raise NVEDataError("NVE area descriptions are temporarily unavailable.") from exc


def load_data_or_stop():
    # Each page gives a short message if NVE is unavailable, rather than a crash.
    try:
        return load_data()
    except NVEDataError as exc:
        st.error(str(exc))
        st.stop()

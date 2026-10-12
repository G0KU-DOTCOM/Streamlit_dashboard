from calendar import month_name
from datetime import datetime

import streamlit as st

from dashboard.transfers import (
    OSLO, complete_hours, line_figure, load_flows, month_lines,
    month_options, period_totals, pie_figure, project_plan,
)

st.set_page_config(page_title='Cross-border transfers', layout='wide')
st.title('Cross-border electricity transfers')
st.write('Compare electricity imported to and exported from Norway on one international connection.')
plan = project_plan()
connections = [item['connection'] for item in plan['connections']]
years = list(range(datetime.fromisoformat(plan['period']['start_inclusive']).year,
                   datetime.fromisoformat(plan['period']['end_exclusive']).year + 1))
left, right = st.columns(2)
with left:
    connection = st.radio('Connection', connections, index=connections.index('NO2-DK1'))
    year = st.selectbox('Year', years, index=years.index(2025))
    result = load_flows(connection, year)
    if result['error']:
        st.error(result['error'])
        st.caption('This result is cached. After fixing configuration or completing an upload, restart the app to refresh it.')
    else:
        frame = result['frame']
        full_year = frame.attrs['full_year']
        st.subheader(f'{connection} · {year}' + ('' if full_year else ' · partial year'))
        first = frame.index[0].tz_convert(OSLO)
        last = frame.index[-1].tz_convert(OSLO)
        st.caption(f'Snapshot interval: {first:%d %b %Y}–{last:%d %b %Y}.')
        totals = period_totals(frame)
        valid = int(complete_hours(frame).sum())
        if totals is None:
            st.warning(
                f'Incomplete data: {valid:,} of {len(frame):,} expected hours have both directions. '
                'The energy pie is withheld until this period is fully available.'
            )
        elif totals.sum() == 0:
            st.info('Both directions report zero energy. Percentage shares are undefined.')
        else:
            st.pyplot(pie_figure(totals), clear_figure=True)
            st.write(f'Import: **{totals.import_mwh:,.0f} MWh** · Export: **{totals.export_mwh:,.0f} MWh**')
            st.caption('Shares of total energy in both directions. Month choices affect only the line plot.')
with right:
    st.subheader('Monthly flow')
    if result['error']:
        st.info('The flow plot is available when MongoDB data can be read.')
    else:
        options = month_options(frame)
        months = st.pills('Months', options, format_func=lambda month: month_name[month],
                          selection_mode='multi', default=[options[0]], key=f'flow_months_{year}')
        if not months:
            st.info('Select one or more months to display.')
        else:
            selected = month_lines(frame, months)
            local_months = frame.index.tz_convert(OSLO).month
            expected = frame.loc[local_months.isin(months)]
            valid = int(complete_hours(expected).sum())
            st.caption(f'{connection} · {year} · {valid:,}/{len(expected):,} complete hours in selected months.')
            if valid < len(expected):
                st.warning('Some hours are missing or incomplete. Available values are shown; gaps are not zeros.')
            if selected.notna().any().any():
                st.pyplot(line_figure(frame, months), clear_figure=True)
                st.caption('Hourly averages smooth short peaks. Gaps separate excluded months and missing measurements.')
            else:
                st.info('No complete hourly measurements are available for these months yet.')

with st.expander('Data source, coverage and caching'):
    st.markdown(
        'Source: [ENTSO-E Transparency Platform](https://transparency.entsoe.eu/), '
        'physical cross-border flows (A11). The notebook stores native intervals in '
        'Cassandra through Spark, then prepares hourly energy for MongoDB. '
        'This page reads those curated MongoDB documents directly.'
    )
    st.write(
        'The frozen snapshot covers 11 October 2024–10 October 2026 in Norwegian time. '
        'Only 2025 is a full calendar year. The nine listed bidding-zone borders '
        'exclude internal Norwegian transfers; the historical Russia-border scope '
        'remains a documented limitation. These are flows, not electricity generation.'
    )
    st.write(
        'One connection and year are read at a time, using an index and only the '
        'fields needed here. The read stops above 8,784 documents or 2 MiB of decoded BSON. '
        'Results are cached for 24 hours, with at most 27 entries shared by app users. '
        'Month selection reuses the cached year. This page makes no database writes.'
    )
    st.caption('Cached empty results or errors also persist until expiry or app restart. After the initial upload, restart the app to refresh them.')
    if not result['error']:
        st.caption(f"Read at (UTC): {frame.attrs['fetched_at']} · {frame.attrs['documents']:,} documents · {frame.attrs['bson_bytes']/1024:.1f} KiB decoded BSON.")

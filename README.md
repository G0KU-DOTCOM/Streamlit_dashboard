# Norwegian Reservoir Dashboard

IND320 project: NVE reservoir statistics, ENTSO-E electricity transfers through
Spark/Cassandra and MongoDB, Open-Meteo ERA5 weather analysis, Norges Bank
exchange rates and weekly River SNARIMAX forecasts.

## Run the app

Use Python 3.12. From a fresh clone, create the local environment and install
the dependencies before starting the app:

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m streamlit run main.py
```

All Python dependencies are in `requirements.txt`. The local Spark notebook
sections also need Java 17 and a running Cassandra container. The Streamlit
app does not need these services running.

Local credentials belong in the Git-ignored `.streamlit/secrets.toml`:
`[mongo] uri` for MongoDB and `[entsoe] token` for ENTSO-E downloads. Configure
the app's MongoDB credentials in Streamlit Cloud Secrets when hosting it.

## App pages

- **Home:** blue map and area selector, observed filling and routes to the main
  tasks. Map clicks and selectors store the same region. The map observation
  week is also the final forecast training week; horizon is shared as well.
- **Explore → Reservoirs:** measurement curves, area summaries with weekly
  sparklines and detailed observations, combining the previous data pages.
- **Explore → Transfers:** bounded MongoDB reads with interactive import/export
  charts and local connection, year and month controls.
- **Analyse → Analyses:** reservoir STL/spectrogram, weather SPC/LOF with
  temperature or precipitation, and lagged sliding-window weather correlation.
- **Predict → Forecast:** recursive River SNARIMAX, editable model orders,
  training length and horizon, optional historical weather scenarios, forecast
  animation and error comparisons when later observations exist.
- **Project → Sources & about:** source definitions, limitations, time alignment
  and a cached EUR/NOK and USD/NOK downloader.

The layout follows the blue sketch in the Part 4 notebook. Native Streamlit
navigation preserves page links and keyboard controls. Previous Data Plot,
Weather Analysis and Reservoir API URLs remain registered as hidden routes.
Charts use Plotly, including the forecast animation. The clickable GeoJSON
map uses Folium through `streamlit-folium`. The notebook's Matplotlib reference
calculations are retained; the app adapts their analysis results to Plotly.

## Data and limitations

**Reservoirs:** NVE history is cached for 24 hours and area descriptions for
7 days. Responses are limited to 8 MiB and 128 KiB respectively. Period choices
filter the downloaded history locally. NVE's inspected API schema documents
no date-range parameters. Upstream interval filtering remains a documented
Part 2 limitation; the app filters the cached response locally. Missing weeks
stay missing.

**Weather:** `data/geography/` contains the Atlas shapefiles and
`weather_locations.csv`, with 1000 sampled locations per region. Electricity
areas are NO1–NO5. The assignment's other groups are East (RS+RØ), West (RV)
and North (RM+RN); these group NVE administrative regions, not detailed
hydrological catchments. No national or separate VASS4 weather sample exists.

Part 3 used temperature for DCT/SPC following the teacher's clarification.
Part 4 makes temperature and precipitation selectable for both SPC and LOF;
temperature remains the default. Flagged observations are statistically
unusual under the selected method, rather than necessarily data errors.

`data/weather/NO3_era5_2024-01-01_2024-12-31_hourly.csv.gz` contains 8784 UTC
hours of ERA5 means across the 1000 NO3 locations. Temperature is in °C;
precipitation is the preceding hour's amount in mm. `point_count` records
coverage. This small summary lets the app reuse the notebook's download.
Other area/year combinations start downloading only after a button press.
Raw point data and resumable batches remain under ignored `no_sync/weather/`.
The Part 4 notebook also uses `data/weather/NO3_era5_2023-2025_hourly_sample100.csv.gz`
for correlation and forecast experiments. It covers the same 100 NO3 locations
in all three years. The notebook compares this sample with the 1,000-point
summary in 2024.
Forecast scenarios use only previous-week weather covered by the selected
training period. Missing weather stops that scenario with a useful message;
the app never substitutes actual future weather or downloads it automatically.
Weather attribution: Open-Meteo / ERA5,
[CC BY 4.0](https://open-meteo.com/en/licence). Boundaries: [NVE Atlas](https://atlas.nve.no).

**Transfers:** the frozen snapshot covers nine international bidding-zone
borders in both directions, 11 October 2024–10 October 2026. Only 2025 is a
complete calendar year. Historical Russia-border coverage is not established.
Hourly energy accounts for interval duration; missing data are not zero.
Hourly averages can smooth short peaks.

The transfer page reads MongoDB directly using the `(connection, time_utc)`
index. One connection/year is limited to 8784 documents and 2 MiB decoded
BSON, cached for 24 hours; month changes reuse it. The page makes no database
writes. Restarting the app clears its in-memory caches.

**Forecasts:** Home starts with NO3, the evaluated example. The forecast starts
with 104 training weeks, a 12-week horizon and filling history alone, using
`p=1, d=1, q=1, m=52, sp=1, sd=0, sq=0`. These orders were selected across
four 2025 development cutoffs; the 2026 checks showed seasonal variation.
Historical evaluation displays MAE and RMSE in percentage points and a
last-value reference when later observations exist. This does not establish
equal accuracy for other areas or periods.

The shared map date is the final training observation date. A date between
observations uses the latest available observation on or before it. The
reservoir overview period and weather year remain separate controls. Exact
first-availability and revision histories are not retained, so the historical
checks use observation-based cutoffs. The notebook documents time zones,
publication delays and the approved historical-week-means weather scenario.

**Exchange rates:** EUR/NOK and USD/NOK spot quotes are requested together for
an inclusive calendar-date interval. The app caches successful reads for
24 hours. Dates without published quotes remain absent; rates are not used
as inputs to the current forecast interface.

## Notebooks and local pipeline

- [Part 1](notebooks/prosjekt_part1.ipynb): original reservoir CSV analysis.
  Its data can be found in the linked [Git snapshot](https://github.com/G0KU-DOTCOM/Streamlit_dashboard/tree/95a35b71c25d5e4c94405deea7462689a0b864c1).
- [Part 2](notebooks/prosjekt_part2.ipynb): APIs, Spark/Cassandra, hourly
  curation, MongoDB and the transfer page.
- [Part 3](notebooks/prosjekt_part3.ipynb): sampled regions, ERA5 downloads,
  SPC/LOF, STL and spectrogram analyses with function tests.
- [Part 4](notebooks/prosjekt_part4.ipynb): exchange rates, time alignment,
  weekly correlation, chronological SNARIMAX comparisons and the design sketch.

The app loads price-area, national and VASS overview GeoJSON converted from
the saved NVE shapefiles. Run `python -m pipeline.export_water_areas` to rebuild
the VASS layer using Part 3's grouping: East = RS + RØ, West = RV, and
Mid/North = RM + RN. These are grouped NVE administrative overview outlines,
not detailed hydrological catchments. The published NVE history contains
VASS1–VASS3; VASS4 appears in metadata but has no observations or separate
map outline.

Map clicks highlight and retain the selected area. Colours can show selection,
weekly filling, weekly mean temperature or weekly precipitation. Weather uses
complete Oslo calendar weeks and the largest complete saved location sample
for each area and week; samples are never blended within a week. Grey means
missing data. An explicit button prepares missing weather for the selected
area and week using its 1000 saved locations, with progress feedback and
reusable summaries. No national or separate VASS4 weather sample is defined.

Shared app and analysis functions are in `dashboard/`; local collection and
database tools are in `pipeline/`. `entsoe_plan.json` defines the frozen
period, connections and existing limits. Run tools from the project root:

| Command after `.venv/bin/python -m` | Purpose |
| --- | --- |
| `pipeline.entsoe_probes` | Check cached one-day samples; `--download` permits missing requests. |
| `pipeline.entsoe_bulk` | Read saved progress; `--execute` permits collection and Cassandra writes. |
| `pipeline.entsoe_hourly` | Read Cassandra and regenerate the curated local BSON file. |
| `pipeline.entsoe_mongo --mode audit` | Read current MongoDB storage usage. |
| `pipeline.entsoe_mongo --mode upload` | Reproduce/resume the guarded upload from verified local BSON. |
| `pipeline.upload_status` | Read saved upload status without contacting MongoDB. |

The full upload was verified on 13 October 2026: **479,845 native intervals**
and **157,680 curated documents**, using **37.09 MiB including indexes**.
These are historical measurements. Existing upload limits remain 160,000
documents, 64 MiB project data plus indexes, 256 MiB across user databases and
40 document writes/second. Fresh storage checks and read-back verification
are part of the uploader. Preserve the `no_sync/` caches, progress and download
ledger when resuming; deleting them discards data or cumulative accounting.

`reports/` holds four public summaries of completed checks from 13 October.
They are historical evidence, not app data or a current database audit. The
Part 2 notebook still reads operational reports from `no_sync/`, so those
cells need the local workflow's saved files. The public summaries alone do
not make the full database notebook reproducible after cloning.

## Checks and submission

```bash
.venv/bin/python -m unittest discover -s tests -q
```

The ordinary tests use fixtures and make no live API/database requests.
Set `RUN_SPARK_TESTS=1` to include the optional local Spark math checks.

All four notebooks contain work logs. Part 4 includes a log within the required
300–500-word range covering the notebook experiments, Streamlit implementation
and correlation findings. Its AI-use statement describes Codex's role in code,
analysis and writing, and the work log explicitly identifies its AI drafting.
The completed Part 4 screencast is linked under **Video** at the top of its
notebook and is available [on Panopto](https://nmbu.cloud.panopto.eu/Panopto/Pages/Viewer.aspx?id=0d78306a-ab11-4531-969d-b50d00ccca8b).
The saved code cells in all four notebooks have executed outputs without
error outputs; this does not mean every notebook can run from a fresh clone
without the local data and services described above.

Part 4 includes the blue app layout, interactive charts, correlation view,
forecast interface, exchange-rate reader, VASS overview map and weather-based
map colouring. Local changes reach the hosted app after being pushed to main.
The [Part 4 HTML export](notebooks/prosjekt_part4.html) includes the saved
outputs, embedded plots and sketches, work log and screencast link. Regenerate
the export whenever the notebook changes.

## Links

- [GitHub repository](https://github.com/G0KU-DOTCOM/Streamlit_dashboard)
- [Streamlit app](https://ind320dashboard.streamlit.app)
- [NVE API](https://biapi.nve.no/magasinstatistikk/swagger/index.html)
- [Open-Meteo Historical Weather API](https://open-meteo.com/en/docs/historical-weather-api)
- [IND320 Streamlit notebook](https://github.com/khliland/IND320/blob/main/D2Dbook/1_Deployment1/1_Dashboards/4_Streamlit.ipynb)
- [IND320 REST notebook](https://github.com/khliland/IND320/blob/main/D2Dbook/2_Data_sources/3_APIs/2_REST.ipynb)

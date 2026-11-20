# Norwegian Reservoir Dashboard

IND320 project: reservoir statistics from NVE, electricity transfers from
ENTSO-E through Spark/Cassandra and MongoDB, and ERA5 weather analysis.

## Run the app

Use Python 3.12. From the project folder:

```bash
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

## Data and limitations

**Reservoirs:** NVE history is cached for 24 hours and area descriptions for
7 days. Responses are limited to 8 MiB and 128 KiB respectively. Period choices
filter the downloaded history locally. NVE's inspected API schema documents
no date-range parameters; upstream interval filtering from the Part 2 task
remains unimplemented. The user chose to retain this documented fallback;
instructor acceptance has not been established. Missing weeks stay missing.

**Weather:** `data/geography/` contains the Atlas shapefiles and
`weather_locations.csv`, with 1000 sampled locations per region. Electricity
areas are NO1–NO5. The assignment's other groups are East (RS+RØ), West (RV)
and North (RM+RN); these group NVE administrative regions, not detailed
hydrological catchments. No national or separate VASS4 weather sample exists.

The teacher clarified that the DCT/SPC analysis should use temperature,
despite the original assignment text mentioning precipitation. Both SPC and
LOF therefore analyse temperature. Temperature and precipitation are still
downloaded as required by the data-collection task.

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

## Notebooks and local pipeline

- [Part 1](notebooks/prosjekt_part1.ipynb): original reservoir CSV analysis.
  Its data can be found in the linked [Git snapshot](https://github.com/G0KU-DOTCOM/Streamlit_dashboard/tree/95a35b71c25d5e4c94405deea7462689a0b864c1).
- [Part 2](notebooks/prosjekt_part2.ipynb): APIs, Spark/Cassandra, hourly
  curation, MongoDB and the transfer page.
- [Part 3](notebooks/prosjekt_part3.ipynb): sampled regions, ERA5 downloads,
  SPC/LOF, STL and spectrogram analyses with function tests.
- [Part 4](notebooks/prosjekt_part4.ipynb): exchange rates, time alignment,
  weekly correlation, chronological SNARIMAX comparisons and the design sketch.

The app loads precomputed price-area and national GeoJSON converted from the
saved NVE shapefiles. Water-area geometry remains unavailable until its
equivalence to Magasinstatistikk's regions is verified; VASS data remain
selectable without drawing an unverified outline. Map weather colouring is
still outstanding. The map currently offers selection and weekly filling.

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

The Part 3 work log and screencast are complete, and the video link is in the
notebook. All notebook cells have been run, and the hosted app has been checked.
The remaining submission step is to export the notebook via HTML to PDF and
check that plots, tables and links are readable.

## Links

- [GitHub repository](https://github.com/G0KU-DOTCOM/Streamlit_dashboard)
- [Streamlit app](https://ind320dashboard.streamlit.app)
- [NVE API](https://biapi.nve.no/magasinstatistikk/swagger/index.html)
- [Open-Meteo Historical Weather API](https://open-meteo.com/en/docs/historical-weather-api)
- [IND320 Streamlit notebook](https://github.com/khliland/IND320/blob/main/D2Dbook/1_Deployment1/1_Dashboards/4_Streamlit.ipynb)
- [IND320 REST notebook](https://github.com/khliland/IND320/blob/main/D2Dbook/2_Data_sources/3_APIs/2_REST.ipynb)

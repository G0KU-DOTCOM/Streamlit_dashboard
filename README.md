# Norwegian Reservoir Dashboard

IND320 project using NVE's reservoir-statistics API in a Jupyter Notebook and
Streamlit app. The app downloads reservoir history directly from NVE; it no
longer requires a CSV file.

## Project contents

- `notebooks/prosjekt_part1.ipynb`: archived Part 1 analysis and outputs. To rerun
  the original CSV analysis, use the [Part 1 repository snapshot](https://github.com/G0KU-DOTCOM/Streamlit_dashboard/tree/95a35b71c25d5e4c94405deea7462689a0b864c1).
- `notebooks/prosjekt_part2.ipynb`: connection checks, NVE API inspection,
  thirteen recreated Part 1 figures, and documentation of the API app.
- `load_data.py`: shared API downloads, validation and Streamlit caching.
- `main.py` and `pages/`: home, table, general plots, Reservoir API and About.

## Run the Streamlit app locally

Use the project's Python 3.12 environment, install `requirements.txt`, then run
from the project folder:

```bash
.venv/bin/python -m streamlit run main.py
```

The reservoir pages need internet access to NVE, but no Docker or database
credentials. The Reservoir API page has a month-range slider and EL/NO/VASS
radio buttons, with a separate filling-fraction curve for each area number.

NVE's history endpoint has no date-range parameters: the slider filters locally
after downloading. History is shared across pages and users in a 24-hour memory
cache; area metadata is cached for 7 days. App restarts clear the caches.
Downloaded JSON is capped at 8 MiB for history and 128 KiB for area metadata.
No reservoir data is written to MongoDB or Cassandra by the app.

## Part 2 notebook progress

Use the Python 3.12 `.venv` kernel. The Spark–Cassandra test additionally needs
Java 17, PySpark 3.5.1, cassandra-driver and the running local Cassandra container.
The MongoDB test uses pymongo and `[mongo] uri` from the Git-ignored local
`.streamlit/secrets.toml`. Never commit credentials. Cloud credentials belong
in Streamlit's Secrets settings.

Section 4 runs independently of Docker and database credentials. It caps the
API history at 8 MiB and keeps a snapshot in Git-ignored `no_sync/nve_cache/`.
Leave `REFRESH_NVE_HISTORY = False` to reuse it. The comparison period is
8 January 1995–6 September 2026. Section 5 documents the Streamlit changes and
the adaptation needed for NVE's date-range limitation.

Remaining work includes ENTSO-E cross-border data, Spark/Cassandra ingestion and
extraction, curated MongoDB data, the transfer page, final log and screencast.
Local changes must be published to GitHub before they appear in the hosted app.

## Offline loader checks

```bash
.venv/bin/python -m unittest discover -s tests -v
```

## References and links

- [IND320 Streamlit notebook](https://github.com/khliland/IND320/blob/main/D2Dbook/1_Deployment1/1_Dashboards/4_Streamlit.ipynb)
- [IND320 REST notebook](https://github.com/khliland/IND320/blob/main/D2Dbook/2_Data_sources/3_APIs/2_REST.ipynb)
- [NVE API](https://biapi.nve.no/magasinstatistikk/swagger/index.html)
- [GitHub repository](https://github.com/G0KU-DOTCOM/Streamlit_dashboard)
- [Streamlit application](https://ind320dashboard.streamlit.app)

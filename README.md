# Norwegian Reservoir Dashboard

IND320 project: NVE reservoir exploration in Streamlit and an ENTSO-E
API → Spark/Cassandra → curated MongoDB workflow developed in Jupyter.

## Start the app

From this folder, with the project's Python 3.12 environment:

```bash
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m streamlit run main.py
```

- **Data Table:** choose a month range and EL/NO/VASS; inspect each area's five
  measurement trends and the original observations.
- **Data Plot:** the same period/area selection is retained between pages.
  Compare areas for a measurement, or view all measurements on separate axes.
- **Reservoir API:** source, area definitions and download/caching information.
- **About:** reserved for the project presentation.
- **Cross Border Transfers:** MongoDB import/export data, connection/year choice,
  an energy pie and multiple-month line plots. Missing hours are clearly flagged.

NVE history is cached for 24 hours (8 MiB maximum response); area metadata for
7 days (128 KiB maximum). The period selection filters **after downloading**:
NVE's documented API has no date-range parameters. The clarified assignment's
server-side interval requirement is not implemented. The user has chosen to
retain and document the cached local-filtering approach. These pages need internet
access, but no Docker or database credentials, and make no database writes.

## Repository map

| Location | Purpose |
| --- | --- |
| `main.py`, `pages/` | Streamlit entry point and pages |
| `dashboard/` | Shared NVE loader, selections, tables and plot helpers |
| `pipeline/` | ENTSO-E parsing, budgets, collection, curation and guarded upload |
| `entsoe_plan.json` | Frozen period, connections and enforced storage/download limits |
| `notebooks/` | Part 1 archive and Part 2 analysis with saved outputs |
| `tests/` | Offline correctness, capacity and app-navigation checks |
| `docs/` | Requirements review, progress and cleanup decisions |
| `requirements.txt` | Hosted Streamlit dependencies |
| `requirements-notebook.txt` | Additional local notebook/pipeline dependencies |
| `no_sync/` | Ignored local cache, reports, progress ledgers and curated BSON |
| `.streamlit/secrets.toml` | Ignored local credentials; never commit this file |

## Local notebook and pipeline

Use Python 3.12 and Java 17. Install local dependencies with
`.venv/bin/python -m pip install -r requirements-notebook.txt`.
Spark uses PySpark 3.5.1 and the matching Cassandra connector. Start the local
Cassandra container for Spark/Cassandra notebook sections. Local credentials
use `[mongo] uri` and `[entsoe] token` in `.streamlit/secrets.toml`; hosted app
credentials belong in Streamlit Cloud Secrets.

The modules now run with `-m` from the project root. This command **only reads
saved progress**:

```bash
.venv/bin/python -m pipeline.entsoe_bulk
```

`pipeline.entsoe_probes` defaults to cache-only checks. Its `--download` flag
permits requests; `pipeline.entsoe_bulk --execute` permits collection and local
writes. `pipeline.entsoe_hourly` reads Cassandra and regenerates local BSON.
`pipeline.entsoe_mongo --mode audit` contacts Atlas for size checks; `pilot` and
`upload` modes write guarded batches. Preserve the existing cache and progress
ledgers when resuming. Moving modules did not move those files or reset budgets.

## Current status and safeguards

The full MongoDB upload **completed and passed final read-back on 13 October
at 16:51:32 UTC**. All **157,680 documents** were compared with local BSON.
Project data plus indexes measured **37.09 MiB / 64 MiB**; inspected user
databases combined measured **37.13 MiB / 256 MiB**. These are dated measurements.
Use `.venv/bin/python -m pipeline.upload_status` for saved verification status.
See [upload operations](docs/mongodb-upload.md).

The saved verification covers nine international borders in both directions,
11 October 2024–10 October 2026: **479,845 native intervals** and **157,680
curated hourly documents**. The BSON artifact is **27.79 MiB before indexes**.
The MongoDB page is implemented and its bounded reader was verified against
the initial pilot. The full dataset is now uploaded and independently read back
by the uploader. **Restart Streamlit** to clear earlier empty/pilot caches, then
select **NO2-DK1 → 2025** to check the full-year pie and January/monthly curves.
The final hosted-app check remains outstanding.

Limits remain **64 MiB project data plus indexes**, **256 MiB across MongoDB
user databases**, **160,000 documents**, **40 document writes/second**, and two
connections. Fresh database checks are required before and during upload.
These are project safeguards, not a guarantee of future usage.

MongoDB reads use the `(connection, time_utc)` index, at most 8,784 documents
and 2 MiB of decoded BSON per connection/year. Results (including empty/error
results) are cached for 24 hours with 27 entries; month changes reuse the cache.
After completing the initial upload, restart the app to clear pilot-era results.
The app uses a pool of two per MongoDB server; driver monitoring connections
are additional. The page never creates collections/indexes or writes documents.

The app updates are implemented locally. The documented NVE
interval limitation, partial-year labels, coverage scope and remaining
submission work are documented in the review. Publishing requires a separate
GitHub update; local changes alone do not change the hosted app.

## Checks

```bash
.venv/bin/python -m unittest discover -s tests -q
```

The ordinary suite uses fixtures and makes no live API/database requests.
Optional local Spark math checks require Java 17 but no running Cassandra:

```bash
RUN_SPARK_TESTS=1 .venv/bin/python -m unittest discover -s tests -p test_entsoe_hourly.py -v
```

## Documentation and references

- [Updated assignment and improvement register](docs/assignment-update-2026-10-12.md)
- [Notebook and pipeline progress](docs/progress.md)
- [Repository cleanup and validation](docs/repository-cleanup.md)
- [Transfer-page implementation and read-only verification](docs/transfer-page.md)
- [Part 2 notebook](notebooks/prosjekt_part2.ipynb)
- [Part 1 repository snapshot for the archived CSV analysis](https://github.com/G0KU-DOTCOM/Streamlit_dashboard/tree/95a35b71c25d5e4c94405deea7462689a0b864c1)
- [IND320 Streamlit notebook](https://github.com/khliland/IND320/blob/main/D2Dbook/1_Deployment1/1_Dashboards/4_Streamlit.ipynb)
- [IND320 REST notebook](https://github.com/khliland/IND320/blob/main/D2Dbook/2_Data_sources/3_APIs/2_REST.ipynb)
- [NVE API](https://biapi.nve.no/magasinstatistikk/swagger/index.html)
- [GitHub repository](https://github.com/G0KU-DOTCOM/Streamlit_dashboard)
- [Streamlit application](https://ind320dashboard.streamlit.app)

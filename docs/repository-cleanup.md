# Repository cleanup — 12 October 2026

## Changes and reasons

| Change | Reason |
| --- | --- |
| Move `load_data.py` to `dashboard/load_data.py`; add `dashboard/reservoir_views.py` | Keep reusable app data/loading/view code together and remove duplicate selection logic from pages. |
| Move the seven `entsoe_*.py` modules to `pipeline/` | Separate local collection, Spark and database operations from the Streamlit pages. |
| Update Python/test/notebook imports to the package paths | Keep the app, tests and notebook usable after the moves; no compatibility copies left in the root. |
| Resolve CLI project root as the parent of `pipeline/` | Preserve the existing cache, secrets, plan, locks and progress-ledger locations. |
| Use `python -m pipeline.<module>` | Make package imports work consistently from the project root. |
| Move the long progress history to `docs/progress.md` and shorten README | Make setup, navigation, directory purpose and current status easier to find. |
| Add `requirements-notebook.txt`; move `ipykernel` out of app dependencies | Separate local Spark/notebook tools from the hosted app's dependencies. Versions match the checked local Spark, Cassandra driver and PyMongo. No packages were installed or upgraded during cleanup. |

`main.py` and `pages/` retain Streamlit's normal multipage structure. The plan
stays at the root so the existing budget and report workflows use the same
configuration. `no_sync/`, `.streamlit/secrets.toml`, the virtual environment,
database contents and saved notebook outputs were not moved or deleted.

## App changes

Data Table and Data Plot share period and EL/NO/VASS choices. Durable session
keys retain choices even when visiting pages without those widgets. Each area
has a table row with five measurement sparklines and a separate line in the
measurement plots. Missing weeks and unavailable areas remain missing; no
zero-filling or geographical summation is introduced. Distinct measurement
units have separate plots. The full eleven fields and their types remain
inspectable, while dates and calendar identifiers are shown as tables.

The Reservoir API page now explains sources and areas rather than duplicating
the explorer. Download bounds and shared caches are unchanged. The UI and
requirements review explicitly retain the unresolved limitation: period
selection filters after NVE's history download, not at the upstream API.

## Validation

- Ordinary suite: **67 tests discovered, 61 passed, six Spark tests skipped**
  unless explicitly enabled. No live API/database calls in this suite.
- Spark-enabled hourly suite: **11 passed**, including those six Spark tests,
  using synthetic data and no Cassandra/MongoDB writes. Spark's local socket
  required running these tests outside the filesystem/network sandbox.
- Streamlit AppTest checks: table/plot navigation and retained choices through
  source/About pages, all column choices, EL/NO/VASS, missing area metadata,
  empty periods, missing weeks and a one-month history.
- Additional app checks reused the **14,913-row local NVE snapshot**: EL (five
  area rows), NO (one), VASS (three) rendered in tables and measurement plots.
  Loader calls were intercepted; this check made no new NVE downloads.
- Safe CLI checks: `python -m pipeline.entsoe_bulk` read the saved report and
  reported 54 verified segments; probes/Mongo `--help` commands succeeded.
- Notebook schema and code syntax validated. Code-cell changes are limited to
  updated package imports; existing outputs and execution counters match the
  pre-cleanup version. This is not a fresh run of database notebook cells.
- Plan limits and frozen period compared with the pre-cleanup version and
  confirmed unchanged. No new MongoDB documents were uploaded; the saved pilot
  remains at 200 documents.

The MongoDB transfer page and full upload remain separate next steps. Nothing
was pushed to GitHub or deployed to Streamlit Cloud during this cleanup.

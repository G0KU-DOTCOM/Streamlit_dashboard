# Notebook and pipeline progress

Historical stages and old section numbers are retained below as development history, not current status. Full upload and local app verification completed on 13 October: 157,680 documents; 37.09 MiB including indexes. Current submission checks are notebook execution/PDF, personal log review and hosted-app verification. Archived section numbers refer to the original notebook layout. For the current layout and commands, see
[the project README](../README.md). The latest requirement review is
[documented separately](assignment-update-2026-10-12.md).

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

Section 6 tests NO2–DK1 physical flows in both directions for 1 January 2026,
using `[entsoe] token` from the same local secrets file. It limits each of two
responses to 128 KiB and reuses XML cached in `no_sync/entsoe_cache/`. The test
needs no running databases. It displays raw A03 points and, in section 6.4, reconstructs the sample
intervals, checks coverage, calculates energy totals and plots the day in
Norwegian time. Section 7 adds a validated A01/A03 interval parser and the first annual plots.

Section 7 covers NO2–DK1 in 2025. Two bounded responses total 3.43 MiB locally.
Spark writes 29,020 intervals to `ind320_energy.cross_border_intervals`, reads
and verifies them, and supplies an annual pie with percentages inside the
slices and a January line plot. Both directions have complete annual coverage.
Use the Python 3.12 environment, Java 17 and running local Cassandra. The
notebook stops Spark after extraction; Cassandra remains running. `pipeline/entsoe_data.py`
contains the bounded downloader and interval parser. Reusing this snapshot
updates fixed keys without duplicates; source revisions with changed interval
boundaries require a replacement strategy before refreshing the database.
No MongoDB writes are made in section 7.

Section 8 and `entsoe_plan.json` define a frozen rolling two-year window,
11 October 2024–10 October 2026 inclusive, with nine international bidding-zone
borders in both directions. Offline budget calculations estimate 157,680 paired
hourly MongoDB documents (27.22 MiB BSON; 54.44 MiB with a 2× planning allowance).
The planned caps are 100 MiB new XML downloads, 128 MiB cache, 1.3 million native
intervals, 64 MiB curated data plus indexes, and 256 MiB whole-cluster MongoDB
usage. `pipeline/entsoe_budget.py` now enforces persistent download/cache/attempt limits,
request spacing and minimum free host space. Raw-row and database-volume guards
are now provided by `pipeline/entsoe_storage.py`; the bulk coordinator must call them.
The planning step makes no data downloads or database writes. A separate
read-only Atlas audit found one 86-byte test document and 36,864 index bytes.
Fresh storage checks are required before any future upload.

Section 9 verifies all nine borders in both directions for 1 January 2026.
The eight new borders required 16 requests and 117,484 decoded bytes (114.73 KiB).
All 18 direction samples cover 24 hours. Its executed table shows import, export,
net import and coverage; reruns are cache-only by default. No databases were
written in this stage. One successful day does not establish two-year coverage.

`pipeline/entsoe_probes.py` performs these bounded sequential checks. Run it without flags
for cache-only verification; `--download` permits missing one-day requests.
`pipeline/entsoe_budget.py` keeps a Git-ignored ledger in `no_sync/entsoe_download_ledger.json`:
80 attempts and 100 MiB of new decoded responses across reruns, 128 MiB total
cache, at least one second between requests, and at least 5 GiB free host space.
Probe responses are capped at 128 KiB; annual responses at 8 MiB. The ledger
begins with the probes; older cache is counted in cache size but not charged as
new traffic. Error bodies and the chunk detecting oversize count too; HTTP
headers and transport overhead are excluded. A process lock prevents concurrent
budget use. Interrupted requests retain reserved bytes and block new downloads
until reviewed. Failed requests are not automatically retried. Keep the ledger
when rerunning; deleting it would discard the cumulative accounting.

Section 10 records a live Spark storage audit: all 29,020 existing flow rows
match the cached 2025 snapshot; zero new rows were needed. `pipeline/entsoe_storage.py`
now guards section 7 writes with actual row counts, allocated volume, host and
Docker free space, and conservative working-space reservations. Identical rows
are skipped; changed snapshots are blocked for review. New writes are flushed
and reread before post-write size checks. Batches must contain complete intended
partitions. The local lock coordinates project writers, not unrelated clients.
The limits are admission checks, not a filesystem quota. The bulk coordinator is now implemented in `pipeline/entsoe_bulk.py`;
MongoDB upload guards are now implemented in `pipeline/entsoe_mongo.py` (see below).

Section 11 completes all 54 planned API/partition jobs using `pipeline/entsoe_bulk.py`:
479,845 native intervals in Cassandra; 17,520 hours per direction on all nine
borders. Final Spark reads confirm exact window boundaries, no gaps/overlaps,
and matching row counts and MWh totals. New bulk XML totalled 53.79 MiB;
allocated Cassandra volume at final verification was 37.40 MiB. These
are measured snapshots, not fixed future sizes. The table and comparison plot
are executed from the saved Spark verification. No MongoDB writes were made.

Run `.venv/bin/python -m pipeline.entsoe_bulk` to inspect saved progress. `--execute`
permits bounded downloads and guarded local writes; verified jobs are reused,
with cache hashes checked, and the final database is verified again. Keep the
Git-ignored download ledger, cache and `no_sync/entsoe_bulk_report.json` when
resuming. Missing/revised cache or failed coverage requires review, not a budget
reset. The frozen period and Russia scope limitation remain as documented.

Section 12 completes Spark hourly curation in `pipeline/entsoe_hourly.py`. It splits
native MW blocks at UTC-hour boundaries and pairs both directions, retaining
coverage minutes and nulls for missing energy. All 157,680 documents have full
coverage; all 18 direction totals match the raw energy within numerical tolerance.
The local file `no_sync/entsoe_curated/hourly_flows.bson` contains 29,135,760
measured BSON bytes (27.79 MiB), excluding indexes. A 2× planning allowance is
55.57 MiB, below the 64 MiB project budget; this is not an Atlas usage measurement.
The saved file was independently read back for IDs, coverage, totals and checksum.
No database writes or new API downloads were made during curation.

Run `.venv/bin/python -m pipeline.entsoe_hourly` with Cassandra running to regenerate
this local artifact. To run the synthetic Spark math checks in addition to the
regular offline tests:

```bash
RUN_SPARK_TESTS=1 .venv/bin/python -m unittest discover -s tests -p test_entsoe_hourly.py -v
```

Both Spark driver and workers use the project's Python 3.12 environment.
`pipeline/entsoe_mongo.py` now provides fresh storage checks, batches of 40, a ceiling of
40 document writes/second, stable-ID inserts, conflict rejection and read-back
verification. The saved 11 October report confirms a 200-document pilot in
`ind320_energy.hourly_flows`; full transfer was subsequently completed on 13 October (see the README). Fresh Atlas checks must
still pass before resuming and around each batch. Keep the existing progress
file so the uploader can resume without duplicating documents.

The upload and transfer page are now completed locally. The log is drafted; personal review, notebook execution/PDF and hosted-app verification remain. No screencast requirement appears in the supplied assignment text.
Local changes must be published to GitHub before they appear in the hosted app.


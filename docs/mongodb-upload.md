# MongoDB upload — 13 October 2026

The full upload was started as a detached local process after a fresh Atlas
storage audit passed. It resumes the existing 200-document pilot and preserves
the source checksum, stable IDs, write-attempt ledger and existing limits.

The preflight audit at **15:00:26 UTC** found 200 documents, 123,016 bytes of
project data plus indexes, and 159,966 bytes across user databases. The verified
BSON artifact contains 157,680 documents and 29,135,760 bytes before indexes.
The process launched at **15:45:10 UTC**. Completion must be checked using the
saved report; the launch time is not evidence of a completed upload.

## Check progress without Codex

From the project folder in the VS Code terminal:

```bash
.venv/bin/python -m pipeline.upload_status
```

This only reads local status/configuration and checks the existing process lock.
It does not contact MongoDB or read credentials. `COMPLETE` requires the saved
final verification count, not just the number of attempted writes. A saved
`running` state without a held lock is reported as not running.

The uploader writes progress to `no_sync/entsoe_mongo_progress.json`. Process
metadata and the log location are in `no_sync/mongo_upload_process.json`.
All these files remain Git-ignored. Do not delete the progress files or start
a second upload while the existing one is active.

## Running conditions and safeguards

The local process continues independently of this chat. A `caffeinate -i`
wrapper prevents automatic idle sleep while the process is running, then exits
with it. Keep the Mac powered on, connected to the internet, and the lid open;
this does not prevent manual sleep or shutdown. Docker/Cassandra is not needed
for this upload because the verified BSON file already exists locally.

At most 40 documents are attempted per second. The full remaining upload takes
at least about 66 minutes, plus database/network/checking time. Every batch is
read back, and storage checks reserve room for remaining data and indexes.
Existing stop limits remain 160,000 documents, 64 MiB project data plus indexes,
and 256 MiB across user databases. Errors stop the process without an automatic
retry loop. The final step compares the full remote dataset with local BSON.

If the process stops, inspect the log and storage/error condition before
resuming. Once the problem is resolved, the existing command resumes safely:

```bash
.venv/bin/python -m pipeline.entsoe_mongo --mode upload
```

No Codex quota reset has been used. No API data is redownloaded for this upload.
The local plan/status text and app caches do not automatically update when the
background upload finishes. After `COMPLETE`, refresh the documented status,
restart Streamlit to clear pilot-era cached results, and verify the app against
the full MongoDB dataset before submission.

## Completed and verified

On **13 October 2026 at 16:51:32 UTC (18:51:32 Europe/Oslo)** the uploader
reported `complete` with **157,680 final verified documents**. It compared every
remote document with the local BSON artifact and checked the collection count.
Data payload: **29,135,760 bytes**; indexes: **9,756,672 bytes**. Project data
plus indexes: **38,892,432 bytes (37.09 MiB)**, below the 64 MiB project stop.
All inspected user databases: **38,929,382 bytes (37.13 MiB)**, below 256 MiB.
The background process has finished. These measurements are dated snapshots.

The next step is to restart Streamlit to clear pilot-era caches and check
connection/year/month views with the uploaded data. Do not rerun the uploader
to refresh the app; the data are already uploaded and verified.

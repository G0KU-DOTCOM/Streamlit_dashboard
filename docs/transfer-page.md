# Cross-border transfer page — 12 October 2026

`pages/5_Cross_Border_Transfers.py` now implements the updated assignment's
separate two-column view. The left side has connection radio buttons, a year
selectbox and an import/export energy pie with percentages inside the slices.
The right side uses multi-select month pills and import/export hourly-mean MW
curves. A source/coverage/cache expander sits below the columns.

## Data access and budget

`dashboard/transfers.py` reads `ind320_energy.hourly_flows` directly with
PyMongo and Streamlit Secrets. It does not import the local pipeline, start
Spark/Cassandra, read a local dataset as a fallback, create indexes or write
documents. The previously created `(connection, time_utc)` index is required;
the reader stops on index/query failure instead of silently doing a full scan.

A query selects one connection and one Norwegian calendar year, clipped to
the frozen snapshot. Start/end dates are converted to UTC for an indexed
half-open range query. Only the timestamp, connection, energies and coverage
fields are returned; `_id` is excluded. Limits are 8,784 documents, 2 MiB of
decoded projected BSON, 200-document batches and a 10-second server query
limit. A one-document overflow sentinel detects excess rows. The cursor is
closed on success/failure. The BSON bound is a processed-payload check, not an
exact network-wire quota; a received batch and protocol overhead also use traffic.

A shared, thread-safe client has a maximum pool of two per server, bounded
connection/queue/socket timeouts and no automatic read retries. MongoDB driver
monitoring connections are additional to that pool. Results, empty results and
safe error messages are cached for 24 hours, with 27 entries (nine connections
× three years). Month choices reuse a cached year. Credentials and raw server
errors are never displayed. App restarts clear caches, so repeated restarts can
cause additional reads. These are conservative bounds, not an account-wide
traffic guarantee across unrelated clients or app replicas.

**After the full initial upload, restart the app** so cached empty/pilot results
are refreshed. The app must not use notebook credentials embedded in source;
its Cloud URI belongs in Streamlit Secrets.

## Correctness and justified adaptations

- A pie is shown only if every expected hour in the selected snapshot interval
  has both directions with complete coverage. The pilot is not an annual total.
- 2025 is complete by design; 2024 and 2026 are labelled partial years. A complete
  partial-year snapshot may have a pie, explicitly labelled as a partial year.
- Months use Europe/Oslo calendar boundaries; storage/time keys remain UTC.
  March 2025 contains 743 hours and October 745, preserving DST transitions.
- The hourly MWh value divided by one hour is mean MW. Incomplete coverage is
  masked; missing values remain gaps, and measured zero remains zero.
- Excluded months retain NaN gaps, so a line never bridges January directly to
  March. Annual pie totals are independent of the month pills.
- The line axis covers the requested snapshot interval, including missing
  trailing hours, rather than zooming to the few available pilot hours.
- Reading a bounded year once supports the annual pie while avoiding new
  database calls for each month click. This is a documented performance choice.
- Two zero annual totals yield an explanatory message, not invented percentages.

## Verification

The live read-only check at **2026-10-12 14:25:40 UTC** read **200 documents**
for NO1-SE3/2024: **30,600 bytes** of projected BSON. They matched the local
pilot exactly. Of the snapshot's 1,969 expected 2024 hours, 200 were complete;
the annual/period pie was correctly withheld. The collection count remained
200 before and after the check. No database data or indexes were changed.

Fresh metadata reported **123,016 bytes** of project data plus indexes and
**159,966 bytes** across the inspected user databases. These are small pilot
measurements, not predictions of the full upload. Index allocation can change
between snapshots. Existing 64 MiB project and 256 MiB cluster admission limits
remain unchanged; the full uploader will perform fresh checks again.

The full local NO2-DK1/2025 artifact is also checked offline against the notebook's
annual import/export totals. This validates the page calculations without
claiming that those full-year documents have already reached MongoDB.

Ten new offline tests cover query/projection/size limits, cursor cleanup,
malformed/duplicate records, missing versus zero energy, DST and month gaps,
percentage labels, cache reuse, partial years, pilot behaviour and safe errors.
The whole ordinary suite now discovers **77 tests: 71 pass and six Spark-only
tests are skipped**. The six Spark tests passed during the preceding repository
cleanup; the pipeline mathematics has not changed in this step.

## Remaining work

The full upload completed on 13 October at 16:51:32 UTC with all 157,680 remote
documents compared against local BSON. Project data plus indexes measured
37.09 MiB, within the 64 MiB project limit. Restart the app to clear pilot caches
and check all connections/years before submission. The hosted-app verification
remains outstanding. See [the completed upload record](mongodb-upload.md).

## Full-data app verification — 13 October 2026

Streamlit AppTest ran the actual transfer page with live MongoDB data after
the full upload. All nine connections rendered with complete 2025 coverage
(8,760 hours each), with no page errors or incomplete-data warnings. The
NO2-DK1 total matched the notebook: approximately 1,153,915 MWh imported and
8,157,331 MWh exported. January/March selection preserved the gap for February;
empty selection produced a helpful message. Month changes caused no new query.

The NO2-DK1 partial-year checks also passed: 1,969 hours for 2024 and 6,791 for
2026, with explicit partial-year labels. The test used 11 bounded queries and
13,394,040 projected BSON bytes (12.77 MiB); no database writes were performed.
The last read was at 2026-10-13 18:05:47 UTC. This is a local app integration
check, not confirmation of the hosted Streamlit Cloud deployment. The saved
report is in Git-ignored `no_sync/full_transfer_app_verification.json`.

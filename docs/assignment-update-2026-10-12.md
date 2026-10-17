# Assignment review — 12 October 2026

This review compares the original assignment with the updated text supplied on
12 October, the current application, and the executed Part 2 notebook. The reservoir table/plot changes below are now implemented locally.
The MongoDB page is now implemented locally and tested against the 200-document
pilot. The user has chosen to retain cached NVE history with local filtering;
this is a documented project decision, not a claim of upstream date filtering. Existing database measurements are dated snapshots, not live audits.

## What changed and what we must do

| Updated requirement | Current implementation | Required action |
| --- | --- | --- |
| The former page-three slider controls **which data are downloaded**. | `dashboard/load_data.py` fetches the full NVE history before either period slider filters it locally. | Unresolved API/requirement mismatch. Do not describe the current slider as restricting the API download. See the evidence below. |
| EL/NO/VASS radio selection controls both plots and `LineChartColumn`, for each associated area number. | The table and plot pages now share period and area choices across navigation. | Implemented: one summary row per area with five measurement sparklines, and one plot line per area. |
| Pages two and three may be reorganised; an extra page and justified usability improvements are allowed. | Data Table and Data Plot share controls; Reservoir API now explains sources and areas. | Implemented. All eleven fields remain inspectable. Measurements use separate axes; calendar descriptors use tables. Notebook figures are preserved. |
| Transfer-page pills select **any set of months**. | The transfer page now reads curated MongoDB data for one connection/year and supports multiple selected months. | Implemented with `st.pills(..., selection_mode="multi")`. Full data upload remains pending; incomplete periods cannot produce an annual pie. |

The separate transfer page implements two `st.columns`: connection `st.radio`,
a different year control and an annual import/export pie on the left; selected
months and an import/export line plot on the right; a source `st.expander` below.
Month selection should affect the line plot, not silently change the annual pie.
Keep percentages inside the pie slices, as requested. Leave visible gaps between
non-adjacent selected months instead of joining a line across excluded months.

The notebook, Cassandra/Spark workflow, curated MongoDB requirement, final log,
PDF and screencast requirements have not changed. Working on `main` remains the
user's explicit choice after receiving the earlier feedback; this review does
not push or publish anything.

## NVE download interval: evidence and unresolved requirement

Checked NVE's [OpenAPI schema](https://biapi.nve.no/magasinstatistikk/swagger/v1/swagger.json)
on 12 October 2026. Its four GET routes provide history (`HentOffentligData`),
latest week, min/max/median, and area metadata. None declares date-range request
parameters. The latest-week route is not an arbitrary historical range selector.
Absence from the schema establishes that server-side date filtering is not
documented; it does not prove that no undocumented capability exists.

Current behaviour is therefore only a fallback: one bounded, cached history
download followed by local filtering. Making dates arguments of a cached Python
function, changing widget labels, or adding unverified URL parameters would not
demonstrate that NVE sends fewer observations. A file-download button would also
serve a different purpose from selecting the upstream API data.

Before claiming full compliance, obtain either a documented NVE range-query
method or clarification from the instructor that the bounded cached fallback is
acceptable. No instructor contact has been made. The assignment's permission
for slight usability deviations does not by itself resolve this data-download
requirement. If a range endpoint becomes available, verify the response dates,
request arguments and payload size before replacing the loader.

## Work already reusable and work still outstanding

- NVE API loading and thirteen recreated Part 1 notebook figures remain useful.
- The saved Spark verification records **479,845 native intervals** for nine
  international bidding-zone borders in both directions. The frozen window is
  **11 October 2024 through 10 October 2026**, inclusive in Norwegian time. It
  was selected on 11 October; it does not advance automatically on reruns.
- Spark produced **157,680 hourly documents**, containing **29,135,760 BSON
  bytes (27.79 MiB)** before indexes. This schema supports the new month pills
  without another ENTSO-E download or a second copy of the dataset.
- The saved uploader report dated **11 October 2026, 19:16 UTC** records a
  successful **200-document pilot** in `ind320_energy.hourly_flows`. It records
  45,192 bytes of project data plus indexes and 82,142 across the inspected user
  databases. These small pilot measurements are not an estimate of the full
  upload or a fresh measurement of Atlas today. Full upload remains pending.
- The Streamlit MongoDB reader/page and `pymongo` application dependency are
  implemented. The page was verified against the 200-document pilot on
  12 October. Full upload is still pending. Cloud secrets remain in Streamlit Secrets.
- The final 300–500-word personal log, final AI-use statement, executed PDF,
  hosted-app verification and five-minute screencast remain outstanding.

2025 is the only complete calendar year in this snapshot. Default the annual
pie to 2025 and clearly label partial 2024/2026 totals. The assignment uses
“production” when describing that pie, but the requested source is cross-border
flow: label the chart **import/export energy**, not generation. The existing
Russia scope limitation still needs historical evidence before claiming that
the inventory covers every Norwegian border during the entire period.

## Improvements and reasons

The user's permission to improve the solution is recorded through explicit
choices, benefits and limitations rather than treating every deviation as
automatically satisfying the assessment requirements.

| Choice | Why it helps | Status and limitation |
| --- | --- | --- |
| Shared bounded API cache and persistent ENTSO-E request ledger | Reduces repeat downloads and enforces local traffic/storage budgets. | Implemented. Cache can be stale; disclose its timestamp. NVE local filtering remains the unresolved deviation above. |
| Reconstruct intervals and weight energy by duration | A simple sum/average of irregular A03 change points gives incorrect energy. | Implemented and checked against coverage and directional MWh totals. |
| One document per UTC hour and connection, containing both directions | Reduces document count while supporting annual totals and monthly plots. UTC avoids ambiguous repeated autumn hours. | Implemented locally; pilot uploaded. Hourly means smooth short peaks, so native intervals remain in Cassandra. |
| Explicit coverage and null/zero distinction | Prevents missing measurements from being presented as zero flows. | Implemented. Display times and calendar filters must use Europe/Oslo boundaries converted to UTC. |
| Stable IDs, small batches, conservative size checks and read-back verification | Supports resuming without duplicate storage and detects conflicting data. | Implemented uploader; full upload pending. Project locks do not control unrelated database clients. |
| Shared reservoir period/area controls and per-area table trends | Makes the same selection mean the same thing in tables and plots, fulfilling the newly clarified area requirement. | Implemented and tested for EL, NO and VASS, empty periods, missing areas and navigation through other pages. |
| Indexed, bounded MongoDB reads cached by connection/year | Supports the pie and month plots without retrieving every connection on each interaction. | Implemented: one connection/year, at most 8,784 documents and 2 MiB decoded BSON, 24-hour cache with 27 entries. Pilot read verified; full upload and publication pending. |

The course [Streamlit notebook](https://github.com/khliland/IND320/blob/main/D2Dbook/1_Deployment1/1_Dashboards/4_Streamlit.ipynb)
was read during this review: it demonstrates caching, sliders, radio buttons,
pills, columns and expanders. Multiple month selection is configured using the
documented [multi-selection mode](https://docs.streamlit.io/develop/api-reference/widgets/st.pills).
We retain these course patterns while adding the explicitly documented safeguards.

## Storage limits and next implementation order

Keep the existing project limits: **160,000 curated documents**, **64 MiB**
MongoDB project data plus indexes, **256 MiB** across user databases, no more
than **40 document writes per second**, and a pool of **two connections**.
These are conservative project limits, not the service's published quota.
The measured 27.79 MiB excludes indexes; the 2× planning allowance is not a
guarantee. Fresh database size checks remain mandatory before and during upload.
This review performs no data downloads from NVE/ENTSO-E or database writes.

1. Project decision: the user accepts cached NVE history with local filtering.
   Keep the upstream limitation explicit; instructor acceptance has not been established.
2. Completed locally: reservoir views share period and EL/NO/VASS selection,
   with separate area plots and table trends; test results are in the cleanup log.
3. Completed locally: full-data MongoDB page checks passed for all nine
   connections in 2025, multiple/empty month selection and NO2-DK1 partial years.
4. Completed on 13 October: all 157,680 uploaded documents were compared with
   local BSON; project storage including indexes was 37.09 MiB, below 64 MiB.
5. Verify the app reads MongoDB directly, complete the notebook documentation,
   and prepare the executed PDF, hosted app and screencast.

## Implementation and repository cleanup

Implemented locally on 12 October: shared table/plot selection, five per-area
measurement sparklines, all-area measurement curves, missing-data notices,
and a dedicated source/area explanation page. Calendar identifiers are shown
as tables and measurements with different units use separate plots. This
improves readability without changing the observations or notebook figures.

The [repository cleanup log](repository-cleanup.md) records file moves, updated
commands, preserved local data paths and validation. The subsequent MongoDB transfer-page implementation and read-only check are
recorded in [the transfer-page note](transfer-page.md). Upstream NVE interval
filtering is not implemented.

## Accepted NVE choice

The user explicitly chose to keep the current cached NVE history and local
filtering after the limitation was explained. We continue with that design and
its documentation. This records the project preference; it does not imply that
the NVE server filters dates or that the instructor has approved the deviation.

# Norwegian Reservoir Dashboard

This repository contains the first part of my IND320 project work. The project
uses historical Norwegian reservoir data from `reservoirs.csv` and presents the
results in both a Jupyter Notebook and a Streamlit application.

## Project contents

- `notebooks/prosjekt_part1.ipynb` contains the data preparation, investigation,
  visualizations, work log, and description of AI usage.
- `main.py` is the home page of the Streamlit application.
- `pages/` contains the table, plot, and project-information pages.
- `data/reservoirs.csv` is the local data source used in part 1.

## Run the Streamlit app locally

Install the packages in `requirements.txt`, then run the following command from
the project folder:

```bash
streamlit run main.py
```

## Part 2 notebook progress

`notebooks/prosjekt_part2.ipynb` contains separate sections for the Spark–Cassandra
test, MongoDB test, a small NVE API sample, and the Part 1 figures recreated from
NVE API history. Use the project's Python 3.12 environment. Section 4 can run on
its own without Docker or database credentials.

The history section caps the decoded API response at 8 MiB and caches it in the
Git-ignored `no_sync/nve_cache/` directory. Leave `REFRESH_NVE_HISTORY = False` to
reuse the snapshot without another download. The original comparison period is
8 January 1995–6 September 2026. This section makes no database writes.

The Streamlit app still uses its Part 1 CSV source until its API migration.

## Links

- [GitHub repository](https://github.com/G0KU-DOTCOM/Streamlit_dashboard)
- [Streamlit application](https://ind320dashboard.streamlit.app)

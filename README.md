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

## Links

- [GitHub repository](https://github.com/G0KU-DOTCOM/Streamlit_dashboard)
- [Streamlit application](https://ind320dashboard.streamlit.app)

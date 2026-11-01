# ERA5 hourly regional means

`NO3_era5_2024-01-01_2024-12-31_hourly.csv.gz` contains 8784 UTC hours from
[Open-Meteo's Historical Weather API](https://open-meteo.com/en/docs/historical-weather-api),
using ERA5. Temperature is in °C; precipitation is the preceding hour's amount
in mm. Each row averages the 1000 NO3 locations in
`data/geography/weather_locations.csv`; `point_count` records coverage.

This small summary is included so the app can reuse the notebook's download.
Other area/year combinations are prepared only after an explicit button press.
`dashboard.weather_data.prepare_weather_summary` creates summaries from saved
raw data or ERA5 downloads. Raw point data and download batches remain in the
Git-ignored `no_sync/weather/` directory.

Weather data: Open-Meteo / ERA5, [CC BY 4.0](https://open-meteo.com/en/licence).
Region boundaries: [NVE Atlas](https://atlas.nve.no).

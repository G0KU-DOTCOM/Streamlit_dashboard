"""Shared ERA5 downloads and small hourly summaries for the notebook and app."""
from pathlib import Path
import requests
import pandas as pd
import time


ROOT = Path(__file__).resolve().parents[1]
WEATHER_COLUMNS = ["temperature_2m", "precipitation"]


def weather_region(area_type, area_number):
    """Match the reservoir selector to the assignment's sampled regions."""
    if area_type == "EL" and area_number in (1, 2, 3, 4, 5):
        return f"NO{area_number}"
    if area_type == "VASS":
        return {1: "Øst", 2: "Vest", 3: "Nord"}.get(area_number)
    # No national sample or separate VASS4 sample was prepared in the notebook.
    return None


def _hourly_totals(frame):
    if frame[WEATHER_COLUMNS].isna().any().any():
        raise ValueError("Weather data contain missing values.")
    grouped = frame.groupby("time")
    totals = grouped[WEATHER_COLUMNS].sum()
    totals["point_count"] = grouped.size()
    return totals


def _finish_hourly(parts, expected_times, point_count):
    totals = pd.concat(parts).groupby(level=0).sum().sort_index()
    if not totals.index.equals(expected_times) or not totals["point_count"].eq(point_count).all():
        raise ValueError("Weather data do not cover every selected location and hour.")
    totals[WEATHER_COLUMNS] = totals[WEATHER_COLUMNS].div(totals["point_count"], axis=0)
    return totals.reset_index()


def download_weather(region, start_date, end_date, batch_size=100, *, hourly=False, progress=None):
    """Retrieve hourly ERA5 temperature and precipitation for the saved region locations."""
    root = ROOT
    locations = pd.read_csv(root / "data/geography/weather_locations.csv")
    locations = locations.loc[locations["region"].eq(region)].sort_values("point_id")
    if locations.empty:
        raise ValueError(f"Unknown region: {region}")

    def report(message, completed=0):
        if progress is None:
            print(message, flush=True)
        else:
            progress(message, completed, len(locations))

    start, end = pd.Timestamp(start_date), pd.Timestamp(end_date)
    if start > end:
        raise ValueError("The start date must be on or before the end date.")
    start_date, end_date = start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")
    expected_times = pd.date_range(start_date, end + pd.Timedelta(days=1),
                                   freq="h", inclusive="left", tz="UTC")
    folder = root / "no_sync/weather"
    folder.mkdir(parents=True, exist_ok=True)
    saved_file = folder / f"{region}_era5_{start_date}_{end_date}.csv.gz"
    if saved_file.exists():
        report("Reading saved weather data.")
        if hourly:
            chunks = pd.read_csv(saved_file, parse_dates=["time"], chunksize=100_000)
            return _finish_hourly([_hourly_totals(chunk) for chunk in chunks], expected_times, len(locations))
        return pd.read_csv(saved_file, parse_dates=["time"])

    # Download locations in batches and reuse completed batches on subsequent runs.
    parts_folder = folder / f"{region}_era5_{start_date}_{end_date}_parts"
    parts_folder.mkdir(exist_ok=True)
    frames = []
    for offset in range(0, len(locations), batch_size):
        batch = locations.iloc[offset:offset + batch_size]
        part_file = parts_folder / f"points_{batch.point_id.iloc[0]:04d}_{batch.point_id.iloc[-1]:04d}.csv.gz"
        if part_file.exists():
            part = pd.read_csv(part_file, parse_dates=["time"])
            frames.append(_hourly_totals(part) if hourly else part)
            report(f"Loaded {offset + len(batch)} of {len(locations)} locations.", offset + len(batch))
            continue
        params = {
            "latitude": ",".join(batch["latitude"].astype(str)),
            "longitude": ",".join(batch["longitude"].astype(str)),
            "start_date": start_date, "end_date": end_date,
            "hourly": "temperature_2m,precipitation",
            "models": "era5", "timezone": "GMT",
            "temperature_unit": "celsius", "precipitation_unit": "mm",
        }
        # Pause and retry if the per-minute API limit is reached.
        for attempt in range(3):
            response = requests.post("https://archive-api.open-meteo.com/v1/archive",
                                     data=params, timeout=(15, 180))
            if response.status_code != 429 or attempt == 2:
                break
            report("API limit reached. Waiting 65 seconds before retrying.", offset)
            time.sleep(65)
        if not response.ok:
            raise requests.HTTPError(f"Open-Meteo {response.status_code}: {response.text[:300]}",
                                     response=response)
        results = response.json()
        if isinstance(results, dict):
            results = [results]
        assert len(results) == len(batch), "Unexpected number of locations in the API response."

        # Keep one row per location and hour, linked to the point ID in the coordinate file.
        batch_frames = []
        for point_id, result in zip(batch["point_id"], results):
            assert result["hourly_units"]["temperature_2m"] == "°C"
            assert result["hourly_units"]["precipitation"] == "mm"
            frame = pd.DataFrame(result["hourly"])
            frame["time"] = pd.to_datetime(frame["time"], utc=True)
            assert pd.DatetimeIndex(frame["time"]).equals(expected_times), "Unexpected timestamps."
            frame.insert(0, "point_id", point_id)
            batch_frames.append(frame)
        part = pd.concat(batch_frames, ignore_index=True)
        assert not part.isna().any().any(), "The API response contains missing values."
        part.to_csv(part_file, index=False, compression="gzip")
        frames.append(_hourly_totals(part) if hourly else part)
        report(f"Saved {offset + len(batch)} of {len(locations)} locations.", offset + len(batch))
        time.sleep(2)
    if hourly:
        return _finish_hourly(frames, expected_times, len(locations))
    data = pd.concat(frames, ignore_index=True)
    data.to_csv(saved_file, index=False, compression="gzip")
    report(f"Saved: {saved_file.name}", len(locations))
    return data


def summary_path(region, start_date, end_date):
    return ROOT / "data/weather" / f"{region}_era5_{start_date}_{end_date}_hourly.csv.gz"


def read_weather_summary(region, start_date, end_date):
    """Read existing hourly means without starting a download."""
    path = summary_path(region, start_date, end_date)
    if not path.exists():
        return None
    data = pd.read_csv(path, parse_dates=["time"])
    expected = pd.date_range(start_date, pd.Timestamp(end_date) + pd.Timedelta(days=1),
                             freq="h", inclusive="left", tz="UTC")
    if not pd.DatetimeIndex(data["time"]).equals(expected):
        raise ValueError("Saved weather data have incomplete or unexpected timestamps.")
    if data.isna().any().any() or not data["point_count"].eq(1000).all():
        raise ValueError("Saved weather data must include all 1000 locations per hour.")
    return data


def prepare_weather_summary(region, start_date, end_date, progress=None):
    """Create hourly means from saved raw data or an explicit API download."""
    existing = read_weather_summary(region, start_date, end_date)
    if existing is not None:
        return existing
    # Aggregate batches rather than holding the full point dataset in app memory.
    data = download_weather(region, start_date, end_date, hourly=True, progress=progress)
    path = summary_path(region, start_date, end_date)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    data.to_csv(temporary, index=False, compression="gzip")
    temporary.replace(path)
    return data

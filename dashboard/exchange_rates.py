"""Read Norges Bank's daily EUR and USD spot exchange rates."""

from datetime import date
from io import StringIO

import pandas as pd
import requests


EXCHANGE_RATE_URL = "https://data.norges-bank.no/api/data/EXR/B.EUR+USD.NOK.SP"
RATE_COLUMNS = {"EUR": "eur_nok", "USD": "usd_nok"}
REQUIRED_FIELDS = {
    "FREQ", "BASE_CUR", "QUOTE_CUR", "TENOR", "UNIT_MULT", "TIME_PERIOD", "OBS_VALUE",
}


class ExchangeRateError(RuntimeError):
    """A download or data problem that can be explained to the user."""


def _as_date(value: date | str) -> date:
    if type(value) is date:
        return value
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("Use calendar dates in YYYY-MM-DD format.") from exc


def download_exchange_rates(start_date: date | str, end_date: date | str) -> pd.DataFrame:
    """Return NOK per EUR and per USD, indexed by published observation dates.

    Both bounds are inclusive. Dates have no timezone or time of day, and dates
    without a published quote for either currency are absent from the result.
    """
    start, end = _as_date(start_date), _as_date(end_date)
    if start > end:
        raise ValueError("The start date must be on or before the end date.")

    params = {
        "format": "csv",
        "locale": "en",
        "startPeriod": start.isoformat(),
        "endPeriod": end.isoformat(),
    }
    empty_message = "Norges Bank has no published exchange rates for the selected dates."
    try:
        response = requests.get(EXCHANGE_RATE_URL, params=params, timeout=(10, 30))
        if response.status_code in (204, 404):
            raise ExchangeRateError(empty_message)
        response.raise_for_status()
    except requests.RequestException as exc:
        raise ExchangeRateError(
            "Could not download exchange rates from Norges Bank. Try again later."
        ) from exc

    try:
        # Use SDMX field IDs and the English locale for semicolon CSV with decimal points.
        rates = pd.read_csv(
            StringIO(response.text), sep=";", usecols=REQUIRED_FIELDS, dtype=str, keep_default_na=False,
        )
    except pd.errors.EmptyDataError as exc:
        raise ExchangeRateError(empty_message) from exc
    except ValueError as exc:
        raise ExchangeRateError("Norges Bank returned an unexpected exchange rate format.") from exc

    if rates.empty:
        raise ExchangeRateError(empty_message)
    if set(rates["BASE_CUR"]) != set(RATE_COLUMNS):
        raise ExchangeRateError("Expected published rates for both EUR and USD from Norges Bank.")

    # The multiplier must be zero because the output is NOK per single unit of EUR or USD.
    expected_series = (
        rates["FREQ"].eq("B") & rates["QUOTE_CUR"].eq("NOK")
        & rates["TENOR"].eq("SP") & rates["UNIT_MULT"].eq("0")
    )
    if not expected_series.all():
        raise ExchangeRateError("Expected daily NOK spot rates per unit of foreign currency.")

    try:
        rates["date"] = pd.to_datetime(rates["TIME_PERIOD"], format="%Y-%m-%d")
        rates["nok"] = pd.to_numeric(rates["OBS_VALUE"])
    except ValueError as exc:
        raise ExchangeRateError("Norges Bank returned an invalid exchange rate date or value.") from exc
    if not rates["date"].between(pd.Timestamp(start), pd.Timestamp(end)).all():
        raise ExchangeRateError("Norges Bank returned dates outside the requested period.")
    if not rates["nok"].between(0, float("inf"), inclusive="neither").all():
        raise ExchangeRateError("Norges Bank returned a missing or invalid exchange rate.")
    if rates.duplicated(["date", "BASE_CUR"]).any():
        raise ExchangeRateError("Norges Bank returned duplicate dates for a currency.")

    # A date with only one quote retains a missing value in the other currency's column.
    daily = rates.pivot(index="date", columns="BASE_CUR", values="nok")
    daily = daily.rename(columns=RATE_COLUMNS).rename_axis(columns=None)
    return daily[list(RATE_COLUMNS.values())].sort_index()

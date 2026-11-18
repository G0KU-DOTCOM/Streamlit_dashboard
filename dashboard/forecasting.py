"""Weekly reservoir forecasts following the IND320 River SNARIMAX example."""

from numbers import Integral

import numpy as np
import pandas as pd
from river import time_series


def forecast_reservoir_snarimax(
    history, area_type, area_number, train_start, train_end, horizon, *,
    p, d, q, m=1, sp=0, sd=0, sq=0,
):
    """Return the selected training series and its dynamic filling forecast.

    Training bounds are inclusive calendar dates. Filling values and forecasts
    use fractions. Each forecast step advances one week from the last training
    observation. Seasonal defaults follow River's SNARIMAX constructor.
    """
    settings = {"p": p, "d": d, "q": q, "m": m, "sp": sp, "sd": sd, "sq": sq}
    for name, value in {**settings, "horizon": horizon}.items():
        minimum = 1 if name in ("horizon", "m") else 0
        if isinstance(value, bool) or not isinstance(value, Integral) or value < minimum:
            raise ValueError(f"{name} must be an integer of at least {minimum}.")

    start, end = pd.Timestamp(train_start), pd.Timestamp(train_end)
    if pd.isna(start) or pd.isna(end) or start.tzinfo is not None or end.tzinfo is not None:
        raise ValueError("Use calendar dates for the training period.")
    if start > end:
        raise ValueError("The training start must be on or before the training end.")

    # Filter before training so the function can receive the complete NVE history.
    selected = history.loc[
        history["area_type"].eq(area_type) & history["area_number"].eq(area_number)
        & history["observation_date"].between(start, end),
        ["observation_date", "filling_fraction"],
    ].sort_values("observation_date")
    training = selected.set_index("observation_date")["filling_fraction"].astype(float)
    if training.empty:
        raise ValueError("No reservoir observations match this area and training period.")
    if not training.index.is_unique or not (
        training.index[1:] - training.index[:-1] == pd.Timedelta(days=7)
    ).all():
        raise ValueError("Training requires consecutive, unique weekly observations.")
    if not np.isfinite(training.to_numpy()).all():
        raise ValueError("Training contains missing or invalid filling values.")

    model = time_series.SNARIMAX(**settings)
    if len(training) <= model.differencer.n_required_past_values:
        raise ValueError("The selected differencing orders require more training observations.")

    # The course's learn_one loop updates River's scaler and regressor in time order.
    for value in training:
        model.learn_one(float(value))

    # River recursively uses its own predictions for all steps beyond the first.
    predictions = np.asarray(model.forecast(horizon=horizon), dtype=float)
    if not np.isfinite(predictions).all():
        raise ValueError("SNARIMAX produced invalid values. Review the selected model settings.")
    dates = pd.date_range(
        training.index[-1] + pd.Timedelta(days=7), periods=horizon, freq="7D",
        name="observation_date",
    )
    forecast = pd.Series(predictions, index=dates, name="snarimax_filling_fraction")
    return training, forecast

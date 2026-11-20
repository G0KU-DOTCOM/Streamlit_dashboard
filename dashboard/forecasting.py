"""Weekly reservoir forecasts following the IND320 River SNARIMAX example."""

from numbers import Integral

import numpy as np
import pandas as pd
from river import time_series


def forecast_reservoir_snarimax(
    history, area_type, area_number, train_start, train_end, horizon, *,
    p, d, q, m=1, sp=0, sd=0, sq=0, exogenous=None, future_exogenous=None,
):
    """Return the selected training series and its dynamic filling forecast.

    Training bounds are inclusive calendar dates. Filling values and forecasts
    use fractions. Each forecast step advances one week from the last training
    observation. Seasonal defaults follow River's SNARIMAX constructor.

    Optional exogenous frames have one numeric feature per column and are
    indexed by reservoir observation dates. Future feature values must be
    supplied explicitly for every forecast date using the same columns.
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

    dates = pd.date_range(
        training.index[-1] + pd.Timedelta(days=7), periods=horizon, freq="7D",
        name="observation_date",
    )
    training_features = None
    future_features = None
    if (exogenous is None) != (future_exogenous is None):
        raise ValueError("Supply both training and future exogenous values.")
    if exogenous is not None:
        if exogenous.empty or not exogenous.columns.is_unique or not exogenous.index.is_unique:
            raise ValueError("Training exogenous values need unique dates and feature columns.")
        if not future_exogenous.index.equals(dates):
            raise ValueError("Future exogenous dates must match every forecast week in order.")
        if not future_exogenous.columns.equals(exogenous.columns):
            raise ValueError("Training and future exogenous feature columns must match.")
        training_features = exogenous.reindex(training.index).astype(float)
        future_features = future_exogenous.astype(float)
        if not (
            np.isfinite(training_features.to_numpy()).all()
            and np.isfinite(future_features.to_numpy()).all()
        ):
            raise ValueError("Exogenous values contain missing or invalid features.")

    model = time_series.SNARIMAX(**settings)
    if len(training) <= model.differencer.n_required_past_values:
        raise ValueError("The selected differencing orders require more training observations.")

    # The course's learn_one loop updates River's scaler and regressor in time order.
    for observed_date, value in training.items():
        features = None
        if training_features is not None:
            features = training_features.loc[observed_date].to_dict()
        model.learn_one(float(value), x=features)

    # River recursively uses its own predictions for all steps beyond the first.
    future_records = None if future_features is None else future_features.to_dict("records")
    predictions = np.asarray(model.forecast(horizon=horizon, xs=future_records), dtype=float)
    if not np.isfinite(predictions).all():
        raise ValueError("SNARIMAX produced invalid values. Review the selected model settings.")
    forecast = pd.Series(predictions, index=dates, name="snarimax_filling_fraction")
    return training, forecast

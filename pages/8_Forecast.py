"""The tested River model, with shared map time and explicit future scenarios."""

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from dashboard.app_state import area_badge, horizon_control, week_control
from dashboard.forecasting import forecast_reservoir_snarimax
from dashboard.load_data import load_data_or_stop
from dashboard.reservoir_views import area_controls, remember_selection
from dashboard.theme import BLUE, style_figure
from dashboard.weather_data import weather_region
from dashboard.weekly import load_weekly_weather, prepare_weather_scenario


@st.cache_data(max_entries=16, show_spinner=False)
def calculate(history, kind, number, cutoff, weeks, horizon, orders, columns):
    start = pd.Timestamp(cutoff) - pd.Timedelta(weeks=weeks - 1)
    training_dates = pd.date_range(start, cutoff, freq="7D", name="observation_date")
    forecast_dates = pd.date_range(pd.Timestamp(cutoff) + pd.Timedelta(weeks=1),
                                   periods=horizon, freq="7D", name="observation_date")
    training_x = future_x = None
    counts = None
    if columns:
        region = weather_region(kind, number)
        if region is None:
            raise ValueError("No weather sample exists for this area. Use filling history alone.")
        weather, _ = load_weekly_weather(region)
        training_x, future_x, counts = prepare_weather_scenario(weather, training_dates, forecast_dates)
        training_x, future_x = training_x[list(columns)], future_x[list(columns)]
    training, prediction = forecast_reservoir_snarimax(
        history, kind, number, start, cutoff, horizon, **orders,
        exogenous=training_x, future_exogenous=future_x,
    )
    if len(training) != weeks:
        raise ValueError(f"This selection needs {weeks} complete training weeks; only {len(training)} are available.")
    observed = history.loc[history.area_type.eq(kind) & history.area_number.eq(number)].set_index(
        "observation_date").filling_fraction.reindex(prediction.index)
    return training, prediction, observed, counts


def forecast_figure(training, prediction, observed):
    display = training.iloc[-min(52, len(training)):]
    cutoff = training.index[-1]
    baseline = pd.Series(training.iloc[-1], index=prediction.index)
    forecast_x = [cutoff, *prediction.index]
    forecast_y = np.r_[training.iloc[-1], prediction] * 100
    figure = go.Figure([
        go.Scatter(x=display.index, y=display * 100, name="Filling history", mode="lines",
                   line=dict(color=BLUE, width=2)),
        go.Scatter(x=forecast_x, y=forecast_y, name="SNARIMAX forecast", mode="lines+markers",
                   line=dict(color=BLUE, dash="dash", width=2), marker=dict(size=4)),
        go.Scatter(x=prediction.index, y=observed * 100, name="Observed after cutoff", mode="lines",
                   connectgaps=False, showlegend=bool(observed.notna().any()),
                   line=dict(color="#53687f", width=2)),
        go.Scatter(x=prediction.index, y=baseline * 100, name="Last-value reference", mode="lines",
                   line=dict(color="#a9bacb", dash="dot", width=1.5), visible="legendonly"),
    ])
    figure.add_shape(type="line", x0=cutoff, x1=cutoff, y0=0, y1=1, yref="paper",
                     line=dict(color="#a9bacb", width=1))
    figure.add_annotation(x=cutoff, y=1, yref="paper", text="Training ends", showarrow=False,
                          yshift=-14, yanchor="top", font=dict(size=11))
    # The play button reveals successive forecast weeks; all values were computed
    # recursively before animation, with no future observations fed into training.
    figure.frames = [go.Frame(
        name=str(step), traces=[1],
        data=[go.Scatter(x=forecast_x[:step + 1], y=forecast_y[:step + 1])],
    ) for step in range(1, len(prediction) + 1)]
    figure.update_layout(updatemenus=[dict(type="buttons", direction="left", x=0, y=-.2,
        showactive=False, buttons=[
            dict(label="Play forecast", method="animate", args=[None, {"frame": {"duration": 220, "redraw": False}, "transition": {"duration": 0}, "fromcurrent": False}]),
            dict(label="Show all", method="animate", args=[[str(len(prediction))], {"mode": "immediate", "frame": {"duration": 0, "redraw": False}}]),
        ])])
    style_figure(figure, height=470, y_title="Filling (%)")
    figure.update_layout(margin=dict(b=90), xaxis=dict(range=[display.index[0], prediction.index[-1]]))
    return figure


st.title("Forecast reservoir filling")
st.write("Train on weekly history and forecast the selected area's filling. The cutoff and horizon are shared with Home.")
history = load_data_or_stop()
kind, number, labels = area_controls("forecast", history)
area_badge()
if number is None:
    st.info("Choose one area to run a forecast.")
    st.stop()
area = history.loc[history.area_type.eq(kind) & history.area_number.eq(number)]
if area.empty:
    st.info("No filling observations exist for this area.")
    st.stop()

cutoff = week_control(area, "forecast")
left, right = st.columns(2)
with left:
    weeks = st.number_input("Training history (weeks)", min_value=2, max_value=1000,
                            value=st.session_state.get("forecast_training_weeks", 104), step=1,
                            key="_forecast_training_weeks", on_change=remember_selection,
                            args=("forecast_training_weeks", "_forecast_training_weeks"))
with right:
    horizon = horizon_control("forecast")
start = pd.Timestamp(cutoff) - pd.Timedelta(weeks=weeks - 1)
st.caption(f"Training: {start:%d %b %Y}–{cutoff:%d %b %Y}. Forecast: {pd.Timestamp(cutoff) + pd.Timedelta(weeks=1):%d %b %Y}–{pd.Timestamp(cutoff) + pd.Timedelta(weeks=horizon):%d %b %Y}.")

with st.expander("Model settings & data"):
    st.write("Starting settings: filling-only SNARIMAX selected from the notebook's 2025 comparisons. Accuracy varies by season.")
    columns = st.columns(3)
    defaults = dict(p=1, d=1, q=1, m=52, sp=1, sd=0, sq=0)
    orders = {}
    for index, (name, default) in enumerate(defaults.items()):
        orders[name] = columns[index % 3].number_input(
            name, min_value=1 if name == "m" else 0,
            max_value=104 if name == "m" else (3 if name in ("d", "sd") else 52),
            value=st.session_state.get(f"forecast_order_{name}", default), step=1,
            key=f"_forecast_order_{name}", on_change=remember_selection,
            args=(f"forecast_order_{name}", f"_forecast_order_{name}"),
        )
    inputs = st.multiselect("Additional weather inputs", ["precipitation_mm", "temperature_c"],
        format_func=lambda value: {"precipitation_mm": "Precipitation", "temperature_c": "Temperature"}[value],
        default=st.session_state.get("forecast_weather_inputs", []),
        key="_forecast_weather_inputs", on_change=remember_selection,
        args=("forecast_weather_inputs", "_forecast_weather_inputs"))
    st.caption("Future weather uses historical means for the corresponding ISO weeks, computed only from the selected training history. Each input describes the previous week. Saved three-year weather is available for NO3; other areas need saved weather covering the full training period.")

signature = (kind, number, str(cutoff), weeks, horizon, tuple(orders.items()), tuple(inputs))
if st.button("Run forecast", type="primary", icon=":material/trending_up:"):
    try:
        with st.spinner("Training SNARIMAX and forecasting weekly filling…"):
            result = calculate(history, kind, number, cutoff, weeks, horizon, orders, tuple(inputs))
        st.session_state["forecast_result"] = (signature, result)
    except (ValueError, OSError, KeyError, ArithmeticError) as exc:
        st.error(str(exc))

stored = st.session_state.get("forecast_result")
if stored and stored[0] == signature:
    training, prediction, observed, counts = stored[1]
    known = observed.notna()
    st.subheader("Historical evaluation" if known.any() else "Future forecast")
    st.caption(f"{labels[number]} · {len(training)} training weeks · {len(prediction)} forecast weeks")
    st.plotly_chart(forecast_figure(training, prediction, observed), key="reservoir_forecast")
    if known.any():
        errors = (prediction[known] - observed[known]) * 100
        baseline_errors = (training.iloc[-1] - observed[known]) * 100
        metrics = st.columns(3)
        metrics[0].metric("SNARIMAX MAE", f"{errors.abs().mean():.2f} pp")
        metrics[1].metric("SNARIMAX RMSE", f"{np.sqrt(errors.pow(2).mean()):.2f} pp")
        metrics[2].metric("Last-value MAE", f"{baseline_errors.abs().mean():.2f} pp")
        st.caption(f"Scored on {int(known.sum())} available observations after the cutoff. These observations were excluded from training.")
    if counts is not None:
        st.info(f"Weather scenario: each forecast-week mean uses {int(counts.min())}–{int(counts.max())} past observations. This is a scenario, not a weather forecast.")
    if prediction.lt(0).any() or prediction.gt(1).any():
        st.warning("Some forecasts fall outside 0–100%. Values are retained for inspection; consider a different configuration.")
    with st.expander("Weekly forecast values"):
        table = pd.DataFrame({"Forecast (%)": prediction * 100, "Observed (%)": observed * 100})
        st.dataframe(table, column_config={"observation_date": st.column_config.DateColumn("Week ending")})
        st.download_button("Download forecast", table.to_csv().encode(), "reservoir_forecast.csv", "text/csv")
else:
    st.info("Choose settings and run the forecast. Changing the area or settings requires a new run.")

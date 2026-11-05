"""Reservoir filling and regional weather analyses shared by notebook and app."""

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy.fft import dct, idct
from scipy.signal import spectrogram
from scipy.stats import median_abs_deviation
from sklearn.neighbors import LocalOutlierFactor
from sklearn.preprocessing import StandardScaler
from statsmodels.tsa.seasonal import STL


def plot_reservoir_stl(filling_fraction, seasonal=13, trend=89, robust=True):
    """Return an STL decomposition figure for a regular weekly filling-fraction series."""
    series = filling_fraction.sort_index()
    if not isinstance(series.index, pd.DatetimeIndex) or len(series) < 104:
        raise ValueError("Use at least two 52-week cycles with a datetime index.")
    if not (series.index[1:] - series.index[:-1] == pd.Timedelta(days=7)).all():
        raise ValueError("The series must have consecutive, unique weekly observations.")
    if not np.isfinite(series.to_numpy(dtype=float)).all():
        raise ValueError("The series contains missing or invalid values.")
    if not isinstance(seasonal, (int, np.integer)) or seasonal < 3 or seasonal % 2 == 0:
        raise ValueError("The seasonal smoother must be an odd integer of at least 3.")
    if not isinstance(trend, (int, np.integer)) or trend <= 52 or trend % 2 == 0:
        raise ValueError("The trend smoother must be an odd integer greater than 52.")
    if not isinstance(robust, (bool, np.bool_)):
        raise ValueError("robust must be True or False.")

    # Fit the additive model to filling fractions, using an approximately annual period.
    result = STL(series, period=52, seasonal=seasonal, trend=trend, robust=robust).fit()
    components = [series, result.trend, result.seasonal, result.resid]
    labels = ["Filling (%)", "Trend (%)", "Seasonal (pp)", "Residual (pp)"]
    fig, axes = plt.subplots(4, 1, figsize=(12, 8), sharex=True)
    for ax, component, label in zip(axes, components, labels):
        # Multiplying by 100 changes fractions to percentages or percentage points.
        ax.plot(series.index, component * 100, color="tab:blue", linewidth=0.9)
        ax.set_ylabel(label)
        ax.grid(alpha=0.2)
    axes[2].axhline(0, color="grey", linewidth=0.6)
    axes[3].axhline(0, color="grey", linewidth=0.6)
    axes[-1].set_xlabel("Observation date")
    fig.suptitle(f"STL decomposition – {series.name or 'reservoir filling'}")
    fig.tight_layout(rect=(0, 0, 1, 0.97))
    return fig


def plot_reservoir_spectrogram(filling_fraction, window_length=156, window_overlap=78):
    """Return a spectrogram figure for a regular weekly filling-fraction series."""
    series = filling_fraction.sort_index()
    if not isinstance(series.index, pd.DatetimeIndex) or len(series) < 4:
        raise ValueError("Use a datetime-indexed series with at least four weekly observations.")
    if not (series.index[1:] - series.index[:-1] == pd.Timedelta(days=7)).all():
        raise ValueError("The series must have consecutive, unique weekly observations.")
    values = series.to_numpy(dtype=float)
    if not np.isfinite(values).all():
        raise ValueError("The series contains missing or invalid values.")
    if not isinstance(window_length, (int, np.integer)) or not 4 <= window_length <= len(values):
        raise ValueError("Window length must be an integer between 4 and the series length.")
    if not isinstance(window_overlap, (int, np.integer)) or not 0 <= window_overlap < window_length:
        raise ValueError("Overlap must be an integer from 0 to window length minus 1.")

    # With one observation per week, frequency is in cycles/week and time in weeks.
    frequencies, times, power = spectrogram(
        values, fs=1, window="hann", nperseg=window_length, noverlap=window_overlap,
        detrend="constant", scaling="density", mode="psd",
    )
    if power.max() == 0:
        raise ValueError("The series has no variation to analyse after removing the window means.")
    # Use relative power and a small floor to avoid log10(0).
    power_db = 10 * np.log10(np.maximum(power / power.max(), 1e-8))
    # Explicit bin edges also give a single complete window a visible width.
    hop = window_length - window_overlap
    time_edges = np.r_[times - hop / 2, times[-1] + hop / 2]
    date_edges = series.index[0] + pd.to_timedelta(time_edges, unit="W")
    frequency_edges = np.r_[frequencies - 0.5 / window_length,
                            frequencies[-1] + 0.5 / window_length] * 52

    fig, ax = plt.subplots(figsize=(12, 4))
    image = ax.pcolormesh(date_edges, frequency_edges, power_db,
                         shading="flat", cmap="viridis", vmin=-80, vmax=0)
    ax.xaxis.set_major_locator(mdates.YearLocator())
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    ax.set(title=f"Reservoir filling spectrogram – {series.name or 'weekly series'}",
           xlabel="Window centre date", ylabel="Frequency (cycles per 52-week year)")
    fig.colorbar(image, ax=ax, label="Power relative to maximum (dB)")
    fig.tight_layout()
    return fig


# Teacher clarification: DCT/SPC should use temperature to calculate SATV.
def plot_temperature_spc(temperature, cutoff_frequency=1/30, n_std=3):
    """Return a figure, summary and outlier table for an hourly temperature series."""
    series = temperature.sort_index()
    if not isinstance(series.index, pd.DatetimeIndex) or len(series) < 3:
        raise ValueError("Use a time series with at least three hourly observations.")
    if not (series.index[1:] - series.index[:-1] == pd.Timedelta(hours=1)).all():
        raise ValueError("The series must have consecutive, unique hours.")
    values = series.to_numpy(dtype=float)
    if not np.isfinite(values).all():
        raise ValueError("The series contains missing or invalid values.")
    if not np.isfinite(cutoff_frequency) or not 0 < cutoff_frequency < 12:
        raise ValueError("The cutoff frequency must be between 0 and 12 cycles per day.")
    if not np.isfinite(n_std) or n_std <= 0:
        raise ValueError("The number of standard deviations must be positive.")

    # DCT-II has frequency k / (2*N*dt), with dt = 1/24 day.
    coefficients = dct(values, type=2, norm="ortho")
    frequencies = np.arange(len(values)) / (2 * len(values) / 24)
    coefficients[frequencies < cutoff_frequency] = 0
    deviations = idct(coefficients, type=2, norm="ortho")
    slow_variation = values - deviations

    # scale="normal" gives MAD × 1.4826 as a robust estimate of the standard deviation.
    median_deviation = np.median(deviations)
    robust_sigma = median_abs_deviation(deviations, scale="normal")
    center = slow_variation + median_deviation
    lower = center - n_std * robust_sigma
    upper = center + n_std * robust_sigma
    outlier_mask = (values < lower) | (values > upper)

    # SATV is used for the limits; plot the original temperature and flagged hours.
    fig, ax = plt.subplots(figsize=(12, 4))
    ax.plot(series.index, values, color="tab:blue", linewidth=0.7, label="Average temperature")
    ax.plot(series.index, lower, color="darkorange", linestyle="--", linewidth=0.9, label="Lower SPC limit")
    ax.plot(series.index, upper, color="darkorange", linestyle="--", linewidth=0.9, label="Upper SPC limit")
    ax.scatter(series.index[outlier_mask], values[outlier_mask],
               color="crimson", s=12, zorder=3, label="Outliers")
    ax.set(title="Outliers in average temperature – DCT/SPC",
           xlabel="Time (UTC)", ylabel="Temperature (°C)")
    ax.legend(loc="upper left", ncol=2)
    ax.grid(alpha=0.2)
    fig.tight_layout()

    summary = {
        "number_of_hours": len(values),
        "number_of_outliers": int(outlier_mask.sum()),
        "percentage": 100 * outlier_mask.mean(),
        "robust_standard_deviation_c": float(robust_sigma),
    }
    outliers = pd.DataFrame({
        "temperature_c": values, "lower_limit_c": lower, "upper_limit_c": upper,
    }, index=series.index).loc[outlier_mask]
    return fig, summary, outliers


def plot_temperature_lof(temperature, outlier_fraction=0.01):
    """Return a figure, summary and anomaly table for an hourly temperature series."""
    series = temperature.sort_index()
    if not isinstance(series.index, pd.DatetimeIndex) or len(series) < 21:
        raise ValueError("LOF with 20 neighbours requires at least 21 hourly observations.")
    if not (series.index[1:] - series.index[:-1] == pd.Timedelta(hours=1)).all():
        raise ValueError("The series must have consecutive, unique hours.")
    values = series.to_numpy(dtype=float)
    if not np.isfinite(values).all():
        raise ValueError("The series contains missing or invalid values.")
    if not np.isfinite(outlier_fraction) or not 0 < outlier_fraction <= 0.5:
        raise ValueError("The anomaly proportion must be greater than 0 and at most 0.5.")

    # Include time and give time and temperature equal standard deviations when calculating distances.
    features = np.column_stack([np.arange(len(values)), values])
    features = StandardScaler().fit_transform(features)
    model = LocalOutlierFactor(n_neighbors=20, contamination=outlier_fraction)
    anomaly_mask = model.fit_predict(features) == -1
    lof_scores = -model.negative_outlier_factor_

    # Plot temperature in °C, with classified anomalies in red.
    fig, ax = plt.subplots(figsize=(12, 4))
    ax.plot(series.index, values, color="tab:blue", linewidth=0.7,
            label="Average temperature")
    ax.scatter(series.index[anomaly_mask], values[anomaly_mask],
               color="crimson", s=18, zorder=3, label="Anomalies")
    ax.set(title=f"Anomalies in average temperature – LOF ({100 * outlier_fraction:g} %)",
           xlabel="Time (UTC)", ylabel="Temperature (°C)")
    ax.legend(loc="upper left")
    ax.grid(alpha=0.2)
    fig.tight_layout()

    summary = {
        "number_of_hours": len(values),
        "number_of_anomalies": int(anomaly_mask.sum()),
        "percentage": 100 * anomaly_mask.mean(),
        "selected_percentage": 100 * outlier_fraction,
    }
    anomalies = pd.DataFrame({
        "temperature_c": values, "lof_score": lof_scores,
    }, index=series.index).loc[anomaly_mask].sort_values("lof_score", ascending=False)
    return fig, summary, anomalies

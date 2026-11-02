"""Weekly reservoir analyses shared by the notebook and Streamlit app."""

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy.signal import spectrogram
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

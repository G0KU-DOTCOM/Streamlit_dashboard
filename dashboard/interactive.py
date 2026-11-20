"""Interactive views of the notebook's existing, tested analysis results.

The reference analysis functions also serve the submitted notebooks. Their
figures contain the calculated curves and heatmap bins; this adapter preserves
those values while replacing the app renderer, without changing the methods.
"""

import matplotlib.dates as mdates
from matplotlib.collections import PathCollection, QuadMesh
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from dashboard.theme import BLUE, style_figure


def analysis_figure(reference):
    axes = reference.axes
    mesh = next((collection for axis in axes for collection in axis.collections
                 if isinstance(collection, QuadMesh)), None)
    if mesh is not None:
        coordinates = mesh.get_coordinates()
        x_edges = coordinates[0, :, 0]
        y_edges = coordinates[:, 0, 1]
        x = mdates.num2date((x_edges[:-1] + x_edges[1:]) / 2)
        y = (y_edges[:-1] + y_edges[1:]) / 2
        figure = go.Figure(go.Heatmap(
            x=x, y=y, z=np.asarray(mesh.get_array()), colorscale="Blues",
            zmin=-80, zmax=0, colorbar=dict(title="Relative<br>power (dB)"),
            hovertemplate="%{x|%d %b %Y}<br>%{y:.2f} cycles/year<br>%{z:.1f} dB<extra></extra>",
        ))
        style_figure(figure, y_title=axes[0].get_ylabel())
        figure.update_xaxes(title="Window centre date")
        return figure

    figure = make_subplots(rows=len(axes), cols=1, shared_xaxes=True,
                           vertical_spacing=.06 if len(axes) > 1 else 0)
    for row, axis in enumerate(axes, start=1):
        for index, line in enumerate(axis.lines):
            x = np.asarray(line.get_xdata())
            # Matplotlib's zero-reference lines use axes fractions, not dates.
            if np.issubdtype(x.dtype, np.number):
                continue
            label = line.get_label()
            label = axis.get_ylabel() if label.startswith("_") else label
            figure.add_trace(go.Scatter(
                x=x, y=np.asarray(line.get_ydata()), mode="lines", name=label,
                line=dict(color=BLUE if index == 0 else "#6885a3",
                          width=1.6 if index == 0 else 1,
                          dash="solid" if index == 0 else "dash"),
                showlegend=len(axes) == 1, connectgaps=False,
            ), row=row, col=1)
        for collection in axis.collections:
            if isinstance(collection, PathCollection):
                points = np.asarray(collection.get_offsets())
                if len(points):
                    figure.add_trace(go.Scatter(
                        x=mdates.num2date(points[:, 0]), y=points[:, 1],
                        mode="markers", name=collection.get_label(),
                        marker=dict(color="#b33e50", size=6, symbol="diamond"),
                    ), row=row, col=1)
        figure.update_yaxes(title=axis.get_ylabel(), row=row, col=1)
    style_figure(figure, height=650 if len(axes) > 1 else 400)
    figure.update_xaxes(title=axes[-1].get_xlabel(), row=len(axes), col=1)
    return figure

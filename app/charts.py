"""Matplotlib drawings of the control charts computed in qc.py.

Drawing only: every number plotted here comes from a qc.py function. Each
function takes the chart table qc.py returned plus the matching flight
numbers, and returns a matplotlib Figure for Shiny's @render.plot.
"""

from __future__ import annotations

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402

SURFACE = "#fcfcfb"
INK, INK_2 = "#0b0b0b", "#52514e"
GRID = "#e4e3df"
SERIES = "#2a78d6"     # categorical slot 1: the charted variable
CRITICAL = "#d03b3b"   # status colour: out-of-control points (always with an X marker)

plt.rcParams.update({
    "font.size": 10, "axes.edgecolor": GRID, "axes.labelcolor": INK_2,
    "xtick.color": INK_2, "ytick.color": INK_2,
    "axes.spines.top": False, "axes.spines.right": False,
})


def _frame(ax, title: str, unit: str, n_baseline: int) -> None:
    ax.set_facecolor(SURFACE)
    ax.grid(axis="y", color=GRID, lw=0.8)
    ax.set_axisbelow(True)
    if n_baseline:
        ax.axvspan(0.5, n_baseline + 0.5, color=GRID, alpha=0.5, lw=0)
        ax.text(0.01, 0.97, f"baseline: first {n_baseline} readings", transform=ax.transAxes,
                va="top", color=INK_2, fontsize=8.5)
    ax.set_title(title, loc="left", color=INK, fontsize=11, fontweight="bold")
    ax.set_ylabel(unit)


def _limits(ax, x, lcl, ucl) -> None:
    for y, name in ((ucl, "UCL"), (lcl, "LCL")):
        ax.plot(x, y, color=INK_2, lw=1.2, ls="--")
        ax.text(x.iloc[-1] + 0.8, y.iloc[-1], name, va="center", color=INK_2, fontsize=8.5)


def _signals(ax, x, y, mask) -> None:
    if not mask.any():
        return
    ax.scatter(x[mask], y[mask], s=44, marker="X", color=CRITICAL, edgecolor=SURFACE,
               linewidth=1, zorder=4)
    first = x[mask].iloc[0]
    ax.annotate(f"first signal: flight {first}", (first, y[mask].iloc[0]), xytext=(-10, 18),
                textcoords="offset points", ha="right", color=CRITICAL, fontsize=9,
                fontweight="bold", arrowprops=dict(arrowstyle="-", color=CRITICAL, lw=1))


def ewma_axes(ax, chart: pd.DataFrame, flight_no: pd.Series, title: str, unit: str) -> None:
    """Draw qc.ewma_chart() output: raw readings as dots, EWMA line, limits, signals."""
    x = pd.Series(flight_no).reset_index(drop=True)
    _frame(ax, title, unit, int(chart["baseline"].sum()))
    ax.scatter(x, chart["value"], s=10, color=INK_2, alpha=0.35, lw=0, label="each flight")
    ax.plot(x, chart["z"], color=SERIES, lw=2, label="EWMA")
    _limits(ax, x, chart["lcl"], chart["ucl"])
    _signals(ax, x, chart["z"], chart["signal"].to_numpy())
    ax.legend(loc="lower left", frameon=False, fontsize=8.5)


def i_axes(ax, chart: pd.DataFrame, flight_no: pd.Series, title: str, unit: str) -> None:
    """Draw the I half of qc.imr_chart() output: readings, limits, signals."""
    x = pd.Series(flight_no).reset_index(drop=True)
    _frame(ax, title, unit, int(chart["baseline"].sum()))
    ax.plot(x, chart["value"], color=SERIES, lw=1.2, marker="o", ms=2.5)
    _limits(ax, x, chart["lcl"], chart["ucl"])
    _signals(ax, x, chart["value"], chart["signal_i"].to_numpy())


def drone_figure(panels: list[tuple[str, pd.DataFrame, pd.Series, str, str]]) -> plt.Figure:
    """Stack several charts for one drone, sharing the flight-number axis.

    panels: (kind, chart, flight_no, title, unit) with kind "ewma" or "i".
    """
    fig, axes = plt.subplots(len(panels), 1, figsize=(10, 3.1 * len(panels)),
                             facecolor=SURFACE, sharex=True)
    for ax, (kind, chart, flight_no, title, unit) in zip(axes, panels):
        (ewma_axes if kind == "ewma" else i_axes)(ax, chart, flight_no, title, unit)
    axes[-1].set_xlabel("flight number")
    fig.tight_layout(h_pad=2)
    return fig

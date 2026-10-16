"""Matplotlib drawings of the control charts computed in qc.py.

Drawing only: every number plotted here comes from a qc.py function. Each
function takes the chart table qc.py returned plus the matching flight
numbers, and returns a matplotlib Figure for Shiny's @render.plot.
"""

from __future__ import annotations

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
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


# ---------------------------------------------------------------- reliability (Stage 4)

PART_TITLE = {"motor": "Motors", "propeller": "Propellers", "battery": "Batteries"}


def reliability_figure(curves: list[dict]) -> plt.Figure:
    """One panel per part type: fitted Weibull R(t), Kaplan-Meier steps, B10 marker.

    curves: dicts with type, unit, t (ages), r (fitted R(t)), km (DataFrame t,
    survival from qc.km_curve), b10, beta, eta.
    """
    fig, axes = plt.subplots(1, len(curves), figsize=(12, 3.8), facecolor=SURFACE)
    for ax, c in zip(np.atleast_1d(axes), curves):
        ax.set_facecolor(SURFACE)
        ax.grid(axis="y", color=GRID, lw=0.8)
        ax.set_axisbelow(True)
        ax.step(c["km"]["t"], c["km"]["survival"], where="post", color=INK_2, lw=1.2, alpha=0.8,
                label="from the data (Kaplan-Meier)")
        ax.plot(c["t"], c["r"], color=SERIES, lw=2.2, label="Weibull fit")
        ax.axvline(c["b10"], color=CRITICAL, lw=1.2, ls="--")
        ax.axhline(0.9, color=GRID, lw=1)
        ax.annotate(f"B10 = {c['b10']:.0f}", (c["b10"], 0.9), xytext=(6, 8), textcoords="offset points",
                    color=CRITICAL, fontsize=9, fontweight="bold")
        ax.set_title(f"{PART_TITLE.get(c['type'], c['type'])}  (β = {c['beta']:.2f}, η = {c['eta']:.0f})",
                     loc="left", color=INK, fontsize=11, fontweight="bold")
        ax.set_xlabel(c["unit"])
        ax.set_ylim(-0.02, 1.04)
        ax.set_xlim(left=0)
    np.atleast_1d(axes)[0].set_ylabel("share still working")
    np.atleast_1d(axes)[0].legend(loc="lower left", frameon=False, fontsize=8.5)
    fig.tight_layout(w_pad=2)
    return fig


def lots_figure(lots: pd.DataFrame, unit: str) -> plt.Figure:
    """Characteristic life (eta) per lot with its 95% interval; a lot whose interval sits
    entirely below another lot's is drawn in red."""
    fitted = lots.dropna(subset=["eta"]).reset_index(drop=True)
    fig, ax = plt.subplots(figsize=(10, 0.9 + 0.75 * max(len(fitted), 1)), facecolor=SURFACE)
    ax.set_facecolor(SURFACE)
    ax.grid(axis="x", color=GRID, lw=0.8)
    ax.set_axisbelow(True)
    best_lo = fitted["eta_lo"].max() if len(fitted) else 0
    for i, r in fitted.iterrows():
        worse = r["eta_hi"] < best_lo
        col = CRITICAL if worse else SERIES
        ax.plot([r["eta_lo"], r["eta_hi"]], [i, i], color=col, lw=3, solid_capstyle="round", alpha=0.45)
        ax.scatter([r["eta"]], [i], s=70, color=col, zorder=3, edgecolor=SURFACE, linewidth=1.5)
        ax.annotate(f"{r['eta']:.0f}  ({r['eta_lo']:.0f}–{r['eta_hi']:.0f})", (r["eta_hi"], i),
                    xytext=(8, -3), textcoords="offset points", color=col if worse else INK_2, fontsize=9.5,
                    fontweight="bold" if worse else "normal")
    ax.set_yticks(range(len(fitted)), [f"Lot {x}" for x in fitted["lot"]])
    ax.invert_yaxis()
    ax.set_xlabel(f"characteristic life η ({unit}), dot = estimate, bar = 95% interval")
    ax.set_xlim(0, fitted["eta_hi"].max() * 1.3 if len(fitted) else 1)
    ax.spines["left"].set_visible(False)
    fig.tight_layout()
    return fig

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
EWMA = "#eb6834"       # categorical slot 2: the EWMA line
VIOLET = "#6250d6"     # categorical slot 7: special causes on the timeline
MUTED = "#9a9890"      # no-fault inspections: present but recessive
WARNING = "#c98500"    # status colour: SPC rules 2-8 and part warnings (diamond / triangle)
CRITICAL = "#d03b3b"   # status colour: rule 1 and in-flight failures (always with an X marker)

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
        ax.text(0.01, 0.97, f"baseline: first {n_baseline} flights", transform=ax.transAxes,
                va="top", color=INK_2, fontsize=8.5)
    ax.set_title(title, loc="left", color=INK, fontsize=11, fontweight="bold")
    ax.set_ylabel(unit)


def monitor_axes(ax, chart: pd.DataFrame, title: str, unit: str, resets: list[int]) -> None:
    """Draw qc.monitor_chart() output: readings, 3-sigma limits, the EWMA and its limits,
    the restarts after each logged action, and every signal."""
    x = chart["flight_no"]
    _frame(ax, title, unit, int(chart["baseline"].sum()))
    for r in resets:
        if r >= x[~chart["baseline"]].min() - 1:
            ax.axvline(r + 0.5, color=GRID, lw=1.1, zorder=0)
    ax.plot(x, chart["value"], color=SERIES, lw=1, marker="o", ms=2.2, alpha=0.85)
    for y, name in ((chart["ucl"], "UCL"), (chart["lcl"], "LCL")):
        ax.plot(x, y, color=INK_2, lw=1.2, ls="--")
        ax.text(1.005, y.iloc[-1], name, va="center", color=INK_2, fontsize=8.5,
                transform=ax.get_yaxis_transform())
    ax.plot(x, chart["z"], color=EWMA, lw=2)
    ax.plot(x, chart["ewma_ucl"], color=EWMA, lw=0.9, ls=":")
    ax.plot(x, chart["ewma_lcl"], color=EWMA, lw=0.9, ls=":")
    r1 = chart["rule_1"].to_numpy()
    other = (chart["rules_triggered"] != "").to_numpy() & ~r1
    ew = chart["signal_ewma"].to_numpy()
    if other.any():
        ax.scatter(x[other], chart["value"][other], s=34, marker="D", color=WARNING, edgecolor=SURFACE,
                   linewidth=0.8, zorder=4)
    if r1.any():
        ax.scatter(x[r1], chart["value"][r1], s=48, marker="X", color=CRITICAL, edgecolor=SURFACE,
                   linewidth=1, zorder=5)
    if ew.any():
        ax.scatter(x[ew], chart["z"][ew], s=46, facecolor="none", edgecolor=EWMA, linewidth=1.6,
                   zorder=5)


MONITOR_LEGEND = [
    plt.Line2D([], [], color=SERIES, lw=1, marker="o", ms=3, label="each flight"),
    plt.Line2D([], [], color=INK_2, lw=1.2, ls="--", label="control limits (±3σ, from the baseline)"),
    plt.Line2D([], [], color=EWMA, lw=2, label="EWMA (and its limits, dotted)"),
    plt.Line2D([], [], ls="", marker="X", color=CRITICAL, ms=8, label="rule 1: beyond 3σ"),
    plt.Line2D([], [], ls="", marker="D", color=WARNING, ms=6, label="rules 2–8: a pattern"),
    plt.Line2D([], [], ls="", marker="o", mfc="none", mec=EWMA, mew=1.6, ms=8, label="EWMA beyond its limit"),
]


def drone_monitor_figure(panels: list[tuple[pd.DataFrame, str, str, list[int]]]) -> plt.Figure:
    """Stack one monitor chart per reading for one drone, sharing the flight axis.

    panels: (chart from qc.monitor_chart, title, unit, reset flights).
    """
    fig, axes = plt.subplots(len(panels), 1, figsize=(11, 3.3 * len(panels)),
                             facecolor=SURFACE, sharex=True)
    for ax, (chart, title, unit, resets) in zip(np.atleast_1d(axes), panels):
        monitor_axes(ax, chart, title, unit, resets)
    np.atleast_1d(axes)[-1].set_xlabel("flight number (thin vertical lines: the technician acted, the chart restarts)")
    fig.tight_layout(h_pad=2, rect=(0, 0, 1, 1 - 0.5 / fig.get_figheight()))
    fig.legend(handles=MONITOR_LEGEND, loc="upper center", ncol=3, frameon=False, fontsize=8.5)
    return fig


# ---------------------------------------------------------------- maintenance timeline (W / R / F / S / N)

#: marker -> (label, colour, matplotlib shape, size). Shape and letter carry the meaning too,
#: so no marker relies on colour alone.
MARKER_STYLE = {
    "W": ("warning", WARNING, "^", 60),
    "R": ("replaced", SERIES, "o", 52),
    "F": ("failed in flight", CRITICAL, "X", 70),
    "S": ("special cause fixed", VIOLET, "D", 50),
    "N": ("inspected, no fault", MUTED, "|", 50),
}
LANES = ([f"motor {i}" for i in range(1, 5)] + [f"propeller {i}" for i in range(1, 5)]
         + [f"battery {i}" for i in range(1, 3)] + ["motor temperature rise", "vibration", "voltage sag"])


def _timeline_axes(ax, rows: list[str], n_flights: int) -> None:
    ax.set_facecolor(SURFACE)
    ax.set_ylim(len(rows) - 0.5, -0.5)
    ax.set_yticks(range(len(rows)), rows)
    ax.set_xlim(0, n_flights + 2)
    ax.grid(axis="x", color=GRID, lw=0.8)
    ax.set_axisbelow(True)
    for i in range(len(rows)):
        ax.axhline(i, color=GRID, lw=0.6, zorder=0)
    ax.spines["left"].set_visible(False)
    ax.tick_params(axis="y", length=0)
    ax.set_xlabel("flight number")


def _legend(ax, markers) -> None:
    handles = [plt.Line2D([], [], ls="", marker=MARKER_STYLE[m][2], color=MARKER_STYLE[m][1],
                          markersize=7, label=f"{m} = {MARKER_STYLE[m][0]}") for m in markers]
    ax.legend(handles=handles, loc="upper left", bbox_to_anchor=(0, -0.16 if len(ax.get_yticks()) < 12 else -0.08),
              ncol=len(handles), frameon=False, fontsize=8.5)


def drone_timeline_figure(tl: pd.DataFrame, n_flights: int, n_baseline: int) -> plt.Figure:
    """One lane per part slot (and per chart for repairs and no-fault inspections), flights
    on the x axis. An amber bar joins each warning to the replacement it led to."""
    rows = [lane for lane in LANES if lane in set(tl["lane"])] or LANES[:10]
    rows = [lane for lane in LANES[:10]] + [lane for lane in LANES[10:] if lane in rows]
    fig, ax = plt.subplots(figsize=(11, 0.36 * len(rows) + 1.3), facecolor=SURFACE)
    _timeline_axes(ax, rows, n_flights)
    ax.axvspan(0, n_baseline + 0.5, color=GRID, alpha=0.4, lw=0)
    y = {lane: i for i, lane in enumerate(rows)}
    for lane, g in tl.groupby("lane"):
        ws = g.loc[g["marker"] == "W", "flight_no"].sort_values().tolist()
        for r in g.loc[g["marker"].isin(["R", "F", "S"]), "flight_no"]:
            before = [w for w in ws if w <= r]
            if before:
                ax.plot([before[-1], r], [y[lane]] * 2, color=WARNING, lw=3, alpha=0.35, solid_capstyle="round")
                ws = [w for w in ws if w > r]
    for m, g in tl.groupby("marker"):
        label, col, shape, size = MARKER_STYLE[m]
        ax.scatter(g["flight_no"], g["lane"].map(y), marker=shape, s=size, color=col,
                   edgecolor=SURFACE if shape not in "|" else None, linewidth=0.8 if shape != "|" else 1.6, zorder=3)
        if m in "RFS":
            for r in g.itertuples():
                ax.text(r.flight_no, y[r.lane] - 0.32, m, ha="center", va="bottom", fontsize=7, color=INK_2)
    _legend(ax, [m for m in MARKER_STYLE if m in set(tl["marker"])])
    fig.tight_layout()
    return fig


def fleet_timeline_figure(tl: pd.DataFrame, drones: list[str], n_flights: int) -> plt.Figure:
    """Every drone on one row: when parts were warned, replaced, failed, or a special cause fixed."""
    fig, ax = plt.subplots(figsize=(12, 0.42 * len(drones) + 1.2), facecolor=SURFACE)
    _timeline_axes(ax, drones, n_flights)
    y = {d: i for i, d in enumerate(drones)}
    for m in ["N", "W", "R", "S", "F"]:
        g = tl[(tl["marker"] == m) & tl["drone_id"].isin(y)]
        if g.empty:
            continue
        label, col, shape, size = MARKER_STYLE[m]
        offset = {"N": 0.28, "W": -0.18, "R": 0.0, "S": 0.0, "F": 0.0}[m]
        ax.scatter(g["flight_no"], g["drone_id"].map(y) + offset, marker=shape, s=size * 0.8, color=col,
                   alpha=0.45 if m == "N" else 1, edgecolor=SURFACE if shape != "|" else None,
                   linewidth=0.7 if shape != "|" else 1.2, zorder=3 if m != "F" else 4)
    _legend(ax, [m for m in MARKER_STYLE if m in set(tl["marker"])])
    fig.tight_layout()
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

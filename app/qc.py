"""Quality-control statistics for the drone fleet reliability tool.

Every function here is plain Python with plain inputs (a list, numpy array or
pandas Series of numbers, or the flights table) and plain outputs (numbers in a
NamedTuple or a DataFrame). Nothing here plots or knows about Shiny: the app
only calls these functions and displays what they return. Formulas follow
SPEC.md section 4; the hand-worked known answers are in tests/test_qc.py.

Control charts in this module
-----------------------------
I-MR chart (individuals + moving range), for sudden damage
    Baseline = the first `n_baseline` points (default 30 flights), which must be
    in control. MR_i = |x_i - x_(i-1)|, MRbar = mean of the baseline MRs.
    sigma_hat = MRbar / d2, with d2 = 1.128 (moving range of 2 points).
    I chart:  center = baseline mean, limits = center +/- 3 * sigma_hat.
    MR chart: UCL = D4 * MRbar with D4 = 3.267, LCL = 0.
    Signal = a point beyond a limit (Western Electric rule 1 only).

EWMA chart (exponentially weighted moving average), for slow wear
    z_0 = mu0 (the baseline mean), z_t = lam * x_t + (1 - lam) * z_(t-1).
    Limits: mu0 +/- L * sigma * sqrt(lam / (2 - lam) * (1 - (1 - lam)^(2t))),
    which widen over the first few points and settle at
    mu0 +/- L * sigma * sqrt(lam / (2 - lam)).
    Defaults lam = 0.2, L = 3; sigma = the I-MR sigma_hat of the baseline.
    Signal = z_t beyond a limit.
"""

from __future__ import annotations

import math
from typing import Iterable, NamedTuple

import numpy as np
import pandas as pd

#: Bias-correction constant d2 for a moving range of span 2.
D2_N2 = 1.128
#: Upper-limit constant D4 for a moving range of span 2.
D4_N2 = 3.267
#: Default baseline (Phase I) length, in flights. Team decision, docs/plan.md.
N_BASELINE = 30
#: Fewest baseline points we accept before refusing to draw limits.
MIN_BASELINE = 20


class ImrLimits(NamedTuple):
    """Limits for an I-MR chart, all in the units of the charted variable.

    Use ``limits._asdict()`` to turn it into a dict.
    """

    center: float      # baseline mean
    lcl: float         # center - 3 * sigma_hat
    ucl: float         # center + 3 * sigma_hat
    sigma_hat: float   # MRbar / 1.128
    mr_bar: float      # mean baseline moving range
    mr_ucl: float      # 3.267 * MRbar (MR chart LCL is 0)
    n_baseline: int    # points actually used as the baseline


def _clean(values: Iterable[float], minimum: int) -> np.ndarray:
    """Convert to a float array and refuse bad input loudly."""
    try:
        xs = np.asarray([float(v) for v in values], dtype=float)
    except (TypeError, ValueError) as err:
        raise ValueError(f"values must all be numbers: {err}") from None
    if len(xs) < minimum:
        raise ValueError(f"need at least {minimum} values, got {len(xs)}")
    if not np.all(np.isfinite(xs)):
        raise ValueError("values must be finite (no blanks, NaN or infinity); "
                         "drop missing readings first, e.g. with drone_series()")
    return xs


def imr_limits(values: Iterable[float], n_baseline: int = N_BASELINE,
               min_baseline: int = MIN_BASELINE) -> ImrLimits:
    """Estimate I-MR control limits from the first `n_baseline` values.

    Points after the baseline never move the limits; that is what lets the
    chart detect them. If fewer than `n_baseline` values exist, all are used,
    as long as there are at least `min_baseline`.

    Raises ValueError for blanks or non-numbers, fewer than `min_baseline`
    baseline points (and always fewer than 2), or a baseline with no
    variation (every moving range 0), where limits would be meaningless.
    """
    xs = _clean(values, minimum=2)
    base = xs[:n_baseline]
    if len(base) < max(min_baseline, 2):
        raise ValueError(f"need at least {max(min_baseline, 2)} baseline points to "
                         f"estimate limits, got {len(base)}")
    mr_bar = float(np.mean(np.abs(np.diff(base))))
    if mr_bar == 0:
        raise ValueError("baseline has no variation (every moving range is 0); "
                         "control limits are undefined")
    center = float(np.mean(base))
    sigma_hat = mr_bar / D2_N2
    return ImrLimits(center=center, lcl=center - 3 * sigma_hat, ucl=center + 3 * sigma_hat,
                     sigma_hat=sigma_hat, mr_bar=mr_bar, mr_ucl=D4_N2 * mr_bar,
                     n_baseline=len(base))


def imr_chart(values: Iterable[float], n_baseline: int = N_BASELINE,
              min_baseline: int = MIN_BASELINE) -> pd.DataFrame:
    """Compute an I-MR chart: one row per point.

    Columns: t (1, 2, ...), value, mr (blank for t = 1), center, lcl, ucl,
    mr_ucl, baseline (True for the points the limits came from),
    signal_i (value beyond lcl/ucl), signal_mr (mr above mr_ucl).
    """
    xs = _clean(values, minimum=2)
    lim = imr_limits(xs, n_baseline, min_baseline)
    mr = np.r_[np.nan, np.abs(np.diff(xs))]
    t = np.arange(1, len(xs) + 1)
    return pd.DataFrame({
        "t": t,
        "value": xs,
        "mr": mr,
        "center": lim.center,
        "lcl": lim.lcl,
        "ucl": lim.ucl,
        "mr_ucl": lim.mr_ucl,
        "baseline": t <= lim.n_baseline,
        "signal_i": (xs > lim.ucl) | (xs < lim.lcl),
        "signal_mr": np.nan_to_num(mr, nan=0.0) > lim.mr_ucl,
    })


def ewma_chart(values: Iterable[float], lam: float = 0.2, L: float = 3.0,
               mu0: float | None = None, sigma: float | None = None,
               n_baseline: int = N_BASELINE, min_baseline: int = MIN_BASELINE) -> pd.DataFrame:
    """Compute an EWMA chart: one row per point.

    lam   weight on the newest point, 0 < lam <= 1 (0.2 = sensitive to small drifts)
    L     limit width in sigmas of the EWMA statistic, > 0
    mu0, sigma
          the in-control mean and standard deviation. Leave them out (the
          normal case) and they are estimated from the first `n_baseline`
          points exactly as in imr_limits(); pass them to chart against a known
          standard, as in a textbook example.

    Columns: t, value, z (the EWMA), center (mu0), lcl, ucl, baseline, signal.
    """
    if not 0 < lam <= 1:
        raise ValueError(f"lam must be in (0, 1], got {lam}")
    if not L > 0:
        raise ValueError(f"L must be positive, got {L}")
    xs = _clean(values, minimum=1)
    n_base = 0
    if mu0 is None or sigma is None:
        lim = imr_limits(xs, n_baseline, min_baseline)
        mu0 = lim.center if mu0 is None else mu0
        sigma = lim.sigma_hat if sigma is None else sigma
        n_base = lim.n_baseline
    if not (math.isfinite(mu0) and math.isfinite(sigma) and sigma > 0):
        raise ValueError(f"need a finite mu0 and a positive sigma, got {mu0}, {sigma}")

    z = np.empty(len(xs))
    prev = mu0
    for i, x in enumerate(xs):
        prev = lam * x + (1 - lam) * prev
        z[i] = prev
    t = np.arange(1, len(xs) + 1)
    half = L * sigma * np.sqrt(lam / (2 - lam) * (1 - (1 - lam) ** (2 * t)))
    return pd.DataFrame({
        "t": t,
        "value": xs,
        "z": z,
        "center": mu0,
        "lcl": mu0 - half,
        "ucl": mu0 + half,
        "baseline": t <= n_base,
        "signal": (z > mu0 + half) | (z < mu0 - half),
    })


# --------------------------------------------------------------------------
# Working with the flights table (columns described in data/README.md)
# --------------------------------------------------------------------------

def add_derived(flights: pd.DataFrame) -> pd.DataFrame:
    """Return a copy of the flights table with the two derived columns.

    temp_rise_c        = motor_temp_max_c - ambient_temp_c         (deg C)
    sag_rate_v_per_min = (voltage_start_v - voltage_end_v) / flight_min   (V/min)

    A blank input reading gives a blank derived value.
    """
    out = flights.copy()
    out["temp_rise_c"] = out["motor_temp_max_c"] - out["ambient_temp_c"]
    out["sag_rate_v_per_min"] = (out["voltage_start_v"] - out["voltage_end_v"]) / out["flight_min"]
    return out


def drone_series(flights: pd.DataFrame, drone_id: str, column: str) -> pd.DataFrame:
    """One drone's readings of one column, in flight order, blanks dropped.

    Returns columns flight_id, flight_no (the sequence number in flight_id,
    e.g. 74 for F-07-074), datetime and value; row i is chart point t = i + 1.
    Raises ValueError if the drone has no flights or the column is missing.
    """
    if column not in flights.columns:
        raise ValueError(f"flights table has no column {column!r}; "
                         "derived columns come from add_derived()")
    d = flights[flights["drone_id"] == drone_id]
    if d.empty:
        raise ValueError(f"no flights for drone {drone_id!r}")
    d = d.sort_values("datetime").dropna(subset=[column])
    return pd.DataFrame({
        "flight_id": d["flight_id"].to_numpy(),
        "flight_no": d["flight_id"].str.rsplit("-", n=1).str[-1].astype(int).to_numpy(),
        "datetime": d["datetime"].to_numpy(),
        "value": d[column].to_numpy(dtype=float),
    })

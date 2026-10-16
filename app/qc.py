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


# --------------------------------------------------------------------------
# Fleet status: go / watch / ground for every drone (SPEC.md section 4)
# --------------------------------------------------------------------------

#: (column, plain name, units, also gets an EWMA chart?)
MONITORED = (
    ("temp_rise_c", "motor temperature rise", "°C", True),
    ("vibration_rms", "vibration", "m/s²", False),
    ("sag_rate_v_per_min", "voltage sag", "V/min", False),
)
#: How many of a drone's latest readings count as "recent" for a watch.
RECENT_FLIGHTS = 10


def chart_margin(value: float, center: float, lcl: float, ucl: float) -> float:
    """Room left before the nearest control limit, as a fraction from 1 to 0.

    1.0 = the reading sits on the center line; 0.5 = halfway to the limit on
    its side; 0.0 = on or beyond the limit (never negative). This is what the
    dashboard's health bar shows.
    """
    if not (ucl > center > lcl):
        raise ValueError(f"limits must satisfy lcl < center < ucl, got {lcl}, {center}, {ucl}")
    room = (ucl - value) / (ucl - center) if value >= center else (value - lcl) / (center - lcl)
    return float(min(1.0, max(0.0, room)))


def _run_start(signal: pd.Series, flight_no: pd.Series) -> int:
    """Flight number where the current unbroken run of signals began."""
    flags = signal.to_numpy()
    k = len(flags) - 1
    while k > 0 and flags[k - 1]:
        k -= 1
    return int(flight_no.iloc[k])


def fleet_status(flights: pd.DataFrame, recent: int = RECENT_FLIGHTS,
                 n_baseline: int = N_BASELINE, min_baseline: int = MIN_BASELINE) -> pd.DataFrame:
    """Decide go / watch / ground for every drone in the flights table.

    For each drone it runs an I chart on temperature rise, vibration and
    voltage sag, plus an EWMA chart on temperature rise (limits from that
    drone's own first `n_baseline` readings), then applies:

      ground  the drone's latest flight was a crash, OR its latest reading is
              outside an I-chart limit, OR its EWMA is outside its limit now
      watch   no ground reason, but a chart signalled within the last
              `recent` readings
      go      every chart in control over the last `recent` readings
      not enough data
              fewer than `min_baseline` readings (or no variation), so no
              limits can be drawn

    Returns one row per drone: drone_id, status, reason (plain English, every
    reason joined by "; "), last_flight_no, n_flights, health and
    health_driver. health = chart_margin() of the latest point on the drone's
    most-stretched chart (1 = at its normal, 0 = at a limit or crashed);
    health_driver names that chart.
    """
    f = flights if "temp_rise_c" in flights.columns else add_derived(flights)
    rows = []
    for drone in sorted(f["drone_id"].unique()):
        d = f[f["drone_id"] == drone].sort_values("datetime")
        last_no = int(d["flight_id"].iloc[-1].rsplit("-", 1)[-1])
        ground, watch, margins = [], [], {}
        crashed = "inflight_event" in d.columns and d["inflight_event"].iloc[-1] == "crash"
        if crashed:
            ground.append(f"crashed on flight {last_no}")
        try:
            for col, name, unit, with_ewma in MONITORED:
                s = drone_series(f, drone, col)
                im = imr_chart(s["value"], n_baseline, min_baseline)
                r = im.iloc[-1]
                margins[name] = chart_margin(r.value, r.center, r.lcl, r.ucl)
                if im["signal_i"].iloc[-1]:
                    r = im.iloc[-1]
                    ground.append(f"{name} {r.value:.2f} {unit} on flight {s.flight_no.iloc[-1]} is outside "
                                  f"its I-chart limits ({r.lcl:.2f} to {r.ucl:.2f})")
                else:
                    hit = s.loc[im["signal_i"].to_numpy(), "flight_no"]
                    hit = hit[hit.index >= len(s) - recent]
                    if len(hit):
                        watch.append(f"{name} was outside its I-chart limits on flight "
                                     f"{', '.join(map(str, hit))}")
                if with_ewma:
                    ew = ewma_chart(s["value"], n_baseline=n_baseline, min_baseline=min_baseline)
                    e = ew.iloc[-1]
                    margins[f"{name} (EWMA)"] = chart_margin(e.z, e.center, e.lcl, e.ucl)
                    if ew["signal"].iloc[-1]:
                        side = "above its upper" if ew["z"].iloc[-1] > ew["center"].iloc[-1] else "below its lower"
                        start = _run_start(ew["signal"], s["flight_no"])
                        first = int(s.loc[ew["signal"].to_numpy(), "flight_no"].iloc[0])
                        note = f" (first crossed on flight {first})" if first != start else ""
                        ground.append(f"{name} EWMA {side} limit since flight {start}{note}")
                    else:
                        hit = s.loc[ew["signal"].to_numpy(), "flight_no"]
                        hit = hit[hit.index >= len(s) - recent]
                        if len(hit):
                            watch.append(f"{name} EWMA signalled on flight {', '.join(map(str, hit))}, now back inside")
        except ValueError as err:
            rows.append(dict(drone_id=drone, status="not enough data", reason=str(err),
                             last_flight_no=last_no, n_flights=len(d),
                             health=float("nan"), health_driver=""))
            continue
        status = "ground" if ground else "watch" if watch else "go"
        reason = "; ".join(ground or watch) or f"all charts in control over the last {recent} flights"
        driver = min(margins, key=margins.get)
        health = 0.0 if crashed else margins[driver]
        rows.append(dict(drone_id=drone, status=status, reason=reason,
                         last_flight_no=last_no, n_flights=len(d),
                         health=health, health_driver="crash" if crashed else driver))
    return pd.DataFrame(rows)


#: Columns fleet_status() and the charts need in an uploaded flights table.
REQUIRED_FLIGHT_COLUMNS = ("flight_id", "drone_id", "datetime", "flight_min", "ambient_temp_c",
                           "voltage_start_v", "voltage_end_v", "motor_temp_max_c", "vibration_rms")


def check_flights(flights: pd.DataFrame) -> pd.DataFrame:
    """Refuse a flights table the tool cannot chart, with a message a technician can act on.

    Checks the required columns are present and numeric where they must be, and
    that every flight_id ends in its sequence number (F-<drone>-<number>).
    Returns the table unchanged when it passes.
    """
    missing = [c for c in REQUIRED_FLIGHT_COLUMNS if c not in flights.columns]
    if missing:
        raise ValueError(f"the flights file is missing column(s): {', '.join(missing)} "
                         "(see data/README.md for the expected columns)")
    for c in ("flight_min", "ambient_temp_c", "voltage_start_v", "voltage_end_v",
              "motor_temp_max_c", "vibration_rms"):
        if not pd.api.types.is_numeric_dtype(flights[c]):
            raise ValueError(f"column {c!r} must hold numbers only (blank cells are fine)")
    if not flights["flight_id"].astype(str).str.match(r"^.+-\d+$").all():
        raise ValueError("every flight_id must end in its flight number, e.g. F-07-074")
    return flights


# --------------------------------------------------------------------------
# Reliability: Weibull life with right-censoring (SPEC.md section 4)
# --------------------------------------------------------------------------
#
# Two-parameter Weibull: R(t) = exp(-(t/eta)^beta), the chance a part is still
# working at age t. beta (shape) > 1 means wear-out (the failure risk rises
# with age); eta (scale) is the age by which 63.2% have failed.
# B10 = eta * (-ln 0.9)^(1/beta): the age by which 10% have failed, used as the
# recommended replacement age.
# Fitted by maximum likelihood with right-censoring (lifelines.WeibullFitter):
# a part with status 0 (still flying, or removed before it failed) counts as
# "lasted at least this long" instead of being thrown away.

#: Usage unit of life_value for each component type (data/README.md).
LIFE_UNIT = {"motor": "flight hours", "propeller": "flight hours", "battery": "charge cycles"}
#: Fewest failures we accept before fitting a Weibull.
MIN_FAILURES = 3


class WeibullFit(NamedTuple):
    """A fitted Weibull life model; _lo/_hi are 95% confidence limits."""

    beta: float
    beta_lo: float
    beta_hi: float
    eta: float
    eta_lo: float
    eta_hi: float
    b10: float       # age by which 10% have failed
    mean_life: float  # eta * Gamma(1 + 1/beta), the mean time to failure
    n: int
    n_failed: int


def b_life(beta: float, eta: float, p: float = 0.10) -> float:
    """Age by which a fraction p of parts have failed: eta * (-ln(1 - p))^(1/beta)."""
    if not (beta > 0 and eta > 0 and 0 < p < 1):
        raise ValueError("need beta > 0, eta > 0 and 0 < p < 1")
    return eta * (-math.log(1 - p)) ** (1 / beta)


def reliability(t, beta: float, eta: float):
    """Chance a part is still working at age t: exp(-(t/eta)^beta). Works on arrays too."""
    return np.exp(-(np.asarray(t, dtype=float) / eta) ** beta)


def weibull_fit(life: Iterable[float], status: Iterable[int],
                min_failures: int = MIN_FAILURES) -> WeibullFit:
    """Fit a 2-parameter Weibull by maximum likelihood with right-censoring.

    life    usage until failure or removal (flight hours or charge cycles), > 0
    status  1 = failed at that age, 0 = censored (survived at least that long)

    Raises ValueError for non-positive or missing lives, statuses other than
    0/1, mismatched lengths, or fewer than `min_failures` failures (too little
    information to estimate a shape).
    """
    from lifelines import WeibullFitter  # imported here so the control charts don't need it

    t = _clean(life, minimum=2)
    try:
        e = np.asarray([int(v) for v in status])
    except (TypeError, ValueError) as err:
        raise ValueError(f"status must be 0 or 1: {err}") from None
    if len(e) != len(t):
        raise ValueError(f"life and status have different lengths ({len(t)} vs {len(e)})")
    if not np.isin(e, (0, 1)).all():
        raise ValueError("status must be 0 (censored) or 1 (failed)")
    if (t <= 0).any():
        raise ValueError("every life must be greater than 0")
    n_failed = int(e.sum())
    if n_failed < min_failures:
        raise ValueError(f"need at least {min_failures} failures to fit a Weibull, got {n_failed} "
                         f"(the other {len(t) - n_failed} parts haven't failed yet)")
    import warnings
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        wf = WeibullFitter().fit(t, e)
    ci = wf.summary
    beta, eta = float(wf.rho_), float(wf.lambda_)
    return WeibullFit(
        beta=beta, beta_lo=float(ci.loc["rho_", "coef lower 95%"]),
        beta_hi=float(ci.loc["rho_", "coef upper 95%"]),
        eta=eta, eta_lo=float(ci.loc["lambda_", "coef lower 95%"]),
        eta_hi=float(ci.loc["lambda_", "coef upper 95%"]),
        b10=b_life(beta, eta), mean_life=eta * math.gamma(1 + 1 / beta),
        n=len(t), n_failed=n_failed)


def _fit_rows(groups, label: str) -> pd.DataFrame:
    rows = []
    for key, g in groups:
        row = {label: key}
        try:
            row.update(weibull_fit(g["life_value"], g["status"])._asdict())
            row["note"] = ""
        except ValueError as err:
            row.update(n=len(g), n_failed=int(g["status"].sum()), note=str(err))
        rows.append(row)
    return pd.DataFrame(rows)


def fit_by_type(components: pd.DataFrame) -> pd.DataFrame:
    """One Weibull fit per component type, with its life unit.

    Returns component_type, unit, beta (+ _lo/_hi), eta (+ _lo/_hi), b10,
    mean_life, n, n_failed and note (why a fit was skipped, if it was).
    """
    out = _fit_rows(components.groupby("component_type"), "component_type")
    out.insert(1, "unit", out["component_type"].map(LIFE_UNIT))
    return out


def compare_lots(components: pd.DataFrame, component_type: str = "battery") -> pd.DataFrame:
    """One Weibull fit per supplier lot of one component type.

    A lot with fewer than MIN_FAILURES failures gets blank estimates and a note.
    Lots whose eta intervals don't overlap differ by more than chance.
    """
    c = components[components["component_type"] == component_type]
    if c.empty:
        raise ValueError(f"no {component_type} rows in the components table")
    return _fit_rows(c.groupby("lot"), "lot").sort_values("lot").reset_index(drop=True)


def parts_past_b10(components: pd.DataFrame, by_type: pd.DataFrame) -> pd.DataFrame:
    """Parts still in service that are older than their type's B10 life.

    These are the ones to replace at the next maintenance slot. Adds
    b10 and pct_of_b10 (age as a % of B10), oldest first.
    """
    b10 = by_type.dropna(subset=["b10"]).set_index("component_type")["b10"]
    live = components[components["end_date"].isna()].copy()
    live["b10"] = live["component_type"].map(b10)
    due = live[live["life_value"] > live["b10"]].copy()
    due["pct_of_b10"] = 100 * due["life_value"] / due["b10"]
    return due.sort_values("pct_of_b10", ascending=False).reset_index(drop=True)


def km_curve(life: Iterable[float], status: Iterable[int]) -> pd.DataFrame:
    """Kaplan-Meier estimate of survival straight from the data (no model).

    At each failure age t: S(t) = S(previous) * (1 - failures at t / parts still at risk at t).
    Censored parts leave the risk set without a step. Plotted next to the fitted
    Weibull R(t) as a check that the Weibull model fits. Returns columns t, survival,
    starting at t = 0, survival = 1.
    """
    t = _clean(life, minimum=1)
    e = np.asarray([int(v) for v in status])
    if len(e) != len(t):
        raise ValueError("life and status have different lengths")
    order = np.argsort(t, kind="stable")
    t, e = t[order], e[order]
    times, surv, s = [0.0], [1.0], 1.0
    at_risk = len(t)
    for u in np.unique(t):
        here = t == u
        d = int(e[here].sum())
        if d:
            s *= 1 - d / at_risk
            times.append(float(u))
            surv.append(s)
        at_risk -= int(here.sum())
    return pd.DataFrame({"t": times, "survival": surv})


#: Columns the reliability tab needs in an uploaded components table.
REQUIRED_COMPONENT_COLUMNS = ("component_id", "drone_id", "component_type", "lot",
                              "end_date", "life_value", "status")


def check_components(components: pd.DataFrame) -> pd.DataFrame:
    """Refuse a components table the reliability tab cannot use, with a clear message."""
    missing = [c for c in REQUIRED_COMPONENT_COLUMNS if c not in components.columns]
    if missing:
        raise ValueError(f"the components file is missing column(s): {', '.join(missing)} "
                         "(see data/README.md for the expected columns)")
    if not pd.api.types.is_numeric_dtype(components["life_value"]):
        raise ValueError("column 'life_value' must hold numbers only")
    if not components["status"].isin([0, 1]).all():
        raise ValueError("column 'status' must be 1 (failed) or 0 (still working / removed early)")
    return components

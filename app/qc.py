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
    Signals = the 8 Nelson / Western Electric rules (spc_rules); rule 1 is a
    point beyond a limit.

EWMA chart (exponentially weighted moving average), for slow wear
    z_0 = mu0 (the baseline mean), z_t = lam * x_t + (1 - lam) * z_(t-1).
    Limits: mu0 +/- L * sigma * sqrt(lam / (2 - lam) * (1 - (1 - lam)^(2t))),
    which widen over the first few points and settle at
    mu0 +/- L * sigma * sqrt(lam / (2 - lam)).
    Defaults lam = 0.2, L = 3; sigma = the I-MR sigma_hat of the baseline.
    Signal = z_t beyond a limit.

monitor_chart() runs both on one drone's reading and restarts them after each
logged repair or replacement (the EWMA at the center, the run rules afresh),
keeping the baseline limits.
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
#: Default baseline (Phase I) length, in flights. Team decision, docs/plan.md: 50 since the
#: 300-flight fleet (30 gave limits whose sigma ranged 0.6x to 1.4x the true value).
N_BASELINE = 50
#: Fewest baseline points we accept before refusing to draw limits.
MIN_BASELINE = 20

#: The 8 Nelson / Western Electric statistical process control (SPC) rules.
#: Rule 1 flags an immediate 3-sigma excursion (ground); Rules 2-8 flag non-random
#: patterns, sustained shifts, and trends (watch / warning).
SPC_RULES: dict[int, str] = {
    1: "1 point beyond 3σ",
    2: "9 points in a row on the same side of the center line",
    3: "6 points in a row steadily increasing or decreasing",
    4: "14 points in a row alternating up and down",
    5: "2 of 3 points beyond 2σ on the same side",
    6: "4 of 5 points beyond 1σ on the same side",
    7: "15 points in a row within 1σ of the center line",
    8: "8 points in a row beyond 1σ on either side",
}


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


def spc_rules(values: Iterable[float], center: float, sigma: float) -> pd.DataFrame:
    """Evaluate the 8 Nelson / Western Electric SPC tests at every point.

    Returns a DataFrame with boolean columns ``rule_1`` .. ``rule_8``, plus:
      - ``signal_ground``: ``rule_1`` (a point beyond 3 sigma)
      - ``signal_watch``: any of ``rule_2`` .. ``rule_8`` (non-random run/trend/zone pattern)
      - ``signal_any``: any of ``rule_1`` .. ``rule_8``
      - ``rules_triggered``: comma-separated rule numbers triggered at each point (e.g. ``"1, 5"``)
    """
    xs = _clean(values, minimum=1)
    if not (math.isfinite(center) and math.isfinite(sigma) and sigma > 0):
        raise ValueError(f"need a finite center and a positive sigma, got {center}, {sigma}")
    z = (xs - center) / sigma
    n = len(xs)
    r1 = np.abs(z) > 3.0
    r2 = np.zeros(n, dtype=bool)
    r3 = np.zeros(n, dtype=bool)
    r4 = np.zeros(n, dtype=bool)
    r5 = np.zeros(n, dtype=bool)
    r6 = np.zeros(n, dtype=bool)
    r7 = np.zeros(n, dtype=bool)
    r8 = np.zeros(n, dtype=bool)

    for i in range(n):
        if i >= 8:
            w = z[i - 8:i + 1]
            if np.all(w > 0) or np.all(w < 0):
                r2[i] = True
        if i >= 5:
            d = np.diff(xs[i - 5:i + 1])
            if np.all(d > 0) or np.all(d < 0):
                r3[i] = True
        if i >= 13:
            d = np.diff(xs[i - 13:i + 1])
            if np.all(d != 0) and np.all(np.sign(d[:-1]) == -np.sign(d[1:])):
                r4[i] = True
        if i >= 1:
            w = z[max(0, i - 2):i + 1]
            if (np.sum(w > 2.0) >= 2 and z[i] > 2.0) or (np.sum(w < -2.0) >= 2 and z[i] < -2.0):
                r5[i] = True
        if i >= 3:
            w = z[max(0, i - 4):i + 1]
            if (np.sum(w > 1.0) >= 4 and z[i] > 1.0) or (np.sum(w < -1.0) >= 4 and z[i] < -1.0):
                r6[i] = True
        if i >= 14:
            w = z[i - 14:i + 1]
            if np.all(np.abs(w) < 1.0):
                r7[i] = True
        if i >= 7:
            w = z[i - 7:i + 1]
            if np.all(np.abs(w) > 1.0) and np.any(w > 1.0) and np.any(w < -1.0):
                r8[i] = True

    cols = {"rule_1": r1, "rule_2": r2, "rule_3": r3, "rule_4": r4,
            "rule_5": r5, "rule_6": r6, "rule_7": r7, "rule_8": r8}
    watch = r2 | r3 | r4 | r5 | r6 | r7 | r8
    triggered = [
        ", ".join(str(k) for k in range(1, 9) if cols[f"rule_{k}"][i])
        for i in range(n)
    ]
    return pd.DataFrame({
        **cols,
        "signal_ground": r1,
        "signal_watch": watch,
        "signal_any": r1 | watch,
        "rules_triggered": triggered,
    })


def imr_chart(values: Iterable[float], n_baseline: int = N_BASELINE,
              min_baseline: int = MIN_BASELINE) -> pd.DataFrame:
    """Compute an I-MR chart with all 8 SPC tests: one row per point.

    Columns: t (1, 2, ...), value, mr (blank for t = 1), center, lcl, ucl,
    mr_ucl, baseline (True for the points the limits came from),
    signal_i (Rule 1: value beyond lcl/ucl), signal_mr (mr above mr_ucl),
    rule_1 .. rule_8, signal_ground, signal_watch, signal_any, rules_triggered.
    """
    xs = _clean(values, minimum=2)
    lim = imr_limits(xs, n_baseline, min_baseline)
    mr = np.r_[np.nan, np.abs(np.diff(xs))]
    t = np.arange(1, len(xs) + 1)
    rules = spc_rules(xs, lim.center, lim.sigma_hat)
    base = pd.DataFrame({
        "t": t,
        "value": xs,
        "mr": mr,
        "center": lim.center,
        "lcl": lim.lcl,
        "ucl": lim.ucl,
        "mr_ucl": lim.mr_ucl,
        "baseline": t <= lim.n_baseline,
        "signal_i": rules["rule_1"],
        "signal_mr": np.nan_to_num(mr, nan=0.0) > lim.mr_ucl,
    })
    return pd.concat([base, rules], axis=1)


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
# Monitoring with repairs: charts that restart after the technician acts
# --------------------------------------------------------------------------

#: (column, plain name, units). Every reading gets both charts: an EWMA for slow wear and an
#: I chart with all 8 rules for sudden changes. Which part pushes each reading up:
MONITORED = (
    ("temp_rise_c", "motor temperature rise", "°C"),
    ("vibration_rms", "vibration", "m/s²"),
    ("sag_rate_v_per_min", "voltage sag", "V/min"),
)
#: The reading each part type pushes up as it wears (data/README.md).
PART_CHART = {"motor": "temp_rise_c", "propeller": "vibration_rms", "battery": "sag_rate_v_per_min"}
#: How many of a drone's latest readings count as "recent" for a watch.
RECENT_FLIGHTS = 10
#: Warn this many flights before a part reaches its replace-at age (B10).
WARN_FLIGHTS = 10


def flight_numbers(flight_ids: pd.Series) -> pd.Series:
    """The sequence number at the end of each flight_id, e.g. 74 for F-07-074."""
    return flight_ids.astype(str).str.rsplit("-", n=1).str[-1].astype(int)


def reset_flights(maintenance: pd.DataFrame | None, drone_id: str, column: str) -> list[int]:
    """Flights after which the technician acted on this drone's `column` chart, in order.

    Any logged replacement of a part that drives the reading, any repair, and any
    inspection of that chart counts. With no maintenance log there are no resets.
    """
    if maintenance is None or maintenance.empty:
        return []
    m = maintenance[(maintenance["drone_id"] == drone_id) & (maintenance["chart"] == column)]
    return sorted(set(flight_numbers(m["flight_id"]).tolist()))


def monitor_chart(values: Iterable[float], flight_no: Iterable[int], resets: Iterable[int] = (),
                  n_baseline: int = N_BASELINE, min_baseline: int = MIN_BASELINE,
                  lam: float = 0.2, L: float = 3.0) -> pd.DataFrame:
    """I chart (all 8 rules) and EWMA on one drone's reading, restarting after each repair.

    values, flight_no
        the readings in flight order and their flight numbers (drone_series() gives both)
    resets
        flight numbers after which a part was replaced, repaired or inspected
        (reset_flights() reads them from maintenance.csv)

    Limits come from the first `n_baseline` readings, exactly as imr_limits(), and are
    kept: a repaired drone is back on its baseline process. Readings after the
    baseline are split into segments: one starts after the baseline and after every
    reset flight. In each segment the EWMA starts again at the center line (z_0 = mu0)
    and the run rules look only at that segment's own points, so a run never spans a
    repair. Baseline rows carry no signals.

    Columns: t, flight_no, value, center, lcl, ucl, sigma, baseline, segment (0 for the
    baseline, then 1, 2, ...), z, ewma_lcl, ewma_ucl, signal_ewma, rule_1 .. rule_8,
    rules_triggered, signal (EWMA or any rule) and what (e.g. "EWMA; rule 1, 5").
    """
    xs = _clean(values, minimum=2)
    fn = np.asarray(list(flight_no), dtype=int)
    if len(fn) != len(xs):
        raise ValueError(f"values and flight_no have different lengths ({len(xs)} vs {len(fn)})")
    lim = imr_limits(xs, n_baseline, min_baseline)
    n_base = lim.n_baseline
    reset_set = set(int(r) for r in resets)
    segment = np.zeros(len(xs), dtype=int)
    seg = 0
    for i in range(n_base, len(xs)):
        if i == n_base or int(fn[i - 1]) in reset_set:
            seg += 1
        segment[i] = seg
    out = pd.DataFrame({
        "t": np.arange(1, len(xs) + 1), "flight_no": fn, "value": xs,
        "center": lim.center, "lcl": lim.lcl, "ucl": lim.ucl, "sigma": lim.sigma_hat,
        "baseline": segment == 0, "segment": segment,
        "z": np.nan, "ewma_lcl": np.nan, "ewma_ucl": np.nan, "signal_ewma": False,
        **{f"rule_{k}": False for k in range(1, 9)}, "rules_triggered": "",
    })
    for s in range(1, seg + 1):
        idx = np.flatnonzero(segment == s)
        ew = ewma_chart(xs[idx], lam=lam, L=L, mu0=lim.center, sigma=lim.sigma_hat)
        out.loc[idx, ["z", "ewma_lcl", "ewma_ucl"]] = ew[["z", "lcl", "ucl"]].to_numpy()
        out.loc[idx, "signal_ewma"] = ew["signal"].to_numpy()
        rules = spc_rules(xs[idx], lim.center, lim.sigma_hat)
        for k in range(1, 9):
            out.loc[idx, f"rule_{k}"] = rules[f"rule_{k}"].to_numpy()
        out.loc[idx, "rules_triggered"] = rules["rules_triggered"].to_numpy()
    out["signal_ewma"] = out["signal_ewma"].astype(bool)
    rule_any = out["rules_triggered"] != ""
    out["signal"] = out["signal_ewma"] | rule_any
    out["what"] = [("EWMA" if e else "") + ("; " if e and r else "") + (f"rule {r}" if r else "")
                   for e, r in zip(out["signal_ewma"], out["rules_triggered"])]
    return out


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


def fleet_status(flights: pd.DataFrame, maintenance: pd.DataFrame | None = None,
                 recent: int = RECENT_FLIGHTS, n_baseline: int = N_BASELINE,
                 min_baseline: int = MIN_BASELINE) -> pd.DataFrame:
    """Decide go / watch / ground for every drone from its open (not yet acted on) signals.

    For each reading in MONITORED it runs monitor_chart(), restarting after every
    action in `maintenance` (leave it out and nothing restarts). A signal is "open"
    if it came after the latest action on that chart. Then:

      ground  the latest reading is open and outside its I-chart 3-sigma limits
              (rule 1), or the EWMA is outside its limits now: inspect before flying
      watch   no ground reason, but an open signal (EWMA or any of the 8 rules)
              within the last `recent` readings
      go      no open signal in the last `recent` readings
      not enough data
              fewer than `min_baseline` readings (or no variation): no limits

    Returns one row per drone: drone_id, status, reason (plain English, reasons
    joined by "; "), last_flight_no, n_flights, health and health_driver. health =
    chart_margin() of the latest point on the most-stretched chart, using the EWMA
    (the smoothed wear level) once past the baseline and the reading itself before.
    """
    f = flights if "temp_rise_c" in flights.columns else add_derived(flights)
    rows = []
    for drone in sorted(f["drone_id"].unique()):
        d = f[f["drone_id"] == drone].sort_values("datetime")
        last_no = int(flight_numbers(d["flight_id"]).iloc[-1])
        ground, watch, margins = [], [], {}
        try:
            for col, name, unit in MONITORED:
                s = drone_series(f, drone, col)
                resets = reset_flights(maintenance, drone, col)
                ch = monitor_chart(s["value"], s["flight_no"], resets, n_baseline, min_baseline)
                r = ch.iloc[-1]
                if r.baseline:
                    margins[name] = chart_margin(r.value, r.center, r.lcl, r.ucl)
                else:
                    margins[name] = chart_margin(r.z, r.center, r.ewma_lcl, r.ewma_ucl)
                last_action = max(resets) if resets else 0
                open_ = ch[~ch["baseline"] & (ch["flight_no"] > last_action)]
                latest_open = len(open_) and open_.index[-1] == ch.index[-1]
                if latest_open and r.rule_1:
                    ground.append(f"{name} {r.value:.2f} {unit} on flight {r.flight_no} is outside "
                                  f"its normal range ({r.lcl:.2f} to {r.ucl:.2f})")
                elif latest_open and r.signal_ewma:
                    side = "above its upper" if r.z > r.center else "below its lower"
                    start = _run_start(open_["signal_ewma"], open_["flight_no"])
                    ground.append(f"{name} trend (EWMA) {side} limit since flight {start}")
                else:
                    hits = open_[open_["signal"] & (open_.index >= ch.index[-1] - recent + 1)]
                    if len(hits):
                        what = ", ".join(f"flight {h.flight_no} ({h.what})" for h in hits.itertuples())
                        watch.append(f"{name} signalled on {what}, not yet inspected")
        except ValueError as err:
            rows.append(dict(drone_id=drone, status="not enough data", reason=str(err),
                             last_flight_no=last_no, n_flights=len(d),
                             health=float("nan"), health_driver=""))
            continue
        status = "ground" if ground else "watch" if watch else "go"
        reason = "; ".join(ground or watch) or f"no open signal in the last {recent} flights"
        driver = min(margins, key=margins.get)
        rows.append(dict(drone_id=drone, status=status, reason=reason,
                         last_flight_no=last_no, n_flights=len(d),
                         health=margins[driver], health_driver=driver))
    return pd.DataFrame(rows)


def _run_start(signal: pd.Series, flight_no: pd.Series) -> int:
    """Flight number where the current unbroken run of signals began."""
    flags = signal.to_numpy()
    k = len(flags) - 1
    while k > 0 and flags[k - 1]:
        k -= 1
    return int(flight_no.iloc[k])


#: Columns the timeline needs in a maintenance log (data/README.md).
REQUIRED_MAINTENANCE_COLUMNS = ("drone_id", "flight_id", "action", "chart", "component_type",
                                "position", "warned_after_flight", "reason")
#: What each timeline marker means.
MARKERS = {"W": "warning: part near its replace-at age, or found worn",
           "R": "part replaced on schedule or because it was worn",
           "F": "part failed in flight, replaced before the next flight",
           "S": "special cause found and fixed (part replaced or repaired)",
           "N": "chart signalled, inspected, no fault found"}
CHART_NAME = {col: name for col, name, _ in MONITORED}


def check_maintenance(maintenance: pd.DataFrame) -> pd.DataFrame:
    """Refuse a maintenance log the timeline cannot use, with a clear message."""
    missing = [c for c in REQUIRED_MAINTENANCE_COLUMNS if c not in maintenance.columns]
    if missing:
        raise ValueError(f"the maintenance file is missing column(s): {', '.join(missing)} "
                         "(see data/README.md for the expected columns)")
    bad = set(maintenance["action"]) - {"replace", "repair", "inspect"}
    if bad:
        raise ValueError(f"action must be replace, repair or inspect, got {sorted(bad)}")
    return maintenance


def maintenance_timeline(maintenance: pd.DataFrame) -> pd.DataFrame:
    """Every W / R / F / S / N marker for the timeline, one row each (see MARKERS).

    lane is the part slot ("propeller 2") for part actions, or the chart's plain name
    for repairs and no-fault inspections. A W comes from a worn part found at
    inspection, or from warned_after_flight on a replacement (the age warning).
    Returns drone_id, lane, flight_no, marker, detail; in flight order.
    """
    m = check_maintenance(maintenance)
    fno = flight_numbers(m["flight_id"])
    rows = []
    for r, k in zip(m.itertuples(), fno):
        part = isinstance(r.component_type, str) and r.component_type != ""
        lane = f"{r.component_type} {int(r.position)}" if part else CHART_NAME.get(r.chart, r.chart)
        if r.action == "replace":
            if pd.notna(r.warned_after_flight):
                rows.append((r.drone_id, lane, int(r.warned_after_flight), "W", "warned"))
            marker = ("F" if r.reason == "failed in flight"
                      else "S" if r.reason.startswith("special cause") else "R")
            rows.append((r.drone_id, lane, int(k), marker, r.reason))
        elif r.action == "repair":
            rows.append((r.drone_id, lane, int(k), "S", r.reason))
        elif r.reason.startswith("worn"):
            rows.append((r.drone_id, lane, int(k), "W", r.reason))
        else:
            rows.append((r.drone_id, lane, int(k), "N", r.reason))
    out = pd.DataFrame(rows, columns=["drone_id", "lane", "flight_no", "marker", "detail"])
    # the same warning can come from the inspection row and from the replacement row
    out = out.drop_duplicates(subset=["drone_id", "lane", "flight_no", "marker"])
    return out.sort_values(["drone_id", "flight_no", "lane"], kind="stable").reset_index(drop=True)


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


#: Batteries each drone swaps between; one battery charge = this many drone flights.
BATTERIES_PER_DRONE = 2


def replacement_plan(components: pd.DataFrame, flights: pd.DataFrame, by_type: pd.DataFrame) -> pd.DataFrame:
    """How long until each part still in service reaches its replace-at age (its type's B10).

    remaining  = B10 - age, in the part's own unit (flight hours or charge cycles)
    flights_left:
        motors, propellers: remaining hours / the drone's mean flight length in hours
        batteries: remaining charges x BATTERIES_PER_DRONE (the drone alternates its
        batteries, so each one is charged on every second flight)
    days_left  = flights_left / the drone's flights per day in the logbook
    Negative values mean the part is already past its replace-at age (overdue = True);
    due = True within WARN_FLIGHTS flights of it (the timeline's W).
    Returns one row per in-service part with drone_id, component_id, component_type,
    position (from the id), lot, age, b10, unit, remaining, pct_used, flights_left,
    days_left, overdue; most urgent first.
    """
    b10 = by_type.dropna(subset=["b10"]).set_index("component_type")["b10"]
    live = components[components["end_date"].isna()].copy()
    live = live[live["component_type"].isin(b10.index)]
    f = flights.copy()
    f["_t"] = pd.to_datetime(f["datetime"])
    pace = f.groupby("drone_id").agg(mean_min=("flight_min", "mean"), n=("flight_id", "size"),
                                     first=("_t", "min"), last=("_t", "max"))
    # n flights have n - 1 gaps between the first and the last, so the rate is (n - 1) / span
    span_days = ((pace["last"] - pace["first"]).dt.total_seconds() / 86400).clip(lower=1)
    pace["per_day"] = (pace["n"] - 1).clip(lower=1) / span_days
    live = live[live["drone_id"].isin(pace.index)]
    live["b10"] = live["component_type"].map(b10)
    live["age"] = live["life_value"]
    live["unit"] = live["component_type"].map(LIFE_UNIT)
    live["remaining"] = live["b10"] - live["age"]
    live["pct_used"] = 100 * live["age"] / live["b10"]
    hours_per_flight = live["drone_id"].map(pace["mean_min"]) / 60
    live["flights_left"] = np.where(live["component_type"] == "battery",
                                    live["remaining"] * BATTERIES_PER_DRONE,
                                    live["remaining"] / hours_per_flight)
    live["days_left"] = live["flights_left"] / live["drone_id"].map(pace["per_day"])
    live["overdue"] = live["remaining"] <= 0
    live["due"] = live["flights_left"] <= WARN_FLIGHTS
    live["position"] = live["component_id"].str.split("-").str[2].astype(int)
    cols = ["drone_id", "component_id", "component_type", "position", "lot", "age", "b10", "unit",
            "remaining", "pct_used", "flights_left", "days_left", "overdue", "due"]
    return live[cols].sort_values("days_left").reset_index(drop=True)

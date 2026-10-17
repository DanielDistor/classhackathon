"""Generate the invented test data for the drone fleet reliability tool.

Run from the repo root:

    python data/simulate.py

It writes one folder, data/fleet/, holding the active fleet's records:

    flights.csv       one row per flight (what the technician logs)
    components.csv    one row per part life (the Weibull input)
    maintenance.csv   one row per replacement, repair or no-fault inspection
    answer_key.csv    the injected special causes (the tool never reads this;
                      it is how the tests check that every one was caught)
    replace_at.csv    the shop's replace-at ages (B10 fitted on the history)
    fleet_reference.csv
                      the fleet's normal range per reading, from acceptance
                      flights (each drone's first 50 log flights are checked
                      against it, rule 1 only, while its own baseline builds)

Every number is invented. See data/README.md, the codebook.

How the fleet is simulated
--------------------------
1. History (commissioning to the log start): every motor, propeller and
   battery runs until it fails, as the startup did before this tool. Lives
   are Weibull draws. The shop fits a Weibull to that history (qc.fit_by_type)
   and adopts B10 as each part type's replace-at age.
2. The flight log: 10 drones x 300 flights. Nothing is planted on a named
   drone. Two kinds of assignable cause act at random:
     - Wear: in the last stretch of its own Weibull life (its P-F interval)
       every part pushes one reading upward: motor -> temperature rise,
       propeller -> vibration, battery -> voltage sag per minute.
     - Special causes: one physical cause per Nelson / Western Electric rule
       shape (SPECIAL_CAUSES), each at a random drone and flight.
3. A simulated technician runs the tool's own statistics (app/qc.py) after
   every flight and acts:
     - a chart signals (EWMA, or any of the 8 rules on the I chart): fix any
       special cause found; a part found in its P-F interval is warned and
       replaced before the next flight; nothing found = a false alarm, logged
       as no_fault (the chart restarts, nothing else happens);
     - a part that reaches its B10 is warned and replaced before the next flight;
     - a part that fails in flight is replaced before the next flight.
   No drone ever stops flying.

Only numpy, pandas and lifelines (through app/qc.py) are needed.
"""

from __future__ import annotations

import math
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

OUT_DIR = Path(__file__).resolve().parent / "fleet"
#: Retirement settings simulated: a part retires at B_p, the age by which p% of its type fails.
#: The fleet is run once per p with the same seed (same part lifetimes and special causes), into
#: fleet/runs/pNN/; fleet/*.csv is the default run.
RETIRE_PCTS = (1, 2, 5, 10, 15, 20, 30)
DEFAULT_RETIRE_PCT = 10
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "app"))
import qc  # noqa: E402  the simulated technician acts on the tool's own statistics

SEED = 5300
#: The test datasets: one folder per fleet, the same simulator with a different seed, so each
#: fleet has its own part lifetimes, special causes and timing. "fleet" is Fleet A, the main one.
DATASETS = {"fleet": 5300, "fleet_b": 7100}
N_DRONES = 10
FLIGHTS_PER_DRONE = 300
LOG_START = pd.Timestamp("2026-07-01")      # first day of the flight log
LOG_DAYS = 91                               # 300 flights at ~3.3 a day
HISTORY_FLIGHTS_PER_DAY = 3.3               # usage before the flight log starts
MEAN_FLIGHT_MIN = 22.0

# True life distributions and wear behaviour per part type.
#   beta, eta  Weibull shape and scale (flight hours; charge cycles for batteries)
#   slots      positions per drone (batteries: 2 packs used in turn)
#   pf         P-F interval: how long before failure the wear shows in the
#              reading (same units as eta)
#   chart      the reading this part type pushes up as it wears
PARTS = {
    "motor": dict(beta=2.5, eta=500.0, slots=4, pf=25.0, chart="temp_rise_c", prefix="M"),
    "propeller": dict(beta=1.8, eta=150.0, slots=4, pf=8.0, chart="vibration_rms", prefix="P"),
    "battery": dict(beta=3.0, eta=400.0, slots=2, pf=30.0, chart="sag_rate_v_per_min", prefix="B"),
}
CHART_TYPE = {spec["chart"]: ctype for ctype, spec in PARTS.items()}
#: Approximate in-control standard deviation of each reading (sizes the effects below).
CHART_SD = {"temp_rise_c": 1.45, "vibration_rms": 0.25, "sag_rate_v_per_min": 0.014}
#: Wear drift at the moment of failure, in chart standard deviations (linear ramp over the P-F interval).
DRIFT_AT_FAILURE = 4.0
P_REMOVED_EARLY = 0.08          # history only: chance a part was pulled before it failed (censored)
EVENT_SPACING = 40              # no two causes on the same drone and chart within this many flights

# One physical special cause per SPC rule shape (rule 3, a trend, is the wear itself).
#   shift   added to the reading, in chart standard deviations
#   part    the part type it damages (replaced to fix it), or None (repaired)
SPECIAL_CAUSES = {
    1: dict(cause="prop strike", chart="vibration_rms", part="propeller",
            how="one vibration spike of +6 sd, then +1 sd from the chipped prop"),
    2: dict(cause="hard landing", chart="temp_rise_c", part="motor",
            how="bent motor shaft: temperature rise steps up +1.5 sd and stays"),
    4: dict(cause="bad battery cell", chart="sag_rate_v_per_min", part="battery",
            how="+2.5 sd voltage sag on that pack's flights only, so readings alternate"),
    5: dict(cause="loose power connector", chart="sag_rate_v_per_min", part=None,
            how="+3 sd voltage sag on a random 40% of flights"),
    6: dict(cause="prop imbalance", chart="vibration_rms", part="propeller",
            how="badly balanced prop after a field repair: vibration +1.3 sd"),
    7: dict(cause="vibration log over-filtered", chart="vibration_rms", part=None,
            how="firmware update smooths the log: vibration noise shrinks to 0.2x, readings too flat"),
    8: dict(cause="loose motor mount", chart="vibration_rms", part=None,
            how="mount rattles in one of two modes: vibration +1.8 or -1.8 sd each flight"),
}

FAILURE_MODES = {
    "motor": (["bearing", "winding"], [0.7, 0.3]),
    "propeller": (["chip", "crack"], [0.6, 0.4]),
    "battery": (["capacity_fade", "swelling"], [0.8, 0.2]),
}
#: Baseline (Phase I) length in flights: the tool's own default.
BASELINE = qc.N_BASELINE
#: Acceptance flights per drone (all-new parts, before the log): the fleet reference.
ACCEPTANCE_FLIGHTS = 20
#: Special causes start after the baseline, with a margin, so the baseline limits stay clean.
FIRST_EVENT_FLIGHT = BASELINE + 10
TYPE_KEY = {"motor": 10, "propeller": 20, "battery": 40}


def rng_for(*key: int) -> np.random.Generator:
    """One independent random stream per (seed, purpose, ...) key."""
    return np.random.default_rng([SEED, *key])


def part_lot(install: pd.Timestamp) -> str:
    """Supplier lot = install half-year, e.g. 2026H1."""
    return f"{install.year}H{1 if install.month <= 6 else 2}"


def draw_life(rng: np.random.Generator, ctype: str) -> tuple[float, float, float]:
    """(Weibull life, early-pull uniform, pull fraction) for one new part, by inverse transform."""
    spec = PARTS[ctype]
    u_life, u_pull, u_frac = rng.uniform(size=3)
    life = spec["eta"] * (-math.log(1 - u_life)) ** (1 / spec["beta"])
    if ctype == "battery":
        life = max(1.0, round(life))
    return life, u_pull, u_frac


def drift(ctype: str, age: float, life: float) -> float:
    """Wear added to the part's reading: 0 until the P-F interval, then a ramp to DRIFT_AT_FAILURE sd."""
    spec = PARTS[ctype]
    left = life - min(age, life)
    if left >= spec["pf"]:
        return 0.0
    return DRIFT_AT_FAILURE * CHART_SD[spec["chart"]] * (1 - left / spec["pf"])


@dataclass
class Part:
    cid: str
    ctype: str
    pos: int
    gen: int
    install: pd.Timestamp
    age: float               # usage so far (hours or cycles)
    life: float              # its true Weibull life (unknown to the technician)
    warned: int | None = None        # flight after which it was warned (and replaced)


def new_part(drone: str, ctype: str, pos: int, gen: int, install: pd.Timestamp,
             rng: np.random.Generator) -> Part:
    life, _, _ = draw_life(rng, ctype)
    return Part(f"{PARTS[ctype]['prefix']}-{drone[2:]}-{pos}-{gen:02d}", ctype, pos, gen, install, 0.0, life)


def comp_row(drone: str, p: Part, end: pd.Timestamp | None, status: int, mode: str) -> dict:
    return dict(component_id=p.cid, drone_id=drone, component_type=p.ctype, lot=part_lot(p.install),
                install_date=p.install.date(), end_date=end.date() if end is not None else None,
                life_value=round(p.age, 1) if p.ctype != "battery" else int(round(p.age)),
                status=status, failure_mode=mode)


# --------------------------------------------------------------------------
# 1. History: run to failure from commissioning to the log start
# --------------------------------------------------------------------------

def simulate_history(d: int) -> tuple[list[dict], dict[tuple[str, int], Part], dict[tuple[str, int], np.random.Generator]]:
    """Completed part lives before the log, and the part in each slot at the log start."""
    drone = f"D-{d + 1:02d}"
    commission = pd.Timestamp("2025-04-01") + pd.Timedelta(int(rng_for(3, d).integers(0, 180)), unit="D")
    hist_days = (LOG_START - commission).days
    usage = {"motor": hist_days * HISTORY_FLIGHTS_PER_DAY * MEAN_FLIGHT_MIN / 60,
             "battery": round(hist_days * HISTORY_FLIGHTS_PER_DAY / 2)}
    usage["propeller"] = usage["motor"]

    rows, current, streams = [], {}, {}
    for ctype, spec in PARTS.items():
        total = usage[ctype]

        def when(u: float) -> pd.Timestamp:
            return commission + (LOG_START - commission) * (u / total)

        for pos in range(1, spec["slots"] + 1):
            rng = rng_for(TYPE_KEY[ctype], d, pos)
            streams[(ctype, pos)] = rng
            t, gen = 0.0, 0
            while True:
                gen += 1
                life, u_pull, u_frac = draw_life(rng, ctype)
                p = Part(f"{spec['prefix']}-{drone[2:]}-{pos}-{gen:02d}", ctype, pos, gen, when(t), 0.0, life)
                end, status, mode = t + life, 1, None
                if u_pull < P_REMOVED_EARLY:
                    end, status, mode = t + max(1.0, u_frac * life), 0, "removed_other"
                    if ctype == "battery":
                        end = t + max(1.0, round(u_frac * life))
                if end >= total:                    # still flying at the log start
                    p.age = total - t
                    current[(ctype, pos)] = p
                    break
                p.age = end - t
                if mode is None:
                    names, probs = FAILURE_MODES[ctype]
                    mode = names[int(rng_for(30, d, TYPE_KEY[ctype], pos, gen).choice(len(names), p=probs))]
                rows.append(comp_row(drone, p, when(end), status, mode))
                t = end
    return rows, current, streams


# --------------------------------------------------------------------------
# 2. Special causes: random drone, flight and part, from the seed
# --------------------------------------------------------------------------

def place_special_causes() -> list[dict]:
    """1 + Poisson(1) occurrences of each cause across the fleet, spaced apart per drone and chart."""
    events = []
    for rule, sc in SPECIAL_CAUSES.items():
        rng = rng_for(50, rule)
        for _ in range(1 + int(rng.poisson(1.0))):
            for _try in range(100):
                d = int(rng.integers(0, N_DRONES))
                start = int(rng.integers(FIRST_EVENT_FLIGHT, FLIGHTS_PER_DRONE - 30 + 1))
                pos = int(rng.integers(1, PARTS[sc["part"]]["slots"] + 1)) if sc["part"] else None
                clash = any(e["d"] == d and SPECIAL_CAUSES[e["rule"]]["chart"] == sc["chart"]
                            and abs(e["start"] - start) < EVENT_SPACING for e in events)
                if not clash:
                    break
            events.append(dict(rule=rule, d=d, start=start, pos=pos, end=None,
                               detected=None, detected_by="", fix=""))
    events.sort(key=lambda e: (e["d"], e["start"], e["rule"]))
    for i, e in enumerate(events, 1):
        e["event_id"] = f"SC-{i:02d}"
    return events


def event_effect(e: dict, k: int, battery_pos: int, rng: np.random.Generator) -> tuple[float, float]:
    """(shift added to the reading, multiplier on the reading's noise) for one active cause on flight k."""
    sd = CHART_SD[SPECIAL_CAUSES[e["rule"]]["chart"]]
    u = rng.uniform()                          # drawn every flight so streams never shift
    match e["rule"]:
        case 1:
            return (6.0 if k == e["start"] else 1.0) * sd, 1.0
        case 2:
            return 1.5 * sd, 1.0
        case 4:
            return (2.5 * sd if battery_pos == e["pos"] else 0.0), 1.0
        case 5:
            return (3.0 * sd if u < 0.4 else 0.0), 1.0
        case 6:
            return 1.3 * sd, 1.0
        case 7:
            return 0.0, 0.2
        case 8:
            return (1.8 if u < 0.5 else -1.8) * sd, 1.0
    raise ValueError(f"no effect defined for rule {e['rule']}")


# --------------------------------------------------------------------------
# 3. The flight log with the technician in the loop
# --------------------------------------------------------------------------

def flight_base(d: int) -> pd.DataFrame:
    """Schedule and in-control readings for drone index d (no wear, no special causes)."""
    rng = rng_for(1, d)
    n = FLIGHTS_PER_DRONE
    days = np.sort(rng.integers(0, LOG_DAYS, n))
    minutes_of_day = rng.integers(7 * 60, 19 * 60, n)
    order = np.lexsort((minutes_of_day, days))
    days, minutes_of_day = days[order], minutes_of_day[order]
    dt = LOG_START + pd.to_timedelta(days, "D") + pd.to_timedelta(minutes_of_day, "min")
    flight_min = np.clip(rng.normal(MEAN_FLIGHT_MIN, 4.0, n), 8, 35).round(1)
    payload = rng.uniform(0.5, 2.5, n)
    day_level = rng_for(2).normal(17.0, 4.0, LOG_DAYS)          # one city: shared daily weather
    hour = minutes_of_day / 60
    ambient = (day_level[days] + 3.0 * np.sin((hour - 7) / 12 * math.pi) + rng.normal(0, 0.8, n)).round(1)
    drone_level = 18.0 + rng.normal(0, 1.0)
    temp_rise = drone_level + 1.2 * (payload - 1.5) + 0.1 * (flight_min - MEAN_FLIGHT_MIN) + rng.normal(0, 1.2, n)
    vib_level = 3.0 + rng.normal(0, 0.2)
    vib_noise = rng.normal(0, 0.25, n)
    sag_rate = 0.17 + 0.02 * (payload - 1.5) + rng.normal(0, 0.008, n)
    voltage_start = rng.normal(25.15, 0.04, n).round(2)
    return pd.DataFrame({"k": np.arange(1, n + 1), "datetime": dt, "flight_min": flight_min,
                         "ambient_temp_c": ambient, "temp_rise": temp_rise, "vib_level": vib_level,
                         "vib_noise": vib_noise, "sag_rate": sag_rate, "voltage_start_v": voltage_start,
                         "drone_level": drone_level})


def acceptance_readings(d: int) -> dict[str, np.ndarray]:
    """ACCEPTANCE_FLIGHTS test flights of drone index d with all-new parts (no wear, no
    special cause), same airframe as in the log: the readings behind the fleet reference."""
    base = flight_base(d)
    rng = rng_for(70, d)
    m = ACCEPTANCE_FLIGHTS
    fm = np.clip(rng.normal(MEAN_FLIGHT_MIN, 4.0, m), 8, 35)
    payload = rng.uniform(0.5, 2.5, m)
    return {
        "temp_rise_c": (base["drone_level"].iloc[0] + 1.2 * (payload - 1.5) + 0.1 * (fm - MEAN_FLIGHT_MIN)
                        + rng.normal(0, 1.2, m)).round(1),
        "vibration_rms": (base["vib_level"].iloc[0] + rng.normal(0, 0.25, m)).round(2),
        "sag_rate_v_per_min": (0.17 + 0.02 * (payload - 1.5) + rng.normal(0, 0.008, m)).round(4),
    }


def fleet_reference() -> pd.DataFrame:
    """The fleet's normal range per reading: mean and standard deviation of every drone's
    acceptance flights pooled (so it includes the differences between drones)."""
    pooled = {c: [] for c in CHART_TYPE}
    for d in range(N_DRONES):
        for c, v in acceptance_readings(d).items():
            pooled[c] += list(v)
    return pd.DataFrame([dict(chart=c, center=round(float(np.mean(v)), 4), sigma=round(float(np.std(v, ddof=1)), 4),
                              n=len(v), source=f"{ACCEPTANCE_FLIGHTS} acceptance flights per drone, all-new parts")
                         for c, v in pooled.items()])


class Chart:
    """The tool's view of one reading on one drone: the fleet check during the baseline,
    then baseline limits, EWMA and the 8 rules."""

    def __init__(self, name: str, fleet: tuple[float, float]):
        self.name = name
        self.fleet = fleet                 # (center, sigma) of the fleet reference
        self.values: list[float] = []      # every reading, for the baseline
        self.since_reset: list[float] = []
        self.lim: qc.ImrLimits | None = None

    def add(self, x: float) -> str:
        """Record a reading; return what signalled ("" if nothing), e.g. "EWMA" or "rule 1, 5"."""
        self.values.append(x)
        if self.lim is None:
            if len(self.values) == BASELINE:
                self.lim = qc.imr_limits(self.values, n_baseline=BASELINE)
            center, sigma = self.fleet
            return qc.FLEET_SIGNAL if abs(x - center) > 3 * sigma else ""
        self.since_reset.append(x)
        hits = []
        ew = qc.ewma_chart(self.since_reset, mu0=self.lim.center, sigma=self.lim.sigma_hat)
        if ew["signal"].iloc[-1]:
            hits.append("EWMA")
        rules = qc.spc_rules(self.since_reset[-15:], self.lim.center, self.lim.sigma_hat).iloc[-1]
        if rules["rules_triggered"]:
            hits.append(f"rule {rules['rules_triggered']}")
        return "; ".join(hits)

    def reset(self) -> None:
        """After a repair or replacement: the EWMA restarts at the center and runs count afresh."""
        self.since_reset = []


def flights_to_retire(p: Part, retire_at: float) -> float:
    per_flight = 0.5 if p.ctype == "battery" else MEAN_FLIGHT_MIN / 60
    return (retire_at - p.age) / per_flight


def simulate_log(d: int, current: dict[tuple[str, int], Part], streams: dict, retire_at: dict[str, float],
                 events: list[dict], fleet: dict[str, tuple[float, float]],
                 retire_pct: int = DEFAULT_RETIRE_PCT) -> tuple[pd.DataFrame, list[dict], list[dict]]:
    drone = f"D-{d + 1:02d}"
    base = flight_base(d)
    times = list(base["datetime"])
    mine = [e for e in events if e["d"] == d]
    event_rng = {e["event_id"]: rng_for(51, e["rule"], d, e["start"]) for e in mine}
    charts = {c: Chart(c, fleet[c]) for c in CHART_TYPE}
    comps, maint = [], []
    motor_temps, vibs, v_ends, inflight = [], [], [], []

    def log(k: int, action: str, p: Part | None, new: Part | None, reason: str, warned: int | None = None,
            chart: str = ""):
        maint.append(dict(drone_id=drone, flight_id=f"F-{drone[2:]}-{k:03d}", datetime=times[k - 1],
                          action=action, chart=chart or PARTS[p.ctype]["chart"],
                          component_type=p.ctype if p else "", position=p.pos if p else None,
                          removed_id=p.cid if p and action == "replace" else "", installed_id=new.cid if new else "",
                          warned_after_flight=warned, reason=reason))

    def replace(k: int, p: Part, status: int, mode: str, reason: str, action: str = "replace") -> None:
        when = times[k - 1]
        comps.append(comp_row(drone, p, when, status, mode))
        new = new_part(drone, p.ctype, p.pos, p.gen + 1, when, streams[(p.ctype, p.pos)])
        current[(p.ctype, p.pos)] = new
        log(k, action, p, new, reason, p.warned)
        charts[PARTS[p.ctype]["chart"]].reset()
        for e in mine:              # a damaged part leaves with its special cause
            if e["end"] is None and e["start"] <= k and SPECIAL_CAUSES[e["rule"]]["part"] == p.ctype \
                    and e["pos"] == p.pos:
                e["end"], e["fix"] = k, e["fix"] or f"part replaced ({reason})"

    for row in base.itertuples():
        k = row.k
        bpos = (k - 1) % 2 + 1
        hours = row.flight_min / 60
        # ---- the flight: usage, failures, readings ----
        failed = []
        for (ctype, pos), p in current.items():
            if ctype == "battery" and pos != bpos:
                continue
            use = 1.0 if ctype == "battery" else hours
            if p.age < p.life <= p.age + use:
                failed.append(p)
            p.age += use
        shift = {c: 0.0 for c in CHART_TYPE}
        noise_mult = {c: 1.0 for c in CHART_TYPE}
        for e in mine:
            active = e["start"] <= k and (e["end"] is None or k <= e["end"])
            dx, nm = event_effect(e, k, bpos, event_rng[e["event_id"]])
            if active:
                c = SPECIAL_CAUSES[e["rule"]]["chart"]
                if e["rule"] == 2:      # the damaged motor runs hotter; the hottest motor is what's read
                    continue
                shift[c] += dx
                noise_mult[c] *= nm
        motor_heat = []
        for pos in range(1, PARTS["motor"]["slots"] + 1):
            p = current[("motor", pos)]
            heat = drift("motor", p.age, p.life)
            heat += sum(1.5 * CHART_SD["temp_rise_c"] for e in mine if e["rule"] == 2 and e["pos"] == pos
                        and e["start"] <= k and (e["end"] is None or k <= e["end"]))
            motor_heat.append(heat)
        tr = row.temp_rise + max(motor_heat) + shift["temp_rise_c"]
        vb = (row.vib_level + row.vib_noise * noise_mult["vibration_rms"] + shift["vibration_rms"]
              + sum(drift("propeller", current[("propeller", q)].age, current[("propeller", q)].life)
                    for q in range(1, PARTS["propeller"]["slots"] + 1)))
        bp = current[("battery", bpos)]
        sr = row.sag_rate + drift("battery", bp.age, bp.life) + shift["sag_rate_v_per_min"]
        # rounded exactly as logged, so the technician's charts match what the tool will read
        motor_temp = round(row.ambient_temp_c + tr, 1)
        v_end = round(row.voltage_start_v - sr * row.flight_min, 2)
        vb = round(vb, 2)
        motor_temps.append(motor_temp)
        vibs.append(vb)
        v_ends.append(v_end)
        inflight.append("return_home" if failed else "none")
        reading = {"temp_rise_c": motor_temp - row.ambient_temp_c, "vibration_rms": vb,
                   "sag_rate_v_per_min": (row.voltage_start_v - v_end) / row.flight_min}
        signals = {c: charts[c].add(reading[c]) for c in CHART_TYPE}

        # ---- after landing, before the next flight: the technician acts ----
        for p in failed:
            names, probs = FAILURE_MODES[p.ctype]
            mode = names[int(rng_for(30, d, TYPE_KEY[p.ctype], p.pos, p.gen).choice(len(names), p=probs))]
            replace(k, p, 1, mode, "failed in flight")
        for c, what in signals.items():
            if not what:
                continue
            ctype = CHART_TYPE[c]
            found = False
            for e in mine:
                sc = SPECIAL_CAUSES[e["rule"]]
                if sc["chart"] != c or e["start"] > k or e["end"] is not None:
                    continue
                found = True
                if e["detected"] is None:
                    e["detected"], e["detected_by"] = k, what
                if sc["part"]:
                    replace(k, current[(sc["part"], e["pos"])], 0, "damaged_" + sc["cause"].replace(" ", "_"),
                            f"special cause: {sc['cause']} ({what})")
                else:
                    e["end"], e["fix"] = k, "repaired"
                    log(k, "repair", None, None, f"special cause: {sc['cause']} ({what})", chart=c)
            for key in [key for key in current if key[0] == ctype]:
                p = current[key]
                if p.life - p.age < PARTS[ctype]["pf"]:
                    # Worn: warned and replaced before the next flight. It was about to fail, so it is
                    # logged as a potential failure (status 1): counting it as censored would bias the
                    # Weibull fit (informative censoring).
                    found = True
                    p.warned = k
                    replace(k, p, 1, "worn_potential_failure", f"worn: found after a chart signal ({what})")
            if not found:
                log(k, "no_fault", None, None, f"chart signal, nothing found: a false alarm ({what})", chart=c)
            charts[c].reset()
        for key in list(current):
            p = current[key]
            if flights_to_retire(p, retire_at[p.ctype]) <= 0:
                p.warned = k
                replace(k, p, 0, "replaced_scheduled", f"reached replace-at age (B{retire_pct})")

    end = None
    for p in current.values():
        comps.append(comp_row(drone, p, end, 0, "in_service"))
    f = pd.DataFrame({
        "flight_id": [f"F-{drone[2:]}-{k:03d}" for k in base["k"]],
        "drone_id": drone,
        "datetime": base["datetime"],
        "flight_min": base["flight_min"],
        "ambient_temp_c": base["ambient_temp_c"],
        "voltage_start_v": base["voltage_start_v"],
        "voltage_end_v": v_ends,
        "motor_temp_max_c": motor_temps,
        "vibration_rms": vibs,
        "inflight_event": inflight,
    })
    return f, comps, maint


def build_fleet(retire_pct: int = DEFAULT_RETIRE_PCT) -> dict[str, pd.DataFrame]:
    """Every table for the fleet when parts retire at B_retire_pct, as DataFrames (nothing written)."""
    history, start_parts, streams = {}, {}, {}
    hist_rows = []
    for d in range(N_DRONES):
        rows, current, st = simulate_history(d)
        history[d], start_parts[d], streams[d] = rows, current, st
        hist_rows += rows + [comp_row(f"D-{d + 1:02d}", p, None, 0, "in_service") for p in current.values()]
    fits = qc.fit_by_type(pd.DataFrame(hist_rows))
    fits["replace_at"] = [qc.b_life(r.beta, r.eta, retire_pct / 100) for r in fits.itertuples()]
    retire_at = fits.set_index("component_type")["replace_at"].to_dict()
    policy = fits[["component_type", "unit", "replace_at", "b10", "beta", "eta", "n", "n_failed"]].round(
        {"replace_at": 1, "b10": 1, "beta": 3, "eta": 1})
    policy.insert(2, "retire_pct", retire_pct)
    policy["fitted_on"] = f"parts history before {LOG_START.date()}"

    events = place_special_causes()
    ref = fleet_reference()
    fleet = {r.chart: (r.center, r.sigma) for r in ref.itertuples()}
    flights, comps, maint = [], [], []
    for d in range(N_DRONES):
        drone = f"D-{d + 1:02d}"
        current = start_parts[d]
        launch = []
        for key, p in list(current.items()):   # launch inspection: anything past its replace-at age goes
            if p.age >= retire_at[p.ctype]:
                launch.append(comp_row(drone, p, LOG_START, 0, "replaced_scheduled"))
                current[key] = new_part(drone, p.ctype, p.pos, p.gen + 1, LOG_START, streams[d][key])
        f, c, m = simulate_log(d, current, streams[d], retire_at, events, fleet, retire_pct)
        flights.append(f)
        comps += history[d] + launch + c
        maint += m

    flights = pd.concat(flights, ignore_index=True).sort_values(["datetime", "drone_id"], kind="stable")
    flights["datetime"] = flights["datetime"].dt.strftime("%Y-%m-%dT%H:%M")
    components = pd.DataFrame(comps).sort_values(["drone_id", "component_id"]).reset_index(drop=True)
    maintenance = pd.DataFrame(maint).sort_values(["datetime", "drone_id"], kind="stable").reset_index(drop=True)
    maintenance["datetime"] = maintenance["datetime"].dt.strftime("%Y-%m-%dT%H:%M")
    maintenance["position"] = maintenance["position"].astype("Int64")
    maintenance["warned_after_flight"] = maintenance["warned_after_flight"].astype("Int64")
    key = pd.DataFrame([dict(event_id=e["event_id"], drone_id=f"D-{e['d'] + 1:02d}", rule_shape=e["rule"],
                             cause=SPECIAL_CAUSES[e["rule"]]["cause"], chart=SPECIAL_CAUSES[e["rule"]]["chart"],
                             component_type=SPECIAL_CAUSES[e["rule"]]["part"] or "", position=e["pos"],
                             start_flight=e["start"], detected_after_flight=e["detected"],
                             detected_by=e["detected_by"], fixed_after_flight=e["end"], fix=e["fix"],
                             how=SPECIAL_CAUSES[e["rule"]]["how"]) for e in events])
    for col in ("position", "detected_after_flight", "fixed_after_flight"):
        key[col] = key[col].astype("Int64")
    return {"flights": flights.reset_index(drop=True), "components": components,
            "maintenance": maintenance, "answer_key": key, "replace_at": policy, "fleet_reference": ref,
            "retire_at": pd.Series(retire_at)}


RUN_TABLES = ("flights", "components", "maintenance", "answer_key", "replace_at")


def run_summary(t: dict, retire_pct: int) -> dict:
    """One row of runs/summary.csv: what this retirement setting cost and prevented."""
    m, f = t["maintenance"], t["flights"]
    rep = m[m["action"] == "replace"]
    row = dict(retire_pct=retire_pct)
    row.update({f"replace_at_{r.component_type}": r.replace_at for r in t["replace_at"].itertuples()})
    row.update(
        parts_replaced=len(rep),
        at_replace_age=int(rep["reason"].str.startswith("reached replace-at age").sum()),
        found_worn=int(rep["reason"].str.startswith("worn").sum()),
        special_causes_fixed=int(m["reason"].str.startswith("special cause").sum()),
        failed_in_flight=int((f["inflight_event"] == "return_home").sum()),
        false_alarms=int((m["action"] == "no_fault").sum()),
    )
    return row


def use_dataset(name: str) -> Path:
    """Point the simulator at one dataset: its seed (every random stream) and its folder."""
    global SEED
    SEED = DATASETS[name]
    return Path(__file__).resolve().parent / name


def write_dataset(out_dir: Path) -> None:
    """Simulate every retirement run of the current seed and write them under out_dir."""
    runs_dir = out_dir / "runs"
    summary = []
    for pct in RETIRE_PCTS:
        t = build_fleet(pct)
        folder = runs_dir / f"p{pct:02d}"
        folder.mkdir(parents=True, exist_ok=True)
        for name in RUN_TABLES:
            t[name].to_csv(folder / f"{name}.csv", index=False, lineterminator="\n")
        if pct == DEFAULT_RETIRE_PCT:
            for name in RUN_TABLES + ("fleet_reference",):
                t[name].to_csv(out_dir / f"{name}.csv", index=False, lineterminator="\n")
        summary.append(run_summary(t, pct))
        print(f"B{pct:<2d}: " + ", ".join(f"{k}={v}" for k, v in summary[-1].items() if k != "retire_pct"))
    pd.DataFrame(summary).to_csv(runs_dir / "summary.csv", index=False, lineterminator="\n")
    print(f"wrote {len(RETIRE_PCTS)} runs to {runs_dir}; {out_dir.name}/*.csv = the B{DEFAULT_RETIRE_PCT} run")


def main() -> None:
    for name, seed in DATASETS.items():
        print(f"--- {name} (seed {seed})")
        write_dataset(use_dataset(name))
    use_dataset("fleet")


if __name__ == "__main__":
    main()

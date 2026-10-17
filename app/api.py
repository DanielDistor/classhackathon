"""Drone fleet reliability API (FastAPI) and the React dashboard that uses it.

For the fleet maintenance technician: the current health of every drone (control
charts with all 8 Nelson / Western Electric rules and an EWMA, restarting after
each logged repair) and the wear of every installed part against its Weibull B10
replace-at age, with a timeline of every warning, replacement, failure and
special cause.

Every statistic comes from qc.py; this file only loads the data, calls qc.py and
returns the results as JSON. The React app (../web/, built into static/) is served
at / and reads everything from the /api/ routes below. Interactive docs: /docs.

Run locally:  ./testme.sh   (or: uvicorn api:app --port 8000, from this folder)
"""

from __future__ import annotations

import io
import json
import re
import shutil
import tempfile
import uuid
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd
from fastapi import FastAPI, File, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

import qc

HERE = Path(__file__).resolve().parent
DATA = HERE / "data"             # a copy of the repo's data/; sync_data.sh refreshes it
#: The test datasets (data/simulate.py, one seed each): folder -> name shown in the dashboard.
DATASET_NAMES = {"fleet": "Fleet A", "fleet_b": "Fleet B"}
DATASETS = [k for k in DATASET_NAMES if (DATA / k / "flights.csv").exists()]
DEFAULT_DATASET = "fleet"
FLEET = DATA / DEFAULT_DATASET
#: Retirement settings available (a part retires at B_p): one precomputed run each.
RETIRE_PCTS = sorted(int(p.name[1:]) for p in (FLEET / "runs").glob("p[0-9][0-9]")) or [10]
DEFAULT_RETIRE_PCT = 10
RETIRE = Query(DEFAULT_RETIRE_PCT, description="retire parts at B_p: when p% of that part type has failed")
DATASET = Query(DEFAULT_DATASET, description="test dataset: " + ", ".join(f"{k} ({v})" for k, v in DATASET_NAMES.items()))


#: Logbooks uploaded since the server started: dataset id -> {"name": file name, "dir": folder}.
UPLOADS: dict[str, dict] = {}
UPLOAD_DIR = Path(tempfile.gettempdir()) / "drone-fleet-uploads"


def dataset_dir(dataset: str) -> Path:
    """The folder of one test dataset or uploaded logbook; 422 for an unknown name."""
    if dataset in UPLOADS:
        return UPLOADS[dataset]["dir"]
    if dataset not in DATASETS:
        raise HTTPException(422, f"dataset must be one of {DATASETS} or an uploaded logbook, got {dataset!r}")
    return DATA / dataset


def has_runs(dataset: str) -> bool:
    """True for a test fleet simulated at every retirement setting; an upload is one run."""
    return (dataset_dir(dataset) / "runs").is_dir()
STATIC = HERE / "static"         # the built React app (cd ../web && npm run build)

#: Parts within this many flights of their replace-at age are listed as "coming up".
UPCOMING_FLIGHTS = 30
STATUS_ORDER = {"ground": 0, "watch": 1, "not enough data": 2, "go": 3}

# (column, chart title, what it catches, units, decimals): the three readings behind the status
DRONE_CHARTS = [
    ("temp_rise_c", "Motor temperature rise", "motor wear, hard-landing damage", "°C", 1),
    ("vibration_rms", "Vibration", "propeller wear, strikes, imbalance, loose mounts", "m/s²", 2),
    ("sag_rate_v_per_min", "Battery voltage drop per minute", "battery wear, bad cells, loose connectors",
     "V/min", 3),
]
CHART_COLUMNS = ["flight_no", "value", "center", "lcl", "ucl", "z", "ewma_lcl", "ewma_ucl", "fleet_lcl",
                 "fleet_ucl", "baseline", "rule_1", "rules_triggered", "signal_ewma", "signal_fleet",
                 "signal", "what"]

app = FastAPI(
    title="Drone Fleet Health & Part Wear Monitor API",
    description="Control charts (I chart with 8 rules + EWMA) and Weibull replace-at ages for a drone "
                "delivery fleet. Every number comes from the tested functions in qc.py.",
    version="1.0.0",
)
# Lets the React dev server (npm run dev, another port) call the API. Fine for a demo.
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


@app.middleware("http")
async def fresh_page(request, call_next):
    """Browsers must re-check index.html after a rebuild (the asset files carry a hash, so
    they can be cached); otherwise an open tab keeps showing the old dashboard."""
    response = await call_next(request)
    if response.headers.get("content-type", "").startswith("text/html"):
        response.headers["Cache-Control"] = "no-cache"
    return response


def records(df: pd.DataFrame) -> list[dict]:
    """A table as JSON-ready rows: numpy types become plain numbers, NaN becomes null."""
    return json.loads(df.to_json(orient="records", double_precision=6))


# ---------------------------------------------------------------- the data, computed once

def run_dir(dataset: str, retire: int) -> Path:
    """The folder of one retirement run of one dataset; 422 for a setting that was not simulated."""
    if retire not in RETIRE_PCTS:
        raise HTTPException(422, f"retire must be one of {RETIRE_PCTS} (percent), got {retire}")
    runs = dataset_dir(dataset) / "runs"
    return runs / f"p{retire:02d}" if runs.is_dir() else dataset_dir(dataset)


@lru_cache(maxsize=16)
def fleet(dataset: str = DEFAULT_DATASET, retire: int = DEFAULT_RETIRE_PCT) -> dict:
    """Load one retirement run of one dataset and compute every qc.py result the dashboard shows (once)."""
    folder = run_dir(dataset, retire)
    flights_raw = qc.check_flights(pd.read_csv(folder / "flights.csv"))
    flights = qc.add_derived(flights_raw)
    maintenance = qc.check_maintenance(pd.read_csv(folder / "maintenance.csv"))
    components = qc.check_components(pd.read_csv(folder / "components.csv"))
    policy = qc.check_replace_at(pd.read_csv(folder / "replace_at.csv"))
    reference = qc.fleet_reference(pd.read_csv(dataset_dir(dataset) / "fleet_reference.csv"))

    status = qc.fleet_status(flights, maintenance, fleet=reference)
    status["_order"] = status["status"].map(STATUS_ORDER)
    status = status.sort_values(["_order", "health", "drone_id"]).drop(columns="_order").reset_index(drop=True)
    by_type = qc.fit_by_type(components)
    plan = qc.replacement_plan(components, flights_raw, policy)
    # The health bar: average replace-at life left over each drone's installed parts.
    status = status.merge(qc.parts_health(plan).rename(columns={"health": "parts_health"})
                          .drop(columns="n_parts"), on="drone_id", how="left")
    timeline = qc.maintenance_timeline(maintenance)
    return dict(retire=retire, folder=folder, flights=flights, maintenance=maintenance, components=components,
                policy=policy,
                reference=reference, status=status, by_type=by_type, plan=plan, timeline=timeline,
                n_flights=int(qc.flight_numbers(flights["flight_id"]).max()))


def flights_equiv(component_type: str, b10: float, mean_flight_min: float) -> float:
    """Replace-at age expressed in drone flights (display only)."""
    if component_type == "battery":
        return b10 * qc.BATTERIES_PER_DRONE
    return b10 / (mean_flight_min / 60)


# ---------------------------------------------------------------- dashboard routes

@app.get("/api/health")
def health() -> dict:
    """Is the API up? (Used by the deploy check.)"""
    return {"status": "ok"}


@app.get("/api/runs")
def runs_view(dataset: str = DATASET) -> dict:
    """The retirement settings, and what each run cost and prevented (data/<dataset>/runs/summary.csv)."""
    path = dataset_dir(dataset) / "runs" / "summary.csv"
    summary = pd.read_csv(path) if path.exists() else pd.DataFrame()
    options = RETIRE_PCTS if has_runs(dataset) else [DEFAULT_RETIRE_PCT]
    return {"default": DEFAULT_RETIRE_PCT, "options": options, "summary": records(summary),
            "dataset": dataset, "datasets": [{"id": k, "name": DATASET_NAMES[k]} for k in DATASETS]}


@app.get("/api/fleet")
def fleet_view(retire: int = RETIRE, dataset: str = DATASET) -> dict:
    """Fleet tab: every drone's status, every installed part's replace-at countdown, the timeline."""
    d = fleet(dataset, retire)
    tl = d["timeline"]
    replaced = tl[tl["marker"] == "R"]
    by_chart = int(replaced["trigger"].str.startswith("chart").sum())
    return {
        "retire": retire,
        "replace_at": d["policy"].set_index("component_type")["replace_at"].to_dict(),
        "n_flights": d["n_flights"],
        "n_drones": int(d["flights"]["drone_id"].nunique()),
        "drones": sorted(d["flights"]["drone_id"].unique().tolist()),
        "n_baseline": qc.N_BASELINE,
        "warn_flights": qc.WARN_FLIGHTS,
        "upcoming_flights": UPCOMING_FLIGHTS,
        "recent_flights": qc.RECENT_FLIGHTS,
        "status": records(d["status"]),
        "plan": records(d["plan"]),
        "timeline": records(tl),
        "activity": {"replaced": len(replaced), "at_age": len(replaced) - by_chart, "by_chart": by_chart,
                     "failed": int((tl["marker"] == "F").sum()), "special": int((tl["marker"] == "S").sum())},
    }


@app.get("/api/drones/{drone_id}")
def drone_view(drone_id: str, retire: int = RETIRE, dataset: str = DATASET) -> dict:
    """Drone pop-up: status, part countdowns, timeline and the three restarting control charts."""
    d = fleet(dataset, retire)
    st = d["status"].set_index("drone_id")
    if drone_id not in st.index:
        raise HTTPException(404, f"no drone called {drone_id}")
    charts = []
    for col, title, catches, unit, dec in DRONE_CHARTS:
        s = qc.drone_series(d["flights"], drone_id, col)
        resets = qc.reset_flights(d["maintenance"], drone_id, col)
        try:
            ch = qc.monitor_chart(s["value"], s["flight_no"], resets, fleet=d["reference"].get(col))
        except ValueError as err:
            raise HTTPException(422, f"no {title.lower()} chart for {drone_id}: {err}") from None
        last = ch.iloc[-1]
        charts.append({
            "column": col, "title": title, "catches": catches, "unit": unit, "decimals": dec,
            "resets": resets,
            "summary": {"center": float(last["center"]), "lcl": float(last["lcl"]), "ucl": float(last["ucl"]),
                        "latest": float(last["value"]), "n_signal": int(ch["signal"].sum()),
                        "n_fleet": int(ch["signal_fleet"].sum()),
                        "n_rule1": int((ch["rule_1"] & ~ch["baseline"]).sum()),
                        "n_ewma": int(ch["signal_ewma"].sum()),
                        "restarts": len([r for r in resets if r > qc.N_BASELINE])},
            "points": records(ch[CHART_COLUMNS]),
        })
    row = st.loc[drone_id]
    return {
        "retire": retire,
        "drone_id": drone_id,
        "status": row["status"], "reason": row["reason"],
        "parts_health": None if pd.isna(row["parts_health"]) else float(row["parts_health"]),
        "worst_part": row["worst_part"], "worst_left": float(row["worst_left"]),
        "n_flights": d["n_flights"], "n_baseline": qc.N_BASELINE,
        "parts": records(d["plan"][d["plan"]["drone_id"] == drone_id].sort_values("flights_left")),
        "timeline": records(d["timeline"][d["timeline"]["drone_id"] == drone_id]),
        "charts": charts,
    }


@app.get("/api/reliability")
def reliability_view(retire: int = RETIRE, dataset: str = DATASET) -> dict:
    """Weibull tab: fits per part type, the shop's replace-at ages and the R(t) vs Kaplan-Meier curves."""
    d = fleet(dataset, retire)
    c, by_type = d["components"], d["by_type"]
    shop = d["policy"].set_index("component_type")["replace_at"]
    mean_min = float(d["flights"]["flight_min"].mean())
    fits = []
    for r in by_type.itertuples():
        replace_at = float(shop.get(r.component_type, r.b10))
        fits.append({**records(by_type[by_type["component_type"] == r.component_type])[0],
                     "replace_at": replace_at,
                     "replace_at_flights": flights_equiv(r.component_type, replace_at, mean_min)})
    curves = []
    for r in by_type.dropna(subset=["eta"]).itertuples():
        part = c[c["component_type"] == r.component_type]
        t = np.linspace(0, part["life_value"].max() * 1.1, 120)
        curves.append({"type": r.component_type, "unit": r.unit, "b10": r.b10, "beta": r.beta, "eta": r.eta,
                       "replace_at": float(shop.get(r.component_type, r.b10)),
                       "t": t.round(3).tolist(), "r": np.round(qc.reliability(t, r.beta, r.eta), 5).tolist(),
                       "km": records(qc.km_curve(part["life_value"], part["status"]))})
    return {"retire": retire, "fits": fits, "curves": curves, "warn_flights": qc.WARN_FLIGHTS,
            "plan": records(d["plan"])}


#: Estimated costs in dollars (planned replacement = part + labour + downtime; failure in flight =
#: a crashed delivery drone, its package and recovery). Placeholders: change them in the dashboard.
DEFAULT_COSTS = {"motor": (350.0, 8000.0), "propeller": (80.0, 8000.0), "battery": (380.0, 8000.0)}


@app.get("/api/cost")
def cost_view(dataset: str = DATASET,
              cp_motor: float = DEFAULT_COSTS["motor"][0], cf_motor: float = DEFAULT_COSTS["motor"][1],
              cp_propeller: float = DEFAULT_COSTS["propeller"][0], cf_propeller: float = DEFAULT_COSTS["propeller"][1],
              cp_battery: float = DEFAULT_COSTS["battery"][0], cf_battery: float = DEFAULT_COSTS["battery"][1]) -> dict:
    """Cost of the retirement choice, per drone-flight, two ways.

    model: the age-replacement cost model (qc.retirement_cost) on each part type's Weibull, for
           retirement at B_p over a fine grid of p. It assumes nothing warns before a failure.
    runs:  the simulated runs, where the charts do warn: planned replacements (at age or caught
           worn) x cp + failures in flight x cf, per drone-flight, at each slider setting.
    """
    costs = {"motor": (cp_motor, cf_motor), "propeller": (cp_propeller, cf_propeller),
             "battery": (cp_battery, cf_battery)}
    if any(not (cp > 0 and cf > 0) for cp, cf in costs.values()):
        raise HTTPException(422, "every cost must be a positive number")
    base = fleet(dataset)
    policy = base["policy"]
    hours = float(base["flights"]["flight_min"].mean()) / 60
    use = {"motor": 4 * hours, "propeller": 4 * hours, "battery": 1.0}    # per drone-flight, all slots
    grid = sorted(set(np.round(np.linspace(0.5, 40, 80), 2)) | set(RETIRE_PCTS))
    model = qc.retirement_cost(policy, costs, use, grid)
    total = model.groupby("retire_pct", as_index=False)["cost_per_flight"].sum()
    best = total.loc[total["cost_per_flight"].idxmin()]
    runs = []
    for pct in (RETIRE_PCTS if has_runs(dataset) else [DEFAULT_RETIRE_PCT]):
        d = fleet(dataset, pct)
        m = d["maintenance"]
        rep = m[m["action"] == "replace"]
        planned = rep[rep["reason"].str.startswith(("reached replace-at age", "worn"))]
        failed = rep[rep["reason"] == "failed in flight"]
        dollars = (sum(costs[t][0] * n for t, n in planned["component_type"].value_counts().items())
                   + sum(costs[t][1] * n for t, n in failed["component_type"].value_counts().items()))
        no_charts = float(total.loc[total["retire_pct"] == pct, "cost_per_flight"].iloc[0])
        runs.append({"retire_pct": pct, "cost_per_flight": dollars / len(d["flights"]),
                     "no_charts_per_flight": no_charts, "n_flights": len(d["flights"]),
                     "planned": len(planned), "caught_worn": int(planned["reason"].str.startswith("worn").sum()),
                     "failed": len(failed)})
    return {"dataset": dataset, "costs": {k: {"planned": v[0], "failure": v[1]} for k, v in costs.items()},
            "model": records(model[["retire_pct", "component_type", "cost_per_flight"]]),
            "model_total": records(total), "best_pct": float(best["retire_pct"]),
            "best_cost": float(best["cost_per_flight"]), "runs": runs}


@app.get("/api/guide")
def guide_view(dataset: str = DATASET) -> dict:
    """Guide page: the injected special causes (answer key), what the technician did, example rows."""
    key_path = dataset_dir(dataset) / "answer_key.csv"
    key = pd.read_csv(key_path) if key_path.exists() else pd.DataFrame(
        columns=["drone_id", "cause", "rule_shape", "start_flight", "detected_after_flight", "detected_by", "fix"])
    d = fleet(dataset)
    m, f, c = d["maintenance"], d["flights"], d["components"]
    reasons = m.loc[m["action"] == "replace", "reason"]
    parts = pd.concat([
        c[(c.component_type == "motor") & (c.status == 1)].head(1),
        c[c.failure_mode == "replaced_scheduled"].head(1),
        c[(c.component_type == "battery") & (c.failure_mode == "in_service")].head(1),
    ])
    flight_cols = ["flight_id", "drone_id", "datetime", "flight_min", "ambient_temp_c", "motor_temp_max_c",
                   "voltage_start_v", "voltage_end_v", "vibration_rms"]
    return {
        "dataset": dataset, "dataset_name": UPLOADS[dataset]["name"] if dataset in UPLOADS else DATASET_NAMES[dataset],
        "n_flights": d["n_flights"], "n_rows": len(f), "n_baseline": qc.N_BASELINE,
        "events": records(key[["drone_id", "cause", "rule_shape", "start_flight", "detected_after_flight",
                               "detected_by", "fix"]]),
        "n_scheduled": int(reasons.str.startswith("reached replace-at age").sum()),
        "n_worn": int(reasons.str.startswith("worn").sum()),
        "n_failed": int((reasons == "failed in flight").sum()),
        "example_flights": records(f[f["drone_id"] == "D-01"].head(3)[flight_cols]),
        "example_parts": records(parts[["component_id", "drone_id", "component_type", "lot", "install_date",
                                        "end_date", "life_value", "status", "failure_mode"]]),
    }


# ---------------------------------------------------------------- the statistics, on any data

class Readings(BaseModel):
    values: list[float] = Field(..., description="readings in time order", examples=[[10, 12, 11, 13, 12] * 5])
    n_baseline: int = Field(qc.N_BASELINE, description="the first n readings set the limits")


class Lives(BaseModel):
    life: list[float] = Field(..., description="age of each part at failure or removal (> 0)",
                              examples=[[120, 340, 410, 95, 260, 500, 380, 210]])
    status: list[int] = Field(..., description="1 = failed, 0 = censored (still working or removed)",
                              examples=[[1, 1, 0, 1, 1, 0, 1, 1]])


@app.post("/api/spc/imr")
def spc_imr(body: Readings) -> dict:
    """I-MR control limits from the baseline: center ± 3σ̂, σ̂ = MR̄ / 1.128 (qc.imr_limits)."""
    try:
        return qc.imr_limits(body.values, body.n_baseline)._asdict()
    except ValueError as err:
        raise HTTPException(422, str(err)) from None


@app.post("/api/spc/monitor")
def spc_monitor(body: Readings) -> list[dict]:
    """I chart with all 8 rules plus an EWMA (λ = 0.2), one row per reading (qc.monitor_chart)."""
    try:
        ch = qc.monitor_chart(body.values, range(1, len(body.values) + 1), n_baseline=body.n_baseline)
    except ValueError as err:
        raise HTTPException(422, str(err)) from None
    return records(ch[CHART_COLUMNS])


@app.post("/api/weibull")
def weibull(body: Lives) -> dict:
    """Two-parameter Weibull fit with right-censoring: β, η, 95% intervals, B10 (qc.weibull_fit)."""
    try:
        return qc.weibull_fit(body.life, body.status)._asdict()
    except ValueError as err:
        raise HTTPException(422, str(err)) from None


# ---------------------------------------------------------------- your own logbook (upload)

#: Largest upload accepted (bytes): a year of flights for a fleet is well under this.
MAX_UPLOAD = 10 * 1024 * 1024


def _read_logbook(name: str, raw: bytes) -> dict[str, pd.DataFrame]:
    """The sheets of an uploaded logbook, by lower-case name. A CSV is the flights sheet alone."""
    try:
        if name.lower().endswith(".csv"):
            return {"flights": pd.read_csv(io.BytesIO(raw))}
        if name.lower().endswith((".xlsx", ".xlsm")):
            sheets = pd.read_excel(io.BytesIO(raw), sheet_name=None, engine="openpyxl")
            return {k.strip().lower(): v for k, v in sheets.items()}
    except Exception as err:  # a corrupt or password-protected file, a bad CSV
        raise HTTPException(422, f"could not read {name}: {err}") from None
    raise HTTPException(422, "upload an Excel workbook (.xlsx) or a flights CSV (.csv)")


#: Source letter for each fleet in the combined dataset: its drones become A01, B01, U01, ...
COMBINE = {"fleet": "A", "fleet_b": "B"}
UPLOAD_PREFIX = "U"


def _relabel(t: dict[str, pd.DataFrame], prefix: str) -> dict[str, pd.DataFrame]:
    """Rename one fleet's drones to <prefix><number> (D-07 -> A07) in every id that names a drone, so
    fleets that reuse D-01 ... D-10 can sit side by side. Flight ids keep their flight number
    (F-07-074 -> F-A07-074) and part ids their type, slot and generation (M-07-3-02 -> M-A07-3-02)."""
    def drone(d) -> str:
        digits = re.sub(r"\D", "", str(d))
        return f"{prefix}{digits.zfill(2) if digits else d}"

    def part(cid, new_drone) -> str:
        if not isinstance(cid, str) or not cid:
            return cid
        bits = cid.split("-")
        return f"{bits[0]}-{new_drone}-{bits[-2]}-{bits[-1]}" if len(bits) >= 4 else f"{cid}-{prefix}"

    def flight(fid, new_drone) -> str:
        return f"F-{new_drone}-{str(fid).rsplit('-', 1)[-1]}"

    out = {}
    for name, df in t.items():
        df = df.copy()
        new = df["drone_id"].map(drone)
        if "flight_id" in df:
            df["flight_id"] = [flight(f, n) for f, n in zip(df["flight_id"], new)]
        for col in ("component_id", "removed_id", "installed_id"):
            if col in df:
                df[col] = [part(c, n) for c, n in zip(df[col], new)]
        df["drone_id"] = new
        if "datetime" in df:
            df["datetime"] = pd.to_datetime(df["datetime"]).dt.strftime("%Y-%m-%dT%H:%M")
        out[name] = df
    return out


@app.post("/api/upload")
async def upload_logbook(file: UploadFile = File(..., description="an .xlsx with 'flights' and 'components' sheets "
                                                  "(optional: 'maintenance')")) -> dict:
    """Combine your own logbook with Fleet A and Fleet B into one dataset, for the dashboard's Combined tab.

    Your workbook needs the same sheets and columns as a data/ folder (data/README.md); the example is
    web/public/example_logbook.xlsx. Drones are renamed by source (Fleet A: A01-A10, Fleet B: B01-B10,
    yours: U01, ...). On the combined data, every part type's replace-at age is the B10 fitted on all the
    parts (qc.fit_by_type), and each reading's fleet range is the mean and standard deviation of every
    drone's first 20 flights. Every GET route then serves it with ?dataset=<the id returned>. Kept in
    memory and a temp folder until the server restarts.
    """
    raw = await file.read()
    if len(raw) > MAX_UPLOAD:
        raise HTTPException(413, f"the file is larger than {MAX_UPLOAD // 2**20} MB")
    sheets = _read_logbook(file.filename or "", raw)
    missing = [k for k in ("flights", "components") if k not in sheets]
    if missing:
        raise HTTPException(422, f"the workbook needs sheets named {' and '.join(repr(m) for m in missing)} "
                                 f"(found: {', '.join(sheets) or 'none'})")
    notes = []
    try:
        mine = {"flights": qc.check_flights(sheets["flights"].dropna(how="all")),
                "components": qc.check_components(sheets["components"].dropna(how="all"))}
        comps = mine["components"]
        brand_new = (comps["status"] == 0) & (comps["life_value"] == 0)   # installed just now: no life information
        if brand_new.any():
            mine["components"] = comps[~brand_new]
            notes.append(f"{int(brand_new.sum())} part(s) with 0 use and still in service left out of the Weibull fit.")
        if "maintenance" in sheets and not sheets["maintenance"].dropna(how="all").empty:
            mine["maintenance"] = qc.check_maintenance(sheets["maintenance"].dropna(how="all"))
        else:
            mine["maintenance"] = pd.DataFrame(columns=list(qc.REQUIRED_MAINTENANCE_COLUMNS))
            notes.append("No maintenance sheet: your drones' charts never restart, so every past signal stays open.")
    except ValueError as err:
        raise HTTPException(422, str(err)) from None

    parts = [_relabel(mine, UPLOAD_PREFIX)]
    for ds, prefix in COMBINE.items():
        folder = dataset_dir(ds)
        parts.append(_relabel({n: pd.read_csv(folder / f"{n}.csv") for n in ("flights", "components", "maintenance")},
                              prefix))
    combined = {n: pd.concat([p[n] for p in parts], ignore_index=True) for n in ("flights", "components", "maintenance")}
    fits = qc.fit_by_type(combined["components"]).dropna(subset=["b10"])
    combined["replace_at"] = fits.assign(replace_at=fits["b10"])[["component_type", "unit", "replace_at", "b10",
                                                                   "beta", "eta"]]
    f = qc.add_derived(combined["flights"])
    first = f[qc.flight_numbers(f["flight_id"]) <= 20]
    combined["fleet_reference"] = pd.DataFrame([dict(chart=c, center=first[c].mean(), sigma=first[c].std())
                                                for c, _, _ in qc.MONITORED])

    dataset = f"combined-{uuid.uuid4().hex[:8]}"
    folder = UPLOAD_DIR / dataset
    folder.mkdir(parents=True, exist_ok=True)
    for name, df in combined.items():
        df.to_csv(folder / f"{name}.csv", index=False)
    UPLOADS[dataset] = {"name": file.filename or "your logbook", "dir": folder}
    try:
        d = fleet(dataset)                       # compute everything once: refuse what the tool cannot use
    except (ValueError, KeyError) as err:
        UPLOADS.pop(dataset)
        shutil.rmtree(folder, ignore_errors=True)
        raise HTTPException(422, f"could not combine this logbook with the test fleets: {err}") from None
    by_source = d["flights"]["drone_id"].str[0].value_counts().to_dict()
    return {"dataset": dataset, "name": UPLOADS[dataset]["name"],
            "n_drones": int(d["flights"]["drone_id"].nunique()), "n_flights": len(d["flights"]),
            "sources": [{"prefix": k, "name": v, "n_drones": int(d["flights"].loc[d["flights"]["drone_id"].str[0] == k, "drone_id"].nunique())}
                        for k, v in (("A", "Fleet A"), ("B", "Fleet B"), (UPLOAD_PREFIX, UPLOADS[dataset]["name"]))],
            "n_flights_by_source": {k: int(v) for k, v in by_source.items()}, "notes": notes}


# ---------------------------------------------------------------- the React app

if STATIC.is_dir():
    app.mount("/", StaticFiles(directory=STATIC, html=True), name="web")
else:
    @app.get("/")
    def root() -> dict:
        return {"message": "API is running. Build the React app (cd web && npm run build) to see the "
                           "dashboard here.", "docs": "/docs"}

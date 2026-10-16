"""Drone fleet reliability dashboard (Shiny for Python).

For the fleet maintenance technician: before each flight, which drones are
go, watch or ground, and why. Every statistic comes from qc.py; this file only
loads data, calls qc.py and shows the result. The welcome page lives in
intro.py and the look in styles.css.

Run locally:  ./testme.sh   (or: shiny run app.py, from this folder)
"""

from __future__ import annotations

import math
from html import escape
from pathlib import Path

import numpy as np
import pandas as pd
from shiny import App, reactive, render, ui
from shiny.types import SafeException

import charts
import qc
from intro import intro_page

HERE = Path(__file__).resolve().parent
DATA = HERE / "data"  # a copy of the repo's data/ folder; manifestme.sh refreshes it
DATASETS = {  # folder in data/ -> (name, what's in it)
    "healthy": ("Normal fleet", "No planted problems: every drone wears normally."),
    "motor_drift": ("Worn motor", "D-07's motor wears out and it crashes on flight 95. D-03 has a prop strike on flight 80."),
    "bad_battery_lot": ("Bad battery batch", "Batteries from supplier lot B wear out about 40% sooner."),
}
STATUS_ORDER = {"ground": 0, "watch": 1, "not enough data": 2, "go": 3}
STATUS_CLASS = {"ground": "ground", "watch": "watch", "go": "go", "not enough data": "na",
                "neutral": "neutral"}
STATUS_WORD = {"ground": "Ground", "watch": "Watch", "go": "Go", "not enough data": "Not enough data"}

# (column, chart title, units, decimals, EWMA too?)
DRONE_CHARTS = [
    ("temp_rise_c", "Motor temperature rise", "°C", 1, True),
    ("vibration_rms", "Vibration", "m/s²", 2, False),
    ("sag_rate_v_per_min", "Battery voltage sag per minute", "V/min", 3, False),
]

# Clicking a drone row sends its id to the server as input.open_drone.
CLICK_JS = ui.tags.script("""
document.addEventListener('click', function (e) {
  const row = e.target.closest('[data-drone]');
  if (row && window.Shiny) Shiny.setInputValue('open_drone', row.dataset.drone, {priority: 'event'});
});
""")


def pill(status: str) -> str:
    return f'<span class="pill {STATUS_CLASS[status]}">{STATUS_WORD[status]}</span>'


def health_bar(health: float, status: str, big: bool = True) -> str:
    """A filled bar: length = health (room left before a limit), colour = status."""
    if health is None or (isinstance(health, float) and math.isnan(health)):
        return '<div class="hbar na"><div class="hbar-fill" style="width:0%"></div></div>'
    pct = round(health * 100)
    return (f'<div class="hbar {STATUS_CLASS[status]}{" big" if big else ""}" role="meter" '
            f'aria-valuemin="0" aria-valuemax="100" aria-valuenow="{pct}">'
            f'<div class="hbar-fill" style="width:{max(pct, 1)}%"></div></div>')


def pct_text(health: float) -> str:
    return "–" if isinstance(health, float) and math.isnan(health) else f"{round(health * 100)}%"


controls = ui.div(
    ui.div(ui.span("1", class_="step-num"), ui.span("Demo: pick a test fleet", class_="ctl-title"),
           ui.span("A real startup would see its own fleet here. These are three invented fleets: the same "
                   "10 drones, each with one planted problem (or none).", class_="ctl-sub"), class_="ctl-head"),
    ui.input_radio_buttons(
        "dataset", None,
        {k: ui.TagList(ui.span(name, class_="ds-name"), ui.span(desc, class_="ds-desc"))
         for k, (name, desc) in DATASETS.items()},
        selected="healthy", inline=True),
    class_="controls",
)

dashboard = ui.div(
    CLICK_JS,
    ui.div(
        ui.div(ui.span("Drone Fleet Reliability Monitor", class_="title"),
               ui.span("go / watch / ground before every flight", class_="subtitle")),
        ui.input_action_link("about", "About this tool and the datasets"),
        class_="topbar",
    ),
    ui.div(
        controls,
        ui.div(ui.span("2", class_="step-num"), ui.span("Choose a view of that fleet", class_="ctl-title"),
               class_="ctl-head views-head"),
        ui.navset_pill(
            ui.nav_panel(
                "Fleet health",
                ui.div(ui.output_ui("fleet_kpis"), ui.output_ui("fleet_health"), class_="pt-3"),
            ),
            ui.nav_panel(
                "Log a flight",
                ui.div(
                    ui.p("Enter one flight's readings. The tool adds it to this fleet's logbook and tells you "
                         "straight away whether the drone should fly again. Fields start with this drone's "
                         "typical recent readings: replace them with what you measured.", class_="section-note"),
                    ui.div(
                        ui.input_select("log_drone", "Drone", []),
                        ui.input_text("log_when", "Take-off time (YYYY-MM-DDTHH:MM)", ""),
                        class_="log-top"),
                    ui.div(
                        ui.div(ui.div(ui.span("1", class_="step-num"), ui.h3("Before take-off"), class_="moment-head"),
                               ui.input_select("log_item", "Checklist: anything failed?",
                                               {"none": "Nothing, all passed", "prop_chip": "Propeller chipped",
                                                "loose_arm": "Arm loose", "connector": "Connector loose"}),
                               ui.input_select("log_battery", "Battery fitted", []),
                               ui.input_numeric("log_cycles", "Battery charge count", None, min=0, step=1),
                               ui.input_numeric("log_vstart", "Battery voltage at take-off (V)", None, step=0.01),
                               ui.input_numeric("log_payload", "Package weight (kg)", None, step=0.01),
                               ui.input_numeric("log_ambient", "Air temperature (°C)", None, step=0.1),
                               class_="info-card log-card"),
                        ui.div(ui.div(ui.span("2", class_="step-num"), ui.h3("During the flight"), class_="moment-head"),
                               ui.p("Copy these from the flight controller's log after landing.", class_="moment-who"),
                               ui.input_numeric("log_minutes", "Minutes flown", None, step=0.1),
                               ui.input_numeric("log_vib", "Vibration (m/s², RMS)", None, step=0.01),
                               ui.input_select("log_event", "Any alert?",
                                               {"none": "None", "warning": "Warning", "return_home": "Returned home on its own",
                                                "crash": "Crashed"}),
                               class_="info-card log-card"),
                        ui.div(ui.div(ui.span("3", class_="step-num"), ui.h3("Right after landing"), class_="moment-head"),
                               ui.input_numeric("log_motor", "Hottest motor (°C, infrared thermometer)", None, step=0.1),
                               ui.input_numeric("log_vend", "Battery voltage at landing (V)", None, step=0.01),
                               class_="info-card log-card"),
                        class_="grid-3"),
                    ui.div(ui.input_action_button("log_submit", "Log this flight and check the drone",
                                                  class_="btn-continue btn-log"), class_="log-actions"),
                    ui.output_ui("log_result"),
                    ui.div(ui.output_ui("log_count"),
                           ui.download_button("log_download", "Download this fleet's logbook (flights.csv)",
                                              class_="btn-outline-primary"),
                           ui.input_action_link("log_clear", "Remove the flights I logged"),
                           class_="panel log-footer"),
                    class_="pt-3",
                ),
            ),
            ui.nav_panel(
                "Drone detail",
                ui.div(
                    ui.div(ui.input_select("drone", "Drone", [], width="220px"),
                           ui.p("Pick a drone here, or click one on the Fleet health view.", class_="ctl-sub"),
                           class_="drone-pick"),
                    ui.output_ui("drone_banner"),
                    ui.div(ui.h4("The numbers behind the charts"), ui.output_ui("drone_numbers"),
                           class_="panel"),
                    ui.div(ui.output_plot("drone_charts", height="1250px"), class_="panel"),
                    ui.div(
                        ui.h4("How to read these charts"),
                        ui.div(ui.markdown(
                            "The shaded band is the drone's first 30 flights, its **baseline**. The dashed "
                            "**limits** are the baseline mean ± 3 sigma, where sigma = average moving range "
                            "÷ 1.128. A red ✕ is a **signal**: a reading the drone's own normal variation is "
                            "very unlikely to produce.\n\n"
                            "* **EWMA** (top chart): a running average that weights recent flights most "
                            "(λ = 0.2). It catches slow wear early.\n"
                            "* **I charts**: each reading on its own. They catch sudden damage.\n"
                            "* **Temperature rise** = hottest motor after landing − air temperature, so a "
                            "hot day isn't mistaken for wear."), class_="read-me"),
                        class_="panel"),
                    class_="pt-3",
                ),
            ),
            ui.nav_panel(
                "Part reliability",
                ui.div(
                    ui.p("How long motors, propellers and batteries last, from this fleet's parts history "
                         "(components.csv). Parts that haven't failed yet still count: they tell us the part "
                         "lasted at least that long.", class_="section-note"),
                    ui.output_ui("rel_cards"),
                    ui.div(ui.h4("How long parts last"),
                           ui.output_plot("rel_curves", height="380px"),
                           ui.p("Blue = the fitted Weibull model. Gray steps = the same thing measured straight "
                                "from the data (Kaplan-Meier). When the two agree, the model fits. Red dashed "
                                "line = B10, the age by which 10% of parts have failed.", class_="rule-note"),
                           class_="panel"),
                    ui.div(ui.h4("Battery batches compared"),
                           ui.output_ui("lot_sentence"),
                           ui.output_plot("lot_plot", height="260px"),
                           class_="panel"),
                    ui.div(ui.h4("Parts to replace at the next maintenance slot"),
                           ui.output_ui("due_table"), class_="panel"),
                    class_="pt-3",
                ),
            ),
            id="tabs",
        ),
        class_="dash",
    ),
)

app_ui = ui.page_fluid(
    ui.head_content(
        ui.tags.link(rel="preconnect", href="https://fonts.googleapis.com"),
        ui.tags.link(rel="stylesheet",
                     href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;650;700&display=swap"),
        ui.tags.style((HERE / "styles.css").read_text(encoding="utf-8")),
    ),
    ui.navset_hidden(
        ui.nav_panel("intro", intro_page()),
        ui.nav_panel("dashboard", dashboard),
        id="pages",
    ),
    title="Drone Fleet Reliability Monitor",
    class_="p-0",
)


def server(input, output, session):

    # ---------- page switching ----------
    @reactive.effect
    @reactive.event(input.enter)
    def _enter():
        ui.update_navset("pages", selected="dashboard")

    @reactive.effect
    @reactive.event(input.about)
    def _about():
        ui.update_navset("pages", selected="intro")

    @reactive.effect
    @reactive.event(input.open_drone)
    def _open_drone():
        ui.update_select("drone", selected=input.open_drone())
        ui.update_navset("tabs", selected="Drone detail")

    # ---------- data ----------
    logged = reactive.value({})       # dataset -> list of flight records logged this session
    log_message = reactive.value(None)  # ("ok", drone) or ("error", text)

    @reactive.calc
    def raw_flights() -> pd.DataFrame:
        f = pd.read_csv(DATA / input.dataset() / "flights.csv")
        for rec in logged.get().get(input.dataset(), []):
            f = qc.append_flight(f, rec)
        return f

    @reactive.calc
    def flights() -> pd.DataFrame:
        f = raw_flights()
        return qc.add_derived(f)

    @reactive.calc
    def status() -> pd.DataFrame:
        st = qc.fleet_status(flights())
        st["_order"] = st["status"].map(STATUS_ORDER)
        return st.sort_values(["_order", "health", "drone_id"]).drop(columns="_order").reset_index(drop=True)

    @reactive.effect
    def _drones():
        st = status()
        ui.update_select("drone", choices=sorted(st["drone_id"]),
                         selected=st["drone_id"].iloc[0] if len(st) else None)

    # ---------- Log a flight ----------
    @reactive.effect
    def _log_drones():
        drones = sorted(raw_flights()["drone_id"].unique())
        current = input.log_drone() if input.log_drone() in drones else drones[0]
        ui.update_select("log_drone", choices=drones, selected=current)

    @reactive.effect
    @reactive.event(input.log_drone, input.dataset, logged)
    def _log_defaults():
        """Refill the form with this drone's typical readings, ready for its next flight."""
        drone = input.log_drone()
        f = raw_flights()
        mine = f[f["drone_id"] == drone].sort_values("datetime")
        if mine.empty:
            return
        recent = mine.tail(10)
        last = mine.iloc[-1]
        # the drone swaps between its two batteries, so the next one is the one used two flights ago
        nxt = mine.iloc[-2] if len(mine) > 1 else last
        batteries = list(dict.fromkeys(mine["battery_id"].iloc[::-1]))[:4]
        ui.update_text("log_when", value=(pd.Timestamp(last["datetime"]) + pd.Timedelta(hours=4)).strftime("%Y-%m-%dT%H:%M"))
        ui.update_select("log_battery", choices=batteries, selected=nxt["battery_id"])
        ui.update_numeric("log_cycles", value=int(nxt["battery_cycles"]) + 1)
        ui.update_numeric("log_vstart", value=round(float(recent["voltage_start_v"].median()), 2))
        ui.update_numeric("log_payload", value=round(float(recent["payload_kg"].median()), 2))
        ui.update_numeric("log_ambient", value=round(float(recent["ambient_temp_c"].median()), 1))
        ui.update_numeric("log_minutes", value=round(float(recent["flight_min"].median()), 1))
        ui.update_numeric("log_vib", value=round(float(recent["vibration_rms"].median()), 2))
        ui.update_numeric("log_motor", value=round(float(recent["motor_temp_max_c"].median()), 1))
        ui.update_numeric("log_vend", value=round(float(recent["voltage_end_v"].median()), 2))
        ui.update_select("log_item", selected="none")
        ui.update_select("log_event", selected="none")

    @reactive.effect
    @reactive.event(input.log_submit)
    def _log_submit():
        entry = dict(
            drone_id=input.log_drone(), datetime=input.log_when(), preflight_fail_item=input.log_item(),
            battery_id=input.log_battery(), battery_cycles=input.log_cycles(), voltage_start_v=input.log_vstart(),
            payload_kg=input.log_payload(), ambient_temp_c=input.log_ambient(), flight_min=input.log_minutes(),
            vibration_rms=input.log_vib(), inflight_event=input.log_event(), motor_temp_max_c=input.log_motor(),
            voltage_end_v=input.log_vend())
        try:
            rec = qc.make_flight_record(raw_flights(), entry)
        except ValueError as err:
            log_message.set(("error", str(err)))
            return
        store = dict(logged.get())
        store[input.dataset()] = store.get(input.dataset(), []) + [rec]
        logged.set(store)
        log_message.set(("ok", rec["drone_id"], rec["flight_id"]))

    @reactive.effect
    @reactive.event(input.log_clear)
    def _log_clear():
        store = dict(logged.get())
        store.pop(input.dataset(), None)
        logged.set(store)
        log_message.set(None)

    @reactive.effect
    @reactive.event(input.dataset)
    def _log_reset_message():
        log_message.set(None)

    @render.ui
    def log_result():
        msg = log_message.get()
        if msg is None:
            return None
        if msg[0] == "error":
            return ui.div(ui.HTML(f"<p><b>Not logged.</b> {escape(msg[1])}</p>"), class_="banner ground")
        _, drone, fid = msg
        row = status().set_index("drone_id").loc[drone]
        cls = STATUS_CLASS[row["status"]]
        verdict = {"go": "can fly again", "watch": "can fly, but keep an eye on it",
                   "ground": "should not fly until it is inspected",
                   "not enough data": "needs more logged flights before the tool can judge it"}[row["status"]]
        return ui.div(
            ui.div(ui.h3(f"Logged {fid}. {drone} {verdict}."), ui.HTML(pill(row["status"])), class_="banner-head"),
            ui.HTML(f'<div class="banner-health">{health_bar(row["health"], row["status"])}'
                    f'<span>{pct_text(row["health"])} health</span></div>'),
            ui.p(row["reason"][0].upper() + row["reason"][1:] + "."),
            ui.HTML(f'<button class="link-btn" data-drone="{escape(drone)}">See {escape(drone)}\'s charts ›</button>'),
            class_=f"banner {cls}")

    @render.ui
    def log_count():
        n = len(logged.get().get(input.dataset(), []))
        return ui.p(f"You've logged {n} flight{'s' if n != 1 else ''} for this fleet in this session. "
                    "The app doesn't keep them after you close it, so download the logbook to save them.",
                    class_="rule-note m-0")

    @render.download(filename=lambda: f"flights_{input.dataset()}.csv")
    def log_download():
        yield raw_flights().to_csv(index=False, lineterminator="\n")

    # ---------- Fleet health tab ----------
    @render.ui
    def fleet_kpis():
        counts = status()["status"].value_counts()
        hints = {"ground": "inspect or repair before the next flight",
                 "watch": "a signal in the last 10 flights",
                 "go": "every chart in control"}
        return ui.div(*[ui.div(ui.div(STATUS_WORD[s], class_="label"),
                               ui.div(str(int(counts.get(s, 0))), class_="value"),
                               ui.div(hints[s], class_="hint"), class_=f"kpi {s}")
                        for s in ("ground", "watch", "go")], class_="kpis")

    @render.ui
    def fleet_health():
        rows = []
        for r in status().itertuples():
            driver = ("crashed on its last flight" if r.health_driver == "crash"
                      else f"closest to a limit: {r.health_driver}" if r.health_driver else "")
            rows.append(
                f'<button class="drone-row" data-drone="{escape(r.drone_id)}" '
                f'aria-label="Open {escape(r.drone_id)}">'
                f'<div class="dr-id">{escape(r.drone_id)}</div>'
                f'<div class="dr-status">{pill(r.status)}</div>'
                f'<div class="dr-bar">{health_bar(r.health, r.status)}'
                f'<div class="dr-why">{escape(r.reason)}</div></div>'
                f'<div class="dr-pct">{pct_text(r.health)}<span>{escape(driver)}</span></div>'
                f'<div class="dr-go">›</div></button>')
        legend = ("<b>Health</b> = how much room is left before the nearest control limit, on the drone's "
                  "most-stretched chart. 100% = right at its normal; 0% = at a limit, or crashed. "
                  "The colour is the status: Ground = latest reading outside a limit, EWMA outside its limit "
                  "now, or a crash · Watch = a signal in the last 10 flights · Go = every chart in control. "
                  "Click a drone to see its charts.")
        return ui.div(ui.HTML(f'<div class="drone-list">{"".join(rows)}</div>'),
                      ui.HTML(f'<p class="rule-note">{legend}</p>'), class_="panel")

    # ---------- Drone detail tab ----------
    @reactive.calc
    def drone_charts_data():
        """Every chart for the selected drone, computed once by qc.py."""
        drone = input.drone()
        if not drone:
            return None
        f = flights()
        out = []
        try:
            for col, title, unit, dec, with_ewma in DRONE_CHARTS:
                s = qc.drone_series(f, drone, col)
                if with_ewma:
                    out.append(("ewma", qc.ewma_chart(s["value"]), s["flight_no"], title, unit, dec))
                out.append(("i", qc.imr_chart(s["value"]), s["flight_no"], title, unit, dec))
        except ValueError as err:
            raise SafeException(f"No charts for {drone}: {err}") from None
        return out

    @render.ui
    def drone_banner():
        drone = input.drone()
        if not drone:
            return None
        row = status().set_index("drone_id").loc[drone]
        cls = STATUS_CLASS[row["status"]]
        return ui.div(
            ui.div(ui.h3(drone), ui.HTML(pill(row["status"])), class_="banner-head"),
            ui.HTML(f'<div class="banner-health">{health_bar(row["health"], row["status"])}'
                    f'<span>{pct_text(row["health"])} health</span></div>'),
            ui.p(row["reason"][0].upper() + row["reason"][1:] + "."),
            class_=f"banner {cls}")

    @render.ui
    def drone_numbers():
        data = drone_charts_data()
        if not data:
            return None
        rows = []
        for kind, ch, flight_no, title, unit, dec in data:
            sig = ch["signal"] if kind == "ewma" else ch["signal_i"]
            latest = ch["z"].iloc[-1] if kind == "ewma" else ch["value"].iloc[-1]
            last = ch.iloc[-1]
            room = qc.chart_margin(latest, last["center"], last["lcl"], last["ucl"])
            hits = flight_no.reset_index(drop=True)[(sig & ~ch["baseline"]).to_numpy()]
            first = f"flight {hits.iloc[0]}" if len(hits) else "none"
            name = f"{title} · {'EWMA' if kind == 'ewma' else 'I chart'}"
            limit_note = " (settled)" if kind == "ewma" else ""
            rows.append(
                f"<tr><td>{escape(name)}</td>"
                f'<td class="num">{ch["center"].iloc[0]:.{dec}f} {unit}</td>'
                f'<td class="num">{last["lcl"]:.{dec}f} to {last["ucl"]:.{dec}f}{limit_note}</td>'
                f'<td class="num">{latest:.{dec}f}</td>'
                f'<td class="room">{health_bar(room, "neutral", big=False)}'
                f'<span>{round(room * 100)}%</span></td>'
                f'<td class="num">{len(hits)}</td><td class="num">{first}</td></tr>')
        table = ('<table class="numbers"><thead><tr><th>Chart</th><th>Baseline mean</th><th>Limits</th>'
                 "<th>Latest</th><th>Room left</th><th>Signals after baseline</th><th>First signal</th>"
                 f"</tr></thead><tbody>{''.join(rows)}</tbody></table>")
        return ui.HTML(f'<div class="scroll-x">{table}</div>')

    # ---------- Part reliability tab ----------
    @reactive.calc
    def components() -> pd.DataFrame:
        return qc.check_components(pd.read_csv(DATA / input.dataset() / "components.csv"))

    @reactive.calc
    def by_type() -> pd.DataFrame:
        return qc.fit_by_type(components())

    @render.ui
    def rel_cards():
        cards = []
        for r in by_type().itertuples():
            name = charts.PART_TITLE.get(r.component_type, r.component_type)
            if r.note:
                cards.append(ui.div(ui.h3(name), ui.p(f"Not enough failures to fit: {r.note}."),
                                    class_="info-card"))
                continue
            if r.beta_lo > 1:
                shape = "Wear-out (β > 1): the older the part, the likelier it fails, so replacing it early prevents failures."
            elif r.beta_hi < 1:
                shape = "Early failures (β < 1): weak parts fail young; better incoming checks help more than early replacement."
            else:
                shape = "No clear wear-out (the interval for β includes 1): failures look random in age."
            cards.append(ui.div(
                ui.div(ui.h3(name), ui.span(f"{r.n_failed} failed of {r.n}", class_="tag"), class_="card-head"),
                ui.div(ui.span("Replace at", class_="rc-label"),
                       ui.span(f"{r.b10:.0f}", class_="rc-value"), ui.span(r.unit, class_="rc-unit"),
                       class_="rc-main"),
                ui.p(f"10% of {name.lower()} fail by {r.b10:.0f} {r.unit} (B10). Typical life η = {r.eta:.0f} "
                     f"(95% interval {r.eta_lo:.0f}–{r.eta_hi:.0f}); mean life {r.mean_life:.0f}."),
                ui.p(f"Shape β = {r.beta:.2f} ({r.beta_lo:.2f}–{r.beta_hi:.2f}). {shape}", class_="muted-p"),
                class_="info-card rel-card"))
        return ui.div(*cards, class_="grid-3 mb-3")

    @render.plot
    def rel_curves():
        c = components()
        curves = []
        for r in by_type().dropna(subset=["eta"]).itertuples():
            part = c[c["component_type"] == r.component_type]
            t = np.linspace(0, part["life_value"].max() * 1.1, 200)
            curves.append(dict(type=r.component_type, unit=r.unit, t=t, r=qc.reliability(t, r.beta, r.eta),
                               km=qc.km_curve(part["life_value"], part["status"]),
                               b10=r.b10, beta=r.beta, eta=r.eta))
        if not curves:
            return None
        return charts.reliability_figure(curves)

    @reactive.calc
    def lots() -> pd.DataFrame:
        try:
            return qc.compare_lots(components(), "battery")
        except ValueError:
            return pd.DataFrame()

    @render.ui
    def lot_sentence():
        lt = lots().dropna(subset=["eta"]) if len(lots()) else lots()
        if len(lt) < 2:
            return ui.p("Fewer than two battery lots have enough failures to compare.", class_="rule-note")
        worst, best = lt.loc[lt["eta"].idxmin()], lt.loc[lt["eta"].idxmax()]
        if worst["eta_hi"] < best["eta_lo"]:
            msg = (f"<b>Lot {escape(str(worst['lot']))} batteries wear out sooner.</b> Their typical life is "
                   f"{worst['eta']:.0f} charge cycles (95% interval {worst['eta_lo']:.0f}–{worst['eta_hi']:.0f}), "
                   f"against {best['eta']:.0f} for lot {escape(str(best['lot']))}. The intervals don't overlap, so "
                   "this is a real difference, not chance: check the supplier and replace those batteries first.")
            cls = "banner ground"
        else:
            msg = ("<b>No battery lot stands out.</b> Every lot's 95% interval overlaps the others, so the "
                   "differences are within chance.")
            cls = "banner go"
        return ui.div(ui.HTML(f"<p>{msg}</p>"), class_=cls)

    @render.plot
    def lot_plot():
        lt = lots()
        if lt.empty or lt["eta"].isna().all():
            return None
        return charts.lots_figure(lt, "charge cycles")

    @render.ui
    def due_table():
        due = qc.parts_past_b10(components(), by_type())
        if due.empty:
            return ui.p("No part still in service is past its B10 life.", class_="rule-note")
        def table(df):
            rows = "".join(
                f"<tr><td><strong>{escape(r.component_id)}</strong></td><td>{escape(r.drone_id)}</td>"
                f"<td>{escape(r.component_type)}</td><td>{escape(str(r.lot))}</td>"
                f'<td class="num">{r.life_value:g} {qc.LIFE_UNIT.get(r.component_type, "")}</td>'
                f'<td class="num">{r.b10:.0f}</td><td class="num">{r.pct_of_b10:.0f}%</td></tr>'
                for r in df.itertuples())
            return ('<div class="scroll-x"><table class="numbers"><thead><tr><th>Part</th><th>Drone</th>'
                    "<th>Type</th><th>Batch</th><th>Age now</th><th>B10 life</th><th>Age as % of B10</th>"
                    f"</tr></thead><tbody>{rows}</tbody></table></div>")

        counts = due["component_type"].value_counts()
        summary = ", ".join(f"{n} {t}{'s' if n != 1 else ''}" for t, n in counts.items())
        top, rest = due.head(10), due.iloc[10:]
        more = (f"<details class='more'><summary>Show the other {len(rest)} parts</summary>{table(rest)}</details>"
                if len(rest) else "")
        return ui.div(
            ui.HTML(f'<p class="due-summary"><b>{len(due)} parts still flying are past their B10 age</b> '
                    f"({summary}). Most overdue first:</p>"),
            ui.HTML(table(top) + more),
            ui.p("B10 = the age by which 10% of that kind of part fail. This fleet runs parts until they "
                 "break, so many are well past it: replacing at B10 would prevent most in-flight failures.",
                 class_="rule-note"))

    @render.plot
    def drone_charts():
        data = drone_charts_data()
        if not data:
            return None
        panels = []
        for kind, ch, flight_no, title, unit, _ in data:
            label = f"{title}: EWMA (slow wear)" if kind == "ewma" else f"{title}: each flight"
            panels.append((kind, ch, flight_no, label, unit))
        return charts.drone_figure(panels)


app = App(app_ui, server)

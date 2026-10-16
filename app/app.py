"""Drone fleet reliability dashboard (Shiny for Python).

For the fleet maintenance technician: monitor the current health of every drone
(SPC control charts with all 8 Nelson/Western Electric rules) and the wear and
tear of every installed part against its Weibull B10 replacement threshold.
Every statistic comes from qc.py; this file only loads data, calls qc.py and
displays the result.

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
    "problem_fleet": (
        "Fleet with problems",
        "Main demo: D-07's motor wears out (EWMA warns at flight 74, crash on 95), "
        "D-03 has a prop strike on flight 80 and battery wear sag (SPC Rule 2).",
    ),
    "healthy": (
        "Healthy fleet",
        "Comparison fleet: the same 10 drones with no severe faults (only ordinary common-cause variation).",
    ),
}
STATUS_ORDER = {"ground": 0, "watch": 1, "not enough data": 2, "go": 3}
STATUS_CLASS = {"ground": "ground", "watch": "watch", "go": "go", "not enough data": "na",
                "neutral": "neutral"}
STATUS_WORD = {"ground": "Do not fly", "watch": "Warning", "go": "Can fly", "not enough data": "Not enough data"}

# (column, chart title, what it catches, units, decimals, chart): the same three charts that set the status
DRONE_CHARTS = [
    ("temp_rise_c", "Motor temperature rise", "slow bearing/winding wear", "°C", 1, "ewma"),
    ("vibration_rms", "Vibration", "sudden rotor/propeller damage", "m/s²", 2, "i"),
    ("sag_rate_v_per_min", "Battery voltage drop per minute", "battery internal-resistance wear", "V/min", 3, "i"),
]

# Clicking a drone card sends its id to the server as input.open_drone.
CLICK_JS = ui.tags.script("""
document.addEventListener('click', function (e) {
  const row = e.target.closest('[data-drone]');
  if (row && window.Shiny) Shiny.setInputValue('open_drone', row.dataset.drone, {priority: 'event'});
});
""")


def pill(status: str) -> str:
    return f'<span class="pill {STATUS_CLASS[status]}">{STATUS_WORD[status]}</span>'


STATUS_SYMBOL = {"go": "✓", "watch": "!", "ground": "✕", "not enough data": "?"}
STATUS_COLOR = {"go": "#0a7d32", "watch": "#c98500", "ground": "#c62f2f", "not enough data": "#5f6670"}


def drone_icon(status: str) -> str:
    """A small top-view quadcopter drawn in the status colour, with the status symbol on its body."""
    c = STATUS_COLOR[status]
    arms = ((28, 28), (92, 28), (92, 92), (28, 92))
    g = "".join(f'<line x1="60" y1="60" x2="{x}" y2="{y}" stroke="#9aa3ad" stroke-width="7" stroke-linecap="round"/>'
                for x, y in arms)
    g += "".join(f'<circle cx="{x}" cy="{y}" r="22" fill="{c}" fill-opacity="0.13" stroke="{c}" '
                 f'stroke-opacity="0.55" stroke-width="2" stroke-dasharray="4 3"/>'
                 f'<line x1="{x - 18}" y1="{y + 5}" x2="{x + 18}" y2="{y - 5}" stroke="#6b7682" stroke-width="3.5" '
                 f'stroke-linecap="round" opacity="0.6"/><circle cx="{x}" cy="{y}" r="6.5" fill="#3a4450"/>'
                 for x, y in arms)
    g += (f'<rect x="42" y="44" width="36" height="32" rx="9" fill="{c}"/>'
          f'<text x="60" y="66.5" text-anchor="middle" font-size="19" font-weight="700" fill="#fff">'
          f'{STATUS_SYMBOL[status]}</text>')
    return f'<svg class="dc-icon" viewBox="0 0 120 120" aria-hidden="true">{g}</svg>'


WARNING_NOTE = "Inspect before next shift."


def card_text(status: str, reason: str) -> str:
    """One short line for a drone card summarizing its SPC telemetry status."""
    import re
    if status == "watch":
        if "SPC rule" in reason:
            short = reason.split(";")[0]
            return short[0].upper() + short[1:] + "."
        flights = sorted({int(n) for grp in re.findall(r"flights? ([\d, ]+)", reason)
                          for n in re.findall(r"\d+", grp)})
        where = (f"on flight {flights[0]}" if len(flights) == 1
                 else f"in flights {flights[0]}–{flights[-1]}" if flights else "recently")
        return f"Unusual reading{'s' if len(flights) > 1 else ''} {where}. {WARNING_NOTE}"
    short = reason.split(";")[0]
    return short[0].upper() + short[1:] + "."


controls = ui.div(
    ui.div(ui.span("Select Fleet Dataset", class_="ctl-title"),
           ui.span("10 drones × ~100 flights in September 2026 (click any drone card for SPC charts & part wear).",
                   class_="ctl-sub"),
           class_="ctl-head"),
    ui.input_radio_buttons(
        "dataset", None,
        {k: ui.TagList(ui.span(name, class_="ds-name"), ui.span(desc, class_="ds-desc"))
         for k, (name, desc) in DATASETS.items()},
        selected="problem_fleet", inline=True),
    ui.tags.details(
        ui.tags.summary("Or load your own logbook (CSV files)"),
        ui.div(
            ui.input_file("up_flights", "Flight logbook (flights.csv)", accept=[".csv"], button_label="Choose file"),
            ui.input_file("up_parts", "Parts history (components.csv, optional)", accept=[".csv"],
                          button_label="Choose file"),
            class_="upload-row"),
        ui.p("Same columns as the test data (see data/README.md in the repo). Your files replace the fleet "
             "chosen above until you reload the page.", class_="ctl-sub"),
        class_="upload-box"),
    class_="controls",
)


def drone_detail_body() -> ui.Tag:
    """Full Health & Wear View shown when a drone card is clicked."""
    return ui.div(
        ui.output_ui("drone_banner"),
        ui.div(
            ui.h4("Installed Parts: Current Wear vs. Weibull B10 Replacement Threshold"),
            ui.output_ui("drone_parts_wear"),
            class_="panel",
        ),
        ui.div(
            ui.h4("Flight Telemetry Summary & Active SPC Tests"),
            ui.output_ui("drone_numbers"),
            class_="panel",
        ),
        ui.div(
            ui.h4("Statistical Process Control (SPC) Charts"),
            ui.output_plot("drone_charts", height="920px"),
            class_="panel",
        ),
        ui.div(
            ui.h4("How to read these charts"),
            ui.div(ui.markdown(
                "The shaded band is the drone's first 30 flights, its **Phase I baseline**. The dashed "
                "**control limits** are the baseline mean ± 3σ, where σ̂ = average moving range "
                "÷ 1.128. A red **✕** is a **Rule 1 signal** (beyond ±3σ, grounding the drone if current); "
                "an amber **◆** is an **SPC pattern warning** (Rules 2–8: sustained shifts, trends, or zone runs).\n\n"
                "* **Trend (EWMA)**, top chart: weights recent flights most (λ = 0.2) to catch slow wear early.\n"
                "* **Each flight (I chart + 8 SPC tests)**: Rule 1 (> 3σ) grounds the drone immediately; "
                "Rules 2–8 (9 on one side, 6 trending, 14 alternating, 2 of 3 > 2σ, 4 of 5 > 1σ, "
                "15 within 1σ, 8 beyond 1σ) trigger a **Warning**.\n"
                "* **Temperature rise** = hottest motor after landing − ambient air temperature."),
                class_="read-me"),
            class_="panel"),
    )


dashboard = ui.div(
    CLICK_JS,
    ui.div(
        ui.div(ui.span("Drone Fleet Health & Part Wear Monitor", class_="title"),
               ui.span("SPC telemetry status + Weibull B10 component replacement alerts", class_="subtitle"),
               class_="topbar-left"),
        ui.input_action_button("about", "Guide & Data Reference", class_="btn-back"),
        class_="topbar",
    ),
    ui.div(
        controls,
        ui.navset_pill(
            ui.nav_panel(
                "Fleet Health & Alerts",
                ui.div(ui.output_ui("fleet_summary"), ui.output_ui("fleet_cards"), class_="pt-3"),
            ),
            ui.nav_panel(
                "Weibull Reliability & B10 Thresholds",
                ui.div(
                    ui.p("Weibull survival models R(t) = exp(−(t/η)^β) fitted by maximum likelihood with "
                         "right-censoring across the fleet's component history. We recommend preventive replacement "
                         "at B10 (the age by which 10% of parts fail, R(B10) = 90%).", class_="section-note"),
                    ui.output_ui("rel_cards"),
                    ui.div(
                        ui.h4("Weibull Reliability Curves R(t) vs. Empirical Kaplan-Meier Survival"),
                        ui.output_plot("rel_curves", height="390px"),
                        ui.p("Blue curve = fitted two-parameter Weibull model R(t). Gray step function = "
                             "non-parametric Kaplan-Meier survival estimate from the same censored data. "
                             "Red dashed vertical line = B10 replacement threshold.", class_="rule-note"),
                        class_="panel",
                    ),
                    ui.div(
                        ui.h4("Fitted Weibull Parameters & 95% Confidence Intervals"),
                        ui.output_ui("stats_table"),
                        class_="panel",
                    ),
                    ui.div(
                        ui.h4("Fleet-Wide Part Replacement Schedule (All 10 Drones)"),
                        ui.output_ui("parts_by_drone"),
                        class_="panel",
                    ),
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
        ui.nav_panel("dashboard", dashboard),
        ui.nav_panel("intro", intro_page()),
        id="pages",
        selected="dashboard",
    ),
    title="Drone Fleet Health & Part Wear Monitor",
    class_="p-0",
)


def server(input, output, session):

    # ---------- page switching ----------
    @reactive.effect
    @reactive.event(input.enter, input.enter_top)
    def _enter():
        ui.update_navset("pages", selected="dashboard")

    @reactive.effect
    @reactive.event(input.about)
    def _about():
        ui.update_navset("pages", selected="intro")

    @reactive.effect
    @reactive.event(input.open_drone)
    def _open_drone():
        selected.set(input.open_drone())
        ui.modal_show(ui.modal(drone_detail_body(), title=None, size="xl", easy_close=True,
                               footer=ui.modal_button("Close"), class_="drone-modal"))

    # ---------- data ----------
    @reactive.calc
    def flights() -> pd.DataFrame:
        up = input.up_flights()
        if up:
            try:
                f = qc.check_flights(pd.read_csv(up[0]["datapath"]))
            except (ValueError, pd.errors.ParserError) as err:
                raise SafeException(f"Can't use that flight logbook: {err}") from None
        else:
            f = pd.read_csv(DATA / input.dataset() / "flights.csv")
        return qc.add_derived(f)

    @reactive.calc
    def status() -> pd.DataFrame:
        st = qc.fleet_status(flights())
        st["_order"] = st["status"].map(STATUS_ORDER)
        return st.sort_values(["_order", "health", "drone_id"]).drop(columns="_order").reset_index(drop=True)

    @reactive.calc
    def components() -> pd.DataFrame:
        return qc.check_components(pd.read_csv(DATA / input.dataset() / "components.csv"))

    @reactive.calc
    def by_type() -> pd.DataFrame:
        return qc.fit_by_type(components())

    @reactive.calc
    def plan() -> pd.DataFrame:
        return qc.replacement_plan(components(), pd.read_csv(DATA / input.dataset() / "flights.csv"), by_type())

    selected = reactive.value(None)  # the drone whose pop-up is open

    # ---------- Fleet Health & Alerts tab ----------
    @render.ui
    def fleet_summary():
        st = status()
        p = plan()
        parts = []
        for s_ in ("go", "watch", "ground"):
            n = int((st["status"] == s_).sum())
            parts.append(f'<span class="sum-item {s_}"><span class="sym">{STATUS_SYMBOL[s_]}</span>'
                         f'<b>{n}</b> {STATUS_WORD[s_].lower()}</span>')
        n_over = int(p["overdue"].sum())
        drones_over = int(p.loc[p["overdue"], "drone_id"].nunique())
        parts.append(
            f'<span class="sum-item parts-alert"><span class="sym">🔧</span>'
            f'<b>{n_over}</b> parts past B10 ({drones_over} drones)</span>'
        )
        note = ""
        n_watch = int((st["status"] == "watch").sum())
        if input.dataset() == "healthy":
            note = ('<p class="fleet-note"><b>Comparison healthy fleet:</b> '
                    + (f"The {n_watch} warning{'s are' if n_watch != 1 else ' is'} ordinary common-cause variation "
                       "(e.g., short 30-flight baseline or random run patterns). "
                       if n_watch else "")
                    + "No drone is marked Do not fly.</p>")
        return ui.HTML(f'<div class="fleet-summary">{"".join(parts)}'
                       f'<span class="sum-hint">Click any drone for SPC charts &amp; 10-part wear breakdown.</span>'
                       f'{note}</div>')

    @render.ui
    def fleet_cards():
        p = plan()
        cards = []
        for r in status().sort_values("drone_id").itertuples():
            cls = STATUS_CLASS[r.status]
            pct = 0 if math.isnan(r.health) else round(r.health * 100)
            mine = p[p["drone_id"] == r.drone_id]
            if mine.empty:
                p_badge = '<div class="dc-part-alert over">✕ Airframe lost in crash</div>'
            else:
                n_over = int(mine["overdue"].sum())
                n_soon = int((~mine["overdue"] & (mine["days_left"] <= 14)).sum())
                if n_over > 0:
                    p_badge = (f'<div class="dc-part-alert over">'
                               f'🔧 {n_over} of {len(mine)} parts past B10</div>')
                elif n_soon > 0:
                    p_badge = (f'<div class="dc-part-alert soon">'
                               f'⏳ {n_soon} part{"s" if n_soon != 1 else ""} due within 14d</div>')
                else:
                    p_badge = '<div class="dc-part-alert ok">✓ All 10 parts within B10</div>'

            cards.append(
                f'<button class="drone-card {cls}" data-drone="{escape(r.drone_id)}" '
                f'aria-label="{escape(r.drone_id)}: {escape(STATUS_WORD[r.status])}. Open its details">'
                f'<div class="dc-top"><span class="dc-id">{escape(r.drone_id)}</span>{pill(r.status)}</div>'
                f'{drone_icon(r.status)}'
                f'<div class="dc-health-wrap">'
                f'<div class="dc-health-label"><span>Telemetry health</span><b>{pct}%</b></div>'
                f'<div class="hbar {cls}"><div class="hbar-fill" style="width:{pct}%"></div></div>'
                f'</div>'
                f'{p_badge}'
                f'<div class="dc-why">{escape(card_text(r.status, r.reason))}</div>'
                f'<div class="dc-open">SPC charts &amp; parts ›</div></button>')
        legend = (
            "<b>Can fly</b> = all SPC charts in control · "
            "<b>Warning</b> = SPC Rules 2–8 active (run/trend/zone shift) or recent signal · "
            "<b>Do not fly</b> = SPC Rule 1 (&gt; 3σ) or EWMA limit exceeded now, or crash · "
            "<b>Parts badge</b> = installed components past Weibull B10 life."
        )
        return ui.div(ui.HTML(f'<div class="hangar">{"".join(cards)}</div>'),
                      ui.HTML(f'<p class="rule-note">{legend}</p>'))

    # ---------- Drone detail pop-up (opened by clicking a drone card) ----------
    @reactive.calc
    def drone_charts_data():
        """Every chart for the selected drone, computed once by qc.py."""
        drone = selected.get()
        if not drone:
            return None
        f = flights()
        out = []
        try:
            for col, title, catches, unit, dec, kind in DRONE_CHARTS:
                s = qc.drone_series(f, drone, col)
                ch = qc.ewma_chart(s["value"]) if kind == "ewma" else qc.imr_chart(s["value"])
                out.append((kind, ch, s["flight_no"], title, catches, unit, dec))
        except ValueError as err:
            raise SafeException(f"No charts for {drone}: {err}") from None
        return out

    @render.ui
    def drone_banner():
        drone = selected.get()
        if not drone:
            return None
        row = status().set_index("drone_id").loc[drone]
        cls = STATUS_CLASS[row["status"]]
        pct = 0 if math.isnan(row["health"]) else round(row["health"] * 100)
        driver = row["health_driver"] or "none"
        return ui.div(
            ui.div(
                ui.h3(drone),
                ui.HTML(pill(row["status"])),
                ui.span(f"Telemetry health: {pct}% (tightest margin: {driver})", class_="banner-driver"),
                class_="banner-head",
            ),
            ui.HTML(f'<div class="hbar big {cls}"><div class="hbar-fill" style="width:{pct}%"></div></div>'),
            ui.p(row["reason"][0].upper() + row["reason"][1:] + "."
                 + (f" {WARNING_NOTE}" if row["status"] == "watch" else "")),
            class_=f"banner {cls}")

    @render.ui
    def drone_parts_wear():
        drone = selected.get()
        if not drone:
            return None
        mine = plan()
        mine = mine[mine["drone_id"] == drone]
        if mine.empty:
            st = status().set_index("drone_id")
            last = int(st.loc[drone, "last_flight_no"])
            return ui.HTML(
                f'<div class="banner ground"><p><b>Airframe lost in crash on flight {last}.</b> '
                "All 10 installed components were retired as crash_loss.</p></div>"
            )
        name_map = {"motor": "Motor", "propeller": "Propeller", "battery": "Battery"}
        n_over = int(mine["overdue"].sum())
        n_soon = int((~mine["overdue"] & (mine["days_left"] <= 14)).sum())
        rows = []
        for r in mine.sort_values(["overdue", "days_left"], ascending=[False, True]).itertuples():
            cls = "over" if r.overdue else "soon" if r.days_left <= 14 else "ok"
            days = round(r.days_left)
            if r.overdue:
                badge = f'<span class="pill ground">Replace now ({abs(days)}d overdue)</span>'
            elif days <= 14:
                badge = f'<span class="pill watch">Due in {days}d</span>'
            else:
                badge = f'<span class="pill go">OK ({days}d left)</span>'
            rows.append(
                f"<tr>"
                f"<td><b>{name_map[r.component_type]} {r.position}</b> "
                f"<code class='part-code'>{escape(r.component_id)}</code></td>"
                f"<td class='num'>{r.age:.0f} / {r.b10:.0f} {escape(r.unit)} ({r.pct_used:.0f}%)</td>"
                f"<td class='pcell {cls}'><div class='pbar'><div style='width:{min(r.pct_used, 100):.0f}%'></div></div></td>"
                f"<td class='num'>{badge}</td>"
                f"</tr>"
            )
        summary = (
            f"<p class='due-summary'><b>{n_over} of {len(mine)} installed parts are past their Weibull B10 life</b>"
            + (f" (plus {n_soon} due within 14 days)." if n_soon else ".")
            + " Parts past B10 carry >10% cumulative failure risk and should be replaced preventively.</p>"
        )
        table = (
            '<div class="scroll-x"><table class="numbers"><thead><tr>'
            "<th>Installed Part</th><th>Usage vs. B10 Limit</th><th>B10 Wear Bar</th><th>Action</th>"
            f"</tr></thead><tbody>{''.join(rows)}</tbody></table></div>"
        )
        return ui.HTML(summary + table)

    @render.ui
    def drone_numbers():
        data = drone_charts_data()
        if not data:
            return None
        rows = []
        for kind, ch, flight_no, title, catches, unit, dec in data:
            sig = ch["signal"] if kind == "ewma" else ch["signal_i"]
            latest = ch["z"].iloc[-1] if kind == "ewma" else ch["value"].iloc[-1]
            last = ch.iloc[-1]
            hits = flight_no.reset_index(drop=True)[(sig & ~ch["baseline"]).to_numpy()]
            first = f"flight {hits.iloc[0]}" if len(hits) else "none"
            out = bool(sig.iloc[-1])
            watch_now = bool(kind != "ewma" and "signal_watch" in ch.columns and ch["signal_watch"].iloc[-1] and not last["baseline"])
            rules_now = str(last["rules_triggered"]) if "rules_triggered" in ch.columns and last["rules_triggered"] else "none"
            name = title + (" (EWMA trend)" if kind == "ewma" else " (I chart + 8 SPC rules)")
            status_tag = " ( > 3σ GROUND)" if out else f" (SPC Rule {rules_now} WATCH)" if watch_now else ""
            rows.append(
                f"<tr><td>{escape(name)}<div class='muted-cell'>catches {escape(catches)}</div></td>"
                f'<td class="num">{last["lcl"]:.{dec}f} to {last["ucl"]:.{dec}f} {unit}</td>'
                f'<td class="num{" out" if (out or watch_now) else ""}">{latest:.{dec}f}{escape(status_tag)}</td>'
                f'<td class="num">{first}</td></tr>')
        table = ('<table class="numbers"><thead><tr><th>Measurement</th><th>3σ Control Limits</th><th>Latest Reading</th>'
                 f"<th>First >3σ Signal</th></tr></thead><tbody>{''.join(rows)}</tbody></table>")
        return ui.HTML(f'<div class="scroll-x">{table}</div>')

    # ---------- Weibull Reliability & B10 tab ----------
    @render.ui
    def rel_cards():
        cards = []
        for r in by_type().itertuples():
            name = charts.PART_TITLE.get(r.component_type, r.component_type)
            if r.note:
                cards.append(ui.div(ui.h3(name), ui.p(f"Not enough failures to fit: {r.note}."),
                                    class_="info-card"))
                continue
            cards.append(ui.div(
                ui.h3(name),
                ui.div(ui.span("Replace at B10 =", class_="rc-label"),
                       ui.span(f"{r.b10:,.0f}", class_="rc-value"),
                       ui.span(r.unit, class_="rc-unit"), class_="rc-main"),
                ui.p(f"≈ {flights_equiv(r.component_type, r.b10):,.0f} drone flights · "
                     f"Weibull β = {r.beta:.2f}, η = {r.eta:.0f} {r.unit}",
                     class_="rc-sub"),
                class_="info-card rel-card"))
        return ui.div(*cards, class_="grid-3 mb-3")

    @render.ui
    def stats_table():
        rows = "".join(
            f"<tr><td><b>{escape(charts.PART_TITLE.get(r.component_type, r.component_type))}</b></td>"
            f'<td class="num">{r.n_failed} failed / {r.n} total</td>'
            f'<td class="num">{r.beta:.2f} ({r.beta_lo:.2f}–{r.beta_hi:.2f})</td>'
            f'<td class="num">{r.eta:.0f} ({r.eta_lo:.0f}–{r.eta_hi:.0f})</td>'
            f'<td class="num"><b>{r.b10:.0f}</b></td><td class="num">{r.mean_life:.0f}</td><td>{escape(r.unit)}</td></tr>'
            for r in by_type().dropna(subset=["eta"]).itertuples())
        return ui.HTML('<div class="scroll-x"><table class="numbers"><thead><tr><th>Component Type</th><th>Censored Sample</th>'
                       "<th>Shape β (95% CI)</th><th>Characteristic Life η (95% CI)</th><th>B10 Threshold</th><th>MTTF</th><th>Unit</th>"
                       f"</tr></thead><tbody>{rows}</tbody></table></div>"
                       '<p class="rule-note">Two-parameter Weibull fitted by maximum likelihood with right-censoring. '
                       "Shape β &gt; 1 confirms wear-out (hazard rate z(t) increases with age), justifying preventive replacement at B10 = η(−ln 0.9)^(1/β).</p>")

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
    def mean_flight_min() -> float:
        return float(flights()["flight_min"].mean())

    def flights_equiv(component_type: str, b10: float) -> float:
        """Replace-at age expressed in drone flights (display only)."""
        if component_type == "battery":
            return b10 * qc.BATTERIES_PER_DRONE
        return b10 / (mean_flight_min() / 60)

    @render.ui
    def parts_by_drone():
        p = plan()
        st = status().set_index("drone_id")
        soon_days = 14
        name = {"motor": "Motor", "propeller": "Propeller", "battery": "Battery"}

        def part_rows(mine) -> str:
            rows = []
            for r in mine.sort_values(["component_type", "position"]).itertuples():
                cls = "over" if r.overdue else "soon" if r.days_left <= soon_days else "ok"
                days = round(r.days_left)
                when = ("overdue" if r.overdue else "today" if days < 1 else f"in {days} day{'s' if days != 1 else ''}")
                rows.append(f'<tr><td>{name[r.component_type]} {r.position}</td>'
                            f'<td class="num">{r.age:.0f} / {r.b10:.0f} {escape(r.unit)}</td>'
                            f'<td class="pcell {cls}"><div class="pbar"><div style="width:{min(r.pct_used, 100):.0f}%">'
                            f'</div></div></td><td class="num when {cls}">{when}</td></tr>')
            return ('<table class="mini-parts"><thead><tr><th>Part</th><th>Usage vs. B10</th><th>Life used</th><th>Replace</th></tr></thead>'
                    f'<tbody>{"".join(rows)}</tbody></table>')

        items = []
        for drone in sorted(st.index):
            mine = p[p["drone_id"] == drone]
            if mine.empty:
                last = int(st.loc[drone, "last_flight_no"])
                items.append(f'<div class="pd-item lost"><span class="pd-id">{escape(drone)}</span>'
                             f'<span class="pd-action">Lost in a crash on flight {last}: replace the drone</span></div>')
                continue
            over = mine[mine["overdue"]]
            if len(over):
                parts = ", ".join(f"{name[r.component_type].lower()} {r.position}" for r in over.itertuples())
                action = f'<b class="over-t">Replace now ({len(over)} past B10):</b> {parts}'
            else:
                r = mine.iloc[0]
                days = round(r.days_left)
                action = f"Next: {name[r.component_type].lower()} {r.position} in {days} day{'s' if days != 1 else ''}"
            items.append(f'<details class="pd-item"><summary><span class="pd-id">{escape(drone)}</span>'
                         f'<span class="pd-action">{action}</span><span class="pd-more">10 parts ▾</span></summary>'
                         f'{part_rows(mine)}</details>')
        n_over = int(p["overdue"].sum())
        summary = (f'<p class="due-summary"><b>{n_over} of {len(p)} parts in service are past their B10 replacement threshold.</b> '
                   "Expand any drone below or click its card on the Fleet Health tab.</p>")
        return ui.HTML(summary + f'<div class="pd-list">{"".join(items)}</div>')

    @render.plot
    def drone_charts():
        data = drone_charts_data()
        if not data:
            return None
        panels = []
        for kind, ch, flight_no, title, catches, unit, _ in data:
            label = f"{title}: {'trend (EWMA)' if kind == 'ewma' else 'each flight (I chart + 8 SPC rules)'}, catches {catches}"
            panels.append((kind, ch, flight_no, label, unit))
        return charts.drone_figure(panels)


app = App(app_ui, server)

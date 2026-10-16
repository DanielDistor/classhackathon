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
    "problem_fleet": ("Fleet with problems", "The main demo. D-07's motor wears out (crash on flight 95), "
                      "D-03 hits something on flight 80, and batteries from supplier lot B die early."),
    "healthy": ("Healthy fleet", "The same 10 drones with nothing wrong, for comparison: the tool "
                "should not raise alarms here."),
}
STATUS_ORDER = {"ground": 0, "watch": 1, "not enough data": 2, "go": 3}
STATUS_CLASS = {"ground": "ground", "watch": "watch", "go": "go", "not enough data": "na",
                "neutral": "neutral"}
STATUS_WORD = {"ground": "Do not fly", "watch": "Warning", "go": "Can fly", "not enough data": "Not enough data"}

# (column, chart title, what it catches, units, decimals, chart): the same three charts that set the status
DRONE_CHARTS = [
    ("temp_rise_c", "Motor temperature rise", "slow wear", "°C", 1, "ewma"),
    ("vibration_rms", "Vibration", "sudden damage, like a prop strike", "m/s²", 2, "i"),
    ("sag_rate_v_per_min", "Battery voltage drop per minute", "a failing battery", "V/min", 3, "i"),
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


WARNING_NOTE = "Often just chance: inspect at the next check."


def card_text(status: str, reason: str) -> str:
    """One short line for a drone card. Warnings say which flights looked unusual, plainly."""
    import re
    if status == "watch":
        flights = sorted({int(n) for grp in re.findall(r"flights? ([\d, ]+)", reason)
                          for n in re.findall(r"\d+", grp)})
        where = (f"on flight {flights[0]}" if len(flights) == 1
                 else f"in flights {flights[0]}–{flights[-1]}" if flights else "recently")
        return f"Unusual reading{'s' if len(flights) > 1 else ''} {where}. {WARNING_NOTE}"
    short = reason.split(";")[0]
    return short[0].upper() + short[1:] + "."






controls = ui.div(
    ui.div(ui.span("Which fleet?", class_="ctl-title"),
           ui.span("Both are invented test data: the same 10 drones flying for September 2026.", class_="ctl-sub"),
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
    """What the pop-up shows when a drone card is clicked."""
    return ui.div(
        ui.output_ui("drone_banner"),
        ui.div(ui.h4("The numbers behind the charts"), ui.output_ui("drone_numbers"), class_="panel"),
        ui.div(ui.output_plot("drone_charts", height="960px"), class_="panel"),
        ui.div(
            ui.h4("How to read these charts"),
            ui.div(ui.markdown(
                "The shaded band is the drone's first 30 flights, its **baseline**. The dashed "
                "**limits** are the baseline mean ± 3 sigma, where sigma = average moving range "
                "÷ 1.128. A red ✕ is a **signal**: a reading the drone's own normal variation is "
                "very unlikely to produce.\n\n"
                "* **Trend (EWMA)**, top chart: a running average that weights recent flights most "
                "(λ = 0.2). It catches slow wear early.\n"
                "* **Each flight (I chart)**: every reading on its own. It catches sudden changes.\n"
                "* **Temperature rise** = hottest motor after landing − air temperature, so a "
                "hot day isn't mistaken for wear."), class_="read-me"),
            class_="panel"),
    )


dashboard = ui.div(
    CLICK_JS,
    ui.div(
        ui.div(ui.input_action_button("about", "← Back to welcome page", class_="btn-back"),
               ui.span("Drone Fleet Reliability Monitor", class_="title"),
               ui.span("which drones can fly today, and why", class_="subtitle"),
               class_="topbar-left"),
        class_="topbar",
    ),
    ui.div(
        controls,
        ui.navset_pill(
            ui.nav_panel(
                "Fleet status",
                ui.div(ui.output_ui("fleet_summary"), ui.output_ui("fleet_cards"), class_="pt-3"),
            ),
            ui.nav_panel(
                "Parts replacement",
                ui.div(
                    ui.p("Replace each part at the age by which 10% of that kind of part fail (B10), worked out "
                         "from this fleet's parts history.", class_="section-note"),
                    ui.output_ui("rel_cards"),
                    ui.div(ui.h4("What to replace on each drone"),
                           ui.output_ui("parts_by_drone"),
                           class_="panel"),
                    ui.div(ui.h4("Battery batches"), ui.output_ui("lot_sentence"), class_="panel"),
                    ui.tags.details(
                        ui.tags.summary("Statistics details (Weibull fits, reliability curves, batch comparison)"),
                        ui.output_ui("stats_table"),
                        ui.output_plot("rel_curves", height="380px"),
                        ui.p("Blue = the fitted Weibull model. Gray steps = the same thing measured straight from the "
                             "data (Kaplan-Meier). When the two agree, the model fits. Red dashed line = B10, the "
                             "replace-at age.", class_="rule-note"),
                        ui.output_plot("lot_plot", height="260px"),
                        class_="panel stats-details"),
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

    selected = reactive.value(None)  # the drone whose pop-up is open

    # ---------- Fleet status tab ----------
    @render.ui
    def fleet_summary():
        st = status()
        parts = []
        for s_ in ("go", "watch", "ground"):
            n = int((st["status"] == s_).sum())
            parts.append(f'<span class="sum-item {s_}"><span class="sym">{STATUS_SYMBOL[s_]}</span>'
                         f'<b>{n}</b> {STATUS_WORD[s_].lower()}</span>')
        note = ""
        n_watch = int((st["status"] == "watch").sum())
        if input.up_flights():
            note = (f'<p class="fleet-note"><b>Showing your uploaded logbook</b> '
                    f'({len(flights()):,} flights, {st["drone_id"].nunique()} drones).</p>')
        elif input.dataset() == "healthy":
            note = ('<p class="fleet-note"><b>Nothing was planted in this fleet.</b> '
                    + (f"The {n_watch} warning{'s are' if n_watch != 1 else ' is'} ordinary chance readings: "
                       if n_watch else "")
                    + "each control limit is set so a normal reading crosses it only about 3 times in 1,000, "
                    "and the tool checks 10 drones × 3 charts over their last 10 flights (300 checks), so one or "
                    "two chance warnings are expected. No drone is marked Do not fly.</p>")
        return ui.HTML(f'<div class="fleet-summary">{"".join(parts)}'
                       f'<span class="sum-hint">Click a drone to see why.</span>{note}</div>')

    @render.ui
    def fleet_cards():
        cards = []
        for r in status().sort_values("drone_id").itertuples():
            cls = STATUS_CLASS[r.status]
            cards.append(
                f'<button class="drone-card {cls}" data-drone="{escape(r.drone_id)}" '
                f'aria-label="{escape(r.drone_id)}: {escape(STATUS_WORD[r.status])}. Open its details">'
                f'<div class="dc-top"><span class="dc-id">{escape(r.drone_id)}</span>{pill(r.status)}</div>'
                f'{drone_icon(r.status)}'
                f'<div class="dc-why">{escape(card_text(r.status, r.reason))}</div>'
                f'<div class="dc-open">Details ›</div></button>')
        legend = ("<b>Can fly</b> = every chart in control · <b>Warning</b> = a warning sign in the last 10 flights, "
                  "fly but inspect soon · <b>Do not fly</b> = a reading is out of limits now, or it crashed.")
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
        return ui.div(
            ui.div(ui.h3(drone), ui.HTML(pill(row["status"])), class_="banner-head"),
            ui.p(row["reason"][0].upper() + row["reason"][1:] + "."
                 + (f" {WARNING_NOTE}" if row["status"] == "watch" else "")),
            class_=f"banner {cls}")

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
            out = sig.iloc[-1]
            name = title + (" (trend)" if kind == "ewma" else "")
            rows.append(
                f"<tr><td>{escape(name)}<div class='muted-cell'>catches {escape(catches)}</div></td>"
                f'<td class="num">{last["lcl"]:.{dec}f} to {last["ucl"]:.{dec}f} {unit}</td>'
                f'<td class="num{" out" if out else ""}">{latest:.{dec}f}{" (outside)" if out else ""}</td>'
                f'<td class="num">{first}</td></tr>')
        table = ('<table class="numbers"><thead><tr><th>Measurement</th><th>Normal range</th><th>Latest</th>'
                 f"<th>First warning</th></tr></thead><tbody>{''.join(rows)}</tbody></table>")
        return ui.HTML(f'<div class="scroll-x">{table}</div>')

    # ---------- Parts replacement tab ----------
    @reactive.calc
    def components() -> pd.DataFrame:
        up = input.up_parts()
        try:
            c = pd.read_csv(up[0]["datapath"]) if up else pd.read_csv(DATA / input.dataset() / "components.csv")
            return qc.check_components(c)
        except (ValueError, pd.errors.ParserError) as err:
            raise SafeException(f"Can't use that parts history: {err}") from None

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
            cards.append(ui.div(
                ui.h3(name),
                ui.div(ui.span("Replace every", class_="rc-label"),
                       ui.span(f"{flights_equiv(r.component_type, r.b10):,.0f}", class_="rc-value"),
                       ui.span("flights", class_="rc-unit"), class_="rc-main"),
                ui.p(f"= {r.b10:.0f} {r.unit}"
                     + (" (each battery flies every other flight)" if r.component_type == "battery" else ""),
                     class_="rc-sub"),
                class_="info-card rel-card"))
        return ui.div(*cards, class_="grid-3 mb-3")

    @render.ui
    def stats_table():
        rows = "".join(
            f"<tr><td>{escape(charts.PART_TITLE.get(r.component_type, r.component_type))}</td>"
            f'<td class="num">{r.n_failed} of {r.n}</td>'
            f'<td class="num">{r.beta:.2f} ({r.beta_lo:.2f}–{r.beta_hi:.2f})</td>'
            f'<td class="num">{r.eta:.0f} ({r.eta_lo:.0f}–{r.eta_hi:.0f})</td>'
            f'<td class="num">{r.b10:.0f}</td><td class="num">{r.mean_life:.0f}</td><td>{escape(r.unit)}</td></tr>'
            for r in by_type().dropna(subset=["eta"]).itertuples())
        return ui.HTML('<div class="scroll-x"><table class="numbers"><thead><tr><th>Part</th><th>Failed</th>'
                       "<th>Shape β (95%)</th><th>Scale η (95%)</th><th>B10</th><th>Mean life</th><th>Unit</th>"
                       f"</tr></thead><tbody>{rows}</tbody></table></div>"
                       '<p class="rule-note">Two-parameter Weibull, maximum likelihood with right-censoring (parts '
                       "still flying count as 'lasted at least this long'). β &gt; 1 = wear-out, so replacing at B10 "
                       "prevents failures. B10 = η(−ln 0.9)^(1/β).</p>")

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

    @reactive.calc
    def mean_flight_min() -> float:
        return float(flights()["flight_min"].mean())

    def flights_equiv(component_type: str, b10: float) -> float:
        """Replace-at age expressed in drone flights (display only)."""
        if component_type == "battery":
            return b10 * qc.BATTERIES_PER_DRONE
        return b10 / (mean_flight_min() / 60)

    @reactive.calc
    def plan() -> pd.DataFrame:
        return qc.replacement_plan(components(), flights(), by_type())

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
                            f'<td class="pcell {cls}"><div class="pbar"><div style="width:{min(r.pct_used, 100):.0f}%">'
                            f'</div></div></td><td class="num when {cls}">{when}</td></tr>')
            return ('<table class="mini-parts"><thead><tr><th>Part</th><th>Life used</th><th>Replace</th></tr></thead>'
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
                action = f'<b class="over-t">Replace now ({len(over)}):</b> {parts}'
            else:
                r = mine.iloc[0]
                days = round(r.days_left)
                action = f"Next: {name[r.component_type].lower()} {r.position} in {days} day{'s' if days != 1 else ''}"
            items.append(f'<details class="pd-item"><summary><span class="pd-id">{escape(drone)}</span>'
                         f'<span class="pd-action">{action}</span><span class="pd-more">parts ▾</span></summary>'
                         f'{part_rows(mine)}</details>')
        n_over = int(p["overdue"].sum())
        summary = (f'<p class="due-summary"><b>{n_over} of {len(p)} parts in service are past their replace-at age.</b> '
                   "This fleet runs parts until they break, so many are overdue: that is the risk the tool makes visible. "
                   "Click a drone to see each of its parts.</p>")
        return ui.HTML(summary + f'<div class="pd-list">{"".join(items)}</div>')

    @render.plot
    def drone_charts():
        data = drone_charts_data()
        if not data:
            return None
        panels = []
        for kind, ch, flight_no, title, catches, unit, _ in data:
            label = f"{title}: {'trend (EWMA)' if kind == 'ewma' else 'each flight'}, catches {catches}"
            panels.append((kind, ch, flight_no, label, unit))
        return charts.drone_figure(panels)


app = App(app_ui, server)

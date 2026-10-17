import { useEffect, useState } from 'react'
import useApi from '../useApi.js'
import { getDrone } from '../api.js'
import MonitorChart, { MonitorLegend } from '../charts/MonitorChart.jsx'
import Timeline, { PART_LANES } from '../charts/Timeline.jsx'
import { Failed, HealthBar, LifeBar, Loading, Panel, Pill, Used, healthPct } from './common.jsx'
import { PART_NAME, STATUS_CLASS, cap, flightsPhrase, fmt } from '../format.js'

const CHART_WINDOW = 100

function Banner({ d }) {
  const pct = healthPct(d.health)
  return (
    <div className={`banner ${STATUS_CLASS[d.status]}`}>
      <div className="banner-head">
        <h3>{d.drone_id}</h3>
        <Pill status={d.status} />
        <span className="banner-driver">Telemetry health: {pct}% (tightest margin: {d.health_driver || 'none'})</span>
      </div>
      <HealthBar status={d.status} pct={pct} big />
      <p>{cap(d.reason)}.</p>
    </div>
  )
}

function Parts({ parts }) {
  if (!parts.length) return <p className="rule-note">No parts history loaded.</p>
  return (
    <>
      <div className="scroll-x">
        <table className="numbers">
          <thead><tr><th>Installed part</th><th>Used / replace at (B10)</th><th>Life used</th><th>Action</th></tr></thead>
          <tbody>
            {parts.map((p) => (
              <tr key={p.component_id}>
                <td><b>{PART_NAME[p.component_type]} {p.position}</b> <code className="part-code">{p.component_id}</code></td>
                <td className="num"><Used p={p} /> ({fmt(p.pct_used)}%)</td>
                <LifeBar part={p} />
                <td className="num">
                  {p.overdue ? <Pill status="ground">Replace before next flight</Pill>
                    : p.due ? <Pill status="watch">Due {flightsPhrase(p.flights_left)}</Pill>
                      : <Pill status="go">OK, {Math.round(p.flights_left)} flights left</Pill>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="rule-note">
        Flights left = (B10 − age) ÷ the drone's average flight length; a battery is charged every second flight. A part
        is warned when it reaches B10, or earlier if a chart shows it worn, and is replaced before the next flight.
      </p>
    </>
  )
}

function Numbers({ charts, nBaseline }) {
  return (
    <div className="scroll-x">
      <table className="numbers">
        <thead><tr><th>Reading</th><th>Baseline mean</th><th>3σ control limits</th><th>Latest</th><th>Flights that signalled</th><th>Restarts</th></tr></thead>
        <tbody>
          {charts.map((c) => {
            const s = c.summary
            const k = c.decimals
            return (
              <tr key={c.column}>
                <td>{c.title}<div className="muted-cell">catches {c.catches}</div></td>
                <td className="num">{fmt(s.center, k)} {c.unit}</td>
                <td className="num">{fmt(s.lcl, k)} to {fmt(s.ucl, k)}</td>
                <td className="num">{fmt(s.latest, k)}</td>
                <td className="num">{s.n_signal} ({s.n_fleet} fleet check, {s.n_rule1} rule 1, {s.n_ewma} EWMA)</td>
                <td className="num">{s.restarts}</td>
              </tr>
            )
          })}
        </tbody>
      </table>
      <p className="rule-note">Restarts count logged actions after the {nBaseline}-flight baseline.</p>
    </div>
  )
}

function ReadMe({ nBaseline }) {
  return (
    <div className="read-me">
      <p>
        The shaded band is the drone's first {nBaseline} flights, its <b>baseline</b>. While it is being collected, each
        reading is checked against the <b>fleet's normal range</b> (dash-dot, from every drone's acceptance flights; rule 1
        only, because drones differ a little from each other), so a wearing part is caught even in a new drone. The
        dashed <b>control limits</b> are the baseline mean ± 3σ, where σ̂ = average moving range ÷ 1.128; they never move.
        The orange <b>EWMA</b> weights recent flights most (λ = 0.2) to catch slow wear; its own limits are narrower because
        it averages.
      </p>
      <ul>
        <li>A red <b>✕</b> is <b>rule 1</b>: one reading beyond 3σ. An amber <b>◆</b> is one of <b>rules 2–8</b>: a pattern (9 on
          one side, 6 trending, 14 alternating, 2 of 3 beyond 2σ, 4 of 5 beyond 1σ, 15 within 1σ, 8 beyond 1σ on both sides). An
          orange ring is the EWMA beyond its limit.</li>
        <li>Each <b>thin vertical line</b> is a logged action (a part replaced, a repair, an inspection). After it the EWMA
          starts again at the center line and the rules count afresh, so a run never spans a repair.</li>
        <li>Using all 8 rules catches more problems and raises more false alarms: about 2% of readings signal with nothing
          wrong. They show here but need no action, so they are not on the timeline.</li>
        <li><b>Temperature rise</b> = hottest motor after landing − air temperature.</li>
      </ul>
    </div>
  )
}

export default function DroneModal({ droneId, onClose }) {
  const { data: d, error } = useApi(() => getDrone(droneId), droneId)
  const [showAll, setShowAll] = useState(false)

  useEffect(() => {
    const onKey = (e) => e.key === 'Escape' && onClose()
    document.addEventListener('keydown', onKey)
    document.body.style.overflow = 'hidden'
    return () => { document.removeEventListener('keydown', onKey); document.body.style.overflow = '' }
  }, [onClose])

  const lanes = d ? PART_LANES.concat(d.timeline.some((e) => e.lane === 'repairs') ? ['repairs'] : []) : []
  return (
    <div className="modal-backdrop" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div className="modal-box" role="dialog" aria-modal="true" aria-label={`Drone ${droneId} details`}>
        <button className="modal-x" onClick={onClose} aria-label="Close">×</button>
        {error && <Failed error={error} />}
        {!d && !error && <Loading what={`drone ${droneId}`} />}
        {d && (
          <>
            <Banner d={d} />
            <Panel title="Maintenance timeline"
                   note="One row per part slot. R = warned and replaced before the next flight (the part reached its replace-at age, or a chart showed it worn). F = failed in flight, replaced before the next flight. S = special cause found from a chart signal and fixed.">
              <Timeline events={d.timeline} rows={lanes} rowKey="lane" nFlights={d.n_flights} nBaseline={d.n_baseline} letters />
            </Panel>
            <Panel title="Installed parts: flights left before the replace-at age (B10)"><Parts parts={d.parts} /></Panel>
            <Panel title="Control charts">
              <Numbers charts={d.charts} nBaseline={d.n_baseline} />
              <label className="switch">
                <input type="checkbox" checked={showAll} onChange={(e) => setShowAll(e.target.checked)} />
                Show all flights (default: the latest {CHART_WINDOW})
              </label>
              <MonitorLegend />
              {d.charts.map((c) => <MonitorChart key={c.column} chart={c} last={showAll ? null : CHART_WINDOW} />)}
              <p className="rule-note">Flight number across. Thin vertical lines: the technician acted, the chart restarts. Hover a chart for each flight's numbers.</p>
            </Panel>
            <Panel title="How to read these charts"><ReadMe nBaseline={d.n_baseline} /></Panel>
            <div className="modal-foot"><button className="btn-close" onClick={onClose}>Close</button></div>
          </>
        )}
      </div>
    </div>
  )
}

import { useEffect, useState } from 'react'
import useApi from '../useApi.js'
import { getDrone } from '../api.js'
import MonitorChart, { MonitorLegend } from '../charts/MonitorChart.jsx'
import Timeline, { PART_LANES } from '../charts/Timeline.jsx'
import { Failed, HealthBar, LifeBar, Loading, Panel, Pill, Used } from './common.jsx'
import { PART_NAME, STATUS_CLASS, cap, flightsPhrase, fmt } from '../format.js'

const CHART_WINDOW = 100

function Banner({ d }) {
  const pct = Math.round(d.parts_health ?? 0)
  return (
    <div className={`banner ${STATUS_CLASS[d.status]}`}>
      <div className="banner-head">
        <h3>{d.drone_id}</h3>
        <Pill status={d.status} />
        <span className="banner-driver">Parts health: {pct}% (average life left of its 10 parts; most worn: {d.worst_part}, {Math.round(d.worst_left)}% left)</span>
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
          <thead><tr><th>Installed part</th><th>Used / replace at</th><th>Life used</th><th>Action</th></tr></thead>
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
      <p className="rule-note">Flights left = (replace-at age − age) ÷ the drone's average flight length; batteries fly every second flight.</p>
    </>
  )
}

/** One line under the reading picker: the chart's limits, latest value and how often it signalled. */
function ChartLine({ c }) {
  const s = c.summary
  const k = c.decimals
  return (
    <p className="chart-line">
      Catches {c.catches} · limits {fmt(s.lcl, k)} to {fmt(s.ucl, k)} {c.unit} (mean {fmt(s.center, k)}) · latest{' '}
      {fmt(s.latest, k)} · signalled on {s.n_signal} flights ({s.n_fleet} fleet check, {s.n_rule1} rule 1, {s.n_ewma} EWMA)
    </p>
  )
}

function ReadMe({ nBaseline }) {
  return (
    <ul className="read-me">
      <li>Shaded: the first {nBaseline} flights (baseline), checked against the fleet range.</li>
      <li>Rules 2–8: 9 on one side, 6 trending, 14 alternating, 2 of 3 beyond 2σ, 4 of 5 beyond 1σ, 15 within 1σ, 8 beyond
        1σ on both sides.</li>
      <li>Vertical lines: the technician acted; the EWMA and rules restart.</li>
      <li>Other terms (EWMA, false alarms, limits): Guide &amp; Data Reference → Key terms.</li>
    </ul>
  )
}

export default function DroneModal({ droneId, retire, onClose }) {
  const { data: d, error } = useApi(() => getDrone(droneId, retire), `${droneId}-${retire}`)
  const [showAll, setShowAll] = useState(false)
  const [reading, setReading] = useState(0)

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
            <Panel title="Maintenance timeline">
              <Timeline events={d.timeline} rows={lanes} rowKey="lane" nFlights={d.n_flights} nBaseline={d.n_baseline} letters />
            </Panel>
            <Panel title="Installed parts"><Parts parts={d.parts} /></Panel>
            <Panel title="Control chart">
              <div className="chart-controls">
                <select value={reading} onChange={(e) => setReading(Number(e.target.value))} aria-label="Reading to chart">
                  {d.charts.map((c, i) => <option key={c.column} value={i}>{c.title}</option>)}
                </select>
                <label className="switch">
                  <input type="checkbox" checked={showAll} onChange={(e) => setShowAll(e.target.checked)} />
                  All flights (default: latest {CHART_WINDOW})
                </label>
              </div>
              <ChartLine c={d.charts[reading]} />
              <MonitorLegend />
              <MonitorChart chart={d.charts[reading]} last={showAll ? null : CHART_WINDOW} />
            </Panel>
            <Panel collapsed title="How to read the chart"><ReadMe nBaseline={d.n_baseline} /></Panel>
            <div className="modal-foot"><button className="btn-close" onClick={onClose}>Close</button></div>
          </>
        )}
      </div>
    </div>
  )
}

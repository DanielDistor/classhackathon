import DroneIcon from './DroneIcon.jsx'
import Timeline from '../charts/Timeline.jsx'
import { HealthBar, LifeBar, Panel, Pill, Used } from './common.jsx'
import { PART_NAME, STATUS_CLASS, STATUS_SYMBOL, STATUS_WORD, cardText, flightsPhrase, plural } from '../format.js'

function Summary({ d }) {
  const nDue = d.plan.filter((p) => p.due).length
  const a = d.activity
  return (
    <div className="fleet-summary">
      {['go', 'watch', 'ground'].map((s) => (
        <span key={s} className={`sum-item ${s}`}>
          <span className="sym">{STATUS_SYMBOL[s]}</span>
          <b>{d.status.filter((r) => r.status === s).length}</b> {STATUS_WORD[s].toLowerCase()}
        </span>
      ))}
      <span className="sum-item parts-alert">
        <span className="sym">🔧</span><b>{nDue}</b> part{nDue !== 1 ? 's' : ''} due within {d.warn_flights} flights
      </span>
      {d.timeline.length > 0 && (
        <span className="sum-hint">
          Over flights 1–{d.n_flights}: <b>{a.replaced}</b> parts warned and replaced ({a.at_age} at their
          replace-at age, {a.by_chart} found worn by a chart), <b>{a.failed}</b> failed in flight,{' '}
          <b>{a.special}</b> special causes found and fixed.
        </span>
      )}
    </div>
  )
}

function DueSoon({ d }) {
  const up = d.plan.filter((p) => p.flights_left <= d.upcoming_flights).sort((a, b) => a.flights_left - b.flights_left)
  if (!up.length) return <p className="rule-note">No part reaches its replace-at age in the next {d.upcoming_flights} flights.</p>
  const nDue = up.filter((p) => p.due).length
  return (
    <>
      <p className="due-summary">
        As of each drone's latest flight: <b>{nDue}</b> part(s) reach their replace-at age within {d.warn_flights} flights
        and <b>{up.length - nDue}</b> more within {d.upcoming_flights}. Each is warned when it gets there and replaced
        before the next flight; this list is the heads-up so the part is in stock.
      </p>
      <div className="scroll-x">
        <table className="numbers">
          <thead><tr><th>Drone</th><th>Part</th><th>Used / replace at</th><th>Life used</th><th>Replace</th><th /></tr></thead>
          <tbody>
            {up.map((p) => (
              <tr key={p.component_id}>
                <td><b>{p.drone_id}</b></td>
                <td>{PART_NAME[p.component_type]} {p.position} <code className="part-code">{p.component_id}</code></td>
                <td className="num"><Used p={p} /></td>
                <LifeBar part={p} />
                <td className="num">{flightsPhrase(p.flights_left)}</td>
                <td>
                  {p.overdue ? <Pill status="ground">Replace before next flight</Pill>
                    : p.due ? <Pill status="watch">Have the part ready</Pill>
                      : <Pill status="go">Coming up</Pill>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  )
}

function DroneCard({ r, parts, warnFlights, onOpen }) {
  const pct = Math.round(r.parts_health ?? 0)
  const nDue = parts.filter((p) => p.due).length
  const next = [...parts].sort((a, b) => a.flights_left - b.flights_left)[0]
  return (
    <button className={`drone-card ${STATUS_CLASS[r.status]}`} onClick={() => onOpen(r.drone_id)}
            aria-label={`${r.drone_id}: ${STATUS_WORD[r.status]}. Open its details`}>
      <div className="dc-top"><span className="dc-id">{r.drone_id}</span><Pill status={r.status} /></div>
      <DroneIcon status={r.status} />
      <div className="dc-health-wrap">
        <div className="dc-health-label"><span>Parts health</span><b>{pct}%</b></div>
        <HealthBar status={r.status} pct={pct} />
      </div>
      {!next ? <div className="dc-part-alert ok">No parts history loaded</div>
        : nDue ? <div className="dc-part-alert soon">🔧 {plural(nDue, 'part')} due within {warnFlights} flights</div>
          : <div className="dc-part-alert ok">✓ Next: {next.component_type} {next.position} {flightsPhrase(next.flights_left)}</div>}
      <div className="dc-why">{cardText(r.reason)}</div>
      <div className="dc-open">Timeline, parts &amp; charts ›</div>
    </button>
  )
}

export default function FleetTab({ d, onOpen }) {
  const cards = [...d.status].sort((a, b) => a.drone_id.localeCompare(b.drone_id))
  return (
    <div className="pt-3">
      <Summary d={d} />
      <Panel title="Due soon"><DueSoon d={d} /></Panel>
      <div className="hangar">
        {cards.map((r) => (
          <DroneCard key={r.drone_id} r={r} parts={d.plan.filter((p) => p.drone_id === r.drone_id)}
                     warnFlights={d.warn_flights} onOpen={onOpen} />
        ))}
      </div>
      <p className="rule-note">
        <b>Can fly</b> = no open chart signal in the last {d.recent_flights} flights · <b>Warning</b> = a signal nobody
        has inspected yet (any of the 8 rules or the EWMA) · <b>Do not fly</b> = the latest flight is beyond 3σ or the
        EWMA is beyond its limit now: inspect first · <b>Parts health</b> = the average share of replace-at
        life (B10) the drone's 10 parts have left: 100% = all new, 0% = all due.
      </p>
      <Panel title="Fleet maintenance timeline"
             note="Every drone on one row, flight number across. R = warned and replaced before the next flight, F = failed in flight and replaced, S = special cause found and fixed. No drone stops flying. Hover a marker for the reason.">
        <Timeline events={d.timeline} rows={d.drones} rowKey="drone_id" nFlights={d.n_flights} />
      </Panel>
    </div>
  )
}


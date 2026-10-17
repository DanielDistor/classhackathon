import DroneIcon from './DroneIcon.jsx'
import Timeline from '../charts/Timeline.jsx'
import { HealthBar, LifeBar, Panel, Pill, Used } from './common.jsx'
import { PART_NAME, STATUS_CLASS, STATUS_SYMBOL, STATUS_WORD, cardText, flightsPhrase, plural } from '../format.js'

function Summary({ d }) {
  const nDue = d.plan.filter((p) => p.due).length
  const a = d.activity
  return (
    <div className="fleet-summary">
      {['ground'].map((s) => (
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
          Flights 1–{d.n_flights}: <b>{a.replaced}</b> replaced ({a.at_age} at the replace-at age, {a.by_chart} caught
          worn) · <b>{a.failed}</b> failed in flight · <b>{a.special}</b> special causes fixed
        </span>
      )}
    </div>
  )
}

const upcoming = (d) => d.plan.filter((p) => p.flights_left <= d.upcoming_flights)
  .sort((a, b) => a.flights_left - b.flights_left)

function DueSoon({ d }) {
  const up = upcoming(d)
  if (!up.length) return <p className="rule-note">Nothing reaches its replace-at age in the next {d.upcoming_flights} flights.</p>
  return (
    <>
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
      <div className="dc-top"><span className="dc-id">{r.drone_id}</span>{r.status !== 'go' && <Pill status={r.status} />}</div>
      <DroneIcon status={r.status} />
      <div className="dc-health-wrap">
        <div className="dc-health-label"><span>Health</span><b>{pct}%</b></div>
        <HealthBar status={r.status} pct={pct} />
      </div>
      {!next ? <div className="dc-part-alert ok">No parts history loaded</div>
        : nDue ? <div className="dc-part-alert soon">🔧 {plural(nDue, 'part')} due within {warnFlights} flights</div>
          : <div className="dc-part-alert ok">✓ Next: {next.component_type} {next.position} {flightsPhrase(next.flights_left)}</div>}
      {r.status !== 'go' && <div className="dc-why">{cardText(r.reason)}</div>}
      <div className="dc-open">Timeline, parts &amp; charts ›</div>
    </button>
  )
}

export default function FleetTab({ d, onOpen }) {
  const cards = [...d.status].sort((a, b) => a.drone_id.localeCompare(b.drone_id))
  const up = upcoming(d)
  const nDue = up.filter((p) => p.due).length
  return (
    <div className="pt-3">
      <Summary d={d} />
      <Panel collapsed title={`Due soon: ${up.length} part${up.length !== 1 ? 's' : ''} within ${d.upcoming_flights} flights (${nDue} within ${d.warn_flights})`}>
        <DueSoon d={d} />
      </Panel>
      <div className="hangar">
        {cards.map((r) => (
          <DroneCard key={r.drone_id} r={r} parts={d.plan.filter((p) => p.drone_id === r.drone_id)}
                     warnFlights={d.warn_flights} onOpen={onOpen} />
        ))}
      </div>
      <p className="rule-note">
        <b>Warning</b>: a signal not yet acted on · <b>Do not fly</b>: beyond the limits now · <b>Health</b>: average
        replace-at life left of the drone's 10 parts (100% = all new)
      </p>
      <Panel title="Fleet maintenance timeline">
        <Timeline events={d.timeline} rows={d.drones} rowKey="drone_id" nFlights={d.n_flights} />
      </Panel>
    </div>
  )
}


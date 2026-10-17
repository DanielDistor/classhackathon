// The guide & data reference page: what you get, how it works, the test fleet, then
// reference material folded away. Plain content: edit the wording here freely. The
// fleet numbers and example rows come from the API, so they always match the data.
import useApi from '../useApi.js'
import { getGuide } from '../api.js'
import { Failed, Loading } from './common.jsx'

const WHAT_YOU_GET = [
  ['Fleet status at a glance', 'All 10 drones on one screen: can fly, warning or do not fly, each with the reason, plus every part due for replacement soon.'],
  ['Replacement timeline', 'Every warned replacement, in-flight failure and special cause, flight by flight, for the whole fleet and for each part slot of each drone.'],
  ['Charts for any drone', 'Click a drone card for its control charts - motor temperature, vibration, battery voltage - with all 8 rules, an EWMA, and a restart at each repair.'],
]

const STEPS = [
  ['1', 'Log each flight', 'A minute of readings: the hottest motor\'s temperature, battery voltage, and numbers from the flight log. Log every part you replace.'],
  ['2', 'Compare to the drone\'s own normal', 'The first 50 flights set each drone\'s baseline; every later flight is checked against it with 8 rules and an EWMA.'],
  ['3', 'Replace before it fails', 'A part is warned when it reaches its replace-at age, or as soon as a chart shows it wearing, and swapped before the next flight. The drone keeps flying.'],
]

const PARTS = [
  ['1', 'Propellers ×4', 'The spinning blades that lift the drone.', 'When a propeller is replaced, and why (chipped, cracked, hit something).', 'components.csv'],
  ['2', 'Motors ×4', 'Spin the propellers. A worn-out motor runs hotter.', 'Right after landing: the temperature of the hottest motor, with an infrared thermometer. When a motor is replaced, and why.', 'motor_temp_max_c, components.csv'],
  ['3', 'Batteries ×2', 'Power the drone. Each drone has two and swaps them between flights. Old batteries drain faster.', 'Battery voltage at take-off and at landing (the battery displays it). When a battery is replaced, and how many charges it lasted.', 'voltage_start_v, voltage_end_v, components.csv'],
  ['4', 'Flight controller', 'The drone\'s onboard computer. It keeps a log of every flight.', 'From that log: how long the flight took, how much the drone shook, and any alert.', 'flight_min, vibration_rms, inflight_event'],
  ['5', 'Air thermometer (at the launch pad, not on the drone)', 'Hot days make every motor hotter.', 'The air temperature, so the tool can subtract it and not mistake a hot day for a worn motor.', 'ambient_temp_c'],
]

const MOMENTS = [
  ['Before take-off', 'Technician, at the launch pad', [['Battery voltage at take-off', 'voltage_start_v'], ['Air temperature', 'ambient_temp_c']]],
  ['During the flight', 'Recorded automatically by the drone\'s flight controller', [['How long it flew', 'flight_min'], ['How much it shook', 'vibration_rms'], ['Any alert: auto-return after a part failed', 'inflight_event']]],
  ['Right after landing', 'Technician, within a minute of landing', [['Hottest motor temperature (infrared thermometer)', 'motor_temp_max_c'], ['Battery voltage at landing', 'voltage_end_v']]],
]

const FLIGHT_COLS = [['flight_id', 'Flight'], ['drone_id', 'Drone'], ['datetime', 'Take-off time'], ['flight_min', 'Minutes flown'],
  ['ambient_temp_c', 'Air temp (°C)'], ['motor_temp_max_c', 'Hottest motor (°C)'], ['voltage_start_v', 'Battery at take-off (V)'],
  ['voltage_end_v', 'Battery at landing (V)'], ['vibration_rms', 'Vibration (m/s²)']]
const PART_COLS = [['component_id', 'Part'], ['drone_id', 'Drone'], ['component_type', 'Type'], ['lot', 'Batch'],
  ['install_date', 'Installed'], ['end_date', 'Removed'], ['life_value', 'Used for'], ['status', 'Failed?'], ['failure_mode', 'What happened']]

const TERMS = [
  ['Baseline', 'Each drone\'s first 50 logged flights: its own normal variation sets the limits for every later flight, and the limits never move. While they are being collected, each reading is checked against the fleet\'s normal range from acceptance flights, so a wearing part is caught from the very first flight.'],
  ['Control limits (UCL / LCL)', 'The upper and lower lines on a chart: baseline mean ± 3 sigma. A healthy drone stays between them about 99.7% of the time.'],
  ['Sigma (σ)', 'The typical flight-to-flight spread, estimated from the average jump between consecutive baseline readings ÷ 1.128.'],
  ['The 8 rules', 'Nelson / Western Electric tests on each reading: rule 1 is one point beyond 3σ; rules 2-8 are patterns (a run on one side, a trend, a zig-zag, points piling up near a limit, or readings suspiciously flat). Each points to a different kind of special cause.'],
  ['EWMA', 'Exponentially weighted moving average: a running average that weights recent flights most (λ = 0.2). Catches slow wear long before any single reading looks odd.'],
  ['Restart after a repair', 'When the technician replaces a part, repairs something or inspects a signal, that chart\'s EWMA starts again at the center line and the rules count afresh, so old readings from a removed part don\'t keep raising alarms.'],
  ['Common and special causes', 'Common cause: the ordinary flight-to-flight noise. Special cause: something that changed, such as a worn part, a strike or a loose connector. Charts separate the two.'],
  ['Temperature rise', 'Hottest motor right after landing minus the air temperature (°C). Subtracting the air temperature means a hot day isn\'t mistaken for wear.'],
  ['Voltage sag', 'Battery voltage at takeoff minus at landing, per flight minute (V/min). It rises as a battery degrades.'],
  ['Can fly / Warning / Do not fly', 'Can fly: no open signal. Warning: a signal nobody has inspected yet. Do not fly: the latest flight is beyond 3σ or the EWMA is beyond its limit now, so inspect before the next flight.'],
  ['Weibull life, B10, censored', 'A model of how long each part type lasts, fitted from the parts history. B10 = the age by which 10% have failed - the replace-at age. Censored = parts still in use or removed for another reason, counted in the fit as \'lasted at least this long\'.'],
  ['R / F / S on the timeline', 'R: warned and replaced before the next flight (the part reached its replace-at age, or a chart showed it worn). F: failed in flight, replaced before the next one. S: special cause found from a chart signal and fixed.'],
  ['False alarm', 'A chart signal with nothing wrong. With all 8 rules about 2% of readings do this. They show on the control charts but need no action, so they are not on the timeline.'],
]

const BAD_CAUSES = new Set(['prop strike', 'hard landing', 'bad battery cell'])

function DroneDiagram() {
  const [cx, cy, rp] = [380, 225, 64]
  const arms = [[268, 113], [492, 113], [492, 337], [268, 337]]
  const badge = (x, y, n) => (
    <g><circle cx={x} cy={y} r="15" className="d-badge" /><text x={x} y={y + 5} textAnchor="middle" className="d-badge-num">{n}</text></g>
  )
  return (
    <svg viewBox="0 0 760 420" role="img" className="drone-svg" aria-label="Top view of a delivery drone with its parts numbered 1 to 5">
      {arms.map(([x, y]) => <line key={`a${x}${y}`} x1={cx} y1={cy} x2={x} y2={y} className="d-arm" />)}
      {arms.map(([x, y]) => (
        <g key={`p${x}${y}`}>
          <circle cx={x} cy={y} r={rp} className="d-prop" />
          <line x1={x - 54} y1={y + 13} x2={x + 54} y2={y - 13} className="d-blade" />
        </g>
      ))}
      {arms.map(([x, y]) => <circle key={`m${x}${y}`} cx={x} cy={y} r="19" className="d-motor" />)}
      <rect x="318" y="178" width="124" height="94" rx="16" className="d-body-shape" />
      <rect x="334" y="189" width="92" height="32" rx="6" className="d-battery" />
      <text x="380" y="210" textAnchor="middle" className="d-inner">BATTERY</text>
      <rect x="356" y="230" width="48" height="32" rx="5" className="d-fc" />
      <text x="380" y="251" textAnchor="middle" className="d-inner">FC</text>
      <text x="380" y="34" textAnchor="middle" className="d-front">▲ FRONT</text>
      {['200,92 222,72', '200,350 250,343', '560,168 426,205', '560,282 404,250'].map((p) => <polyline key={p} points={p} className="d-leader" />)}
      {badge(40, 92, '1')}<text x="64" y="98" className="d-name">Propellers</text>
      {badge(40, 350, '2')}<text x="64" y="356" className="d-name">Motors</text>
      {badge(590, 168, '3')}<text x="614" y="174" className="d-name">Batteries</text>
      {badge(590, 282, '4')}<text x="614" y="280" className="d-name">Flight</text><text x="614" y="300" className="d-name">controller</text>
      {badge(590, 56, '5')}<text x="614" y="54" className="d-name">Air</text><text x="614" y="74" className="d-name">thermometer</text>
      <text x="614" y="92" className="d-sub">at the launch pad</text>
    </svg>
  )
}

function ExampleTable({ rows, cols }) {
  return (
    <div className="scroll-x">
      <table className="example">
        <thead><tr>{cols.map(([c, name]) => <th key={c}>{name}<div className="col-code">{c}</div></th>)}</tr></thead>
        <tbody>{rows.map((r, i) => <tr key={i}>{cols.map(([c]) => <td key={c}>{r[c] == null ? '' : String(r[c])}</td>)}</tr>)}</tbody>
      </table>
    </div>
  )
}

function FleetTimeline({ events, n }) {
  const marks = events.map((e) => ({
    f: e.start_flight,
    cls: BAD_CAUSES.has(e.cause) ? 'bad' : 'wear',
    label: `${e.drone_id}: ${e.cause} (rule ${e.rule_shape} shape), caught after flight ${e.detected_after_flight} by ${e.detected_by}`,
  })).sort((a, b) => a.f - b.f)
  return (
    <>
      <div className="tl">
        <div className="tl-bar" />
        {marks.map((m, i) => <span key={i} className={`tl-dot ${m.cls}`} style={{ left: `${((m.f - 1) / (n - 1)) * 100}%` }} />)}
        <div className="tl-ends"><span>flight 1</span><span>flight {n}</span></div>
      </div>
      <ul className="tl-list">
        {marks.map((m, i) => <li key={i}><span className={`tl-dot ${m.cls}`} /><b>Flight {m.f}</b> {m.label}</li>)}
      </ul>
    </>
  )
}

function FleetCard({ g }) {
  return (
    <div className="info-card scenario">
      <div className="card-head"><span className="tag">Test fleet</span><code>data/fleet/</code></div>
      <h3>10 drones, {g.n_rows.toLocaleString('en-US')} flights, Jul–Sep 2026</h3>
      <p className="mini-cap">The {g.events.length} special causes injected at random (the simulation's answer key)</p>
      <FleetTimeline events={g.events} n={g.n_flights} />
      <dl className="scenario-dl">
        <dt>What happens</dt>
        <dd>Every part wears out at its own random Weibull life, and in its last stretch it pushes one reading up (motor →
          temperature, propeller → vibration, battery → voltage sag). On top of that, the special causes above strike random
          drones. Nothing is scripted on a named drone.</dd>
        <dt>What the technician did</dt>
        <dd>{g.n_scheduled} parts warned at their replace-at age and {g.n_worn} warned early because a chart showed them
          wearing (including in each drone's first {g.n_baseline} flights, checked against the fleet's normal range), each
          replaced before the next flight.{' '}
          {g.n_failed ? `${g.n_failed} failed in flight and were replaced before the next flight. ` : 'No part failed in flight. '}
          No drone ever stopped flying.</dd>
        <dt>What the tool should show</dt>
        <dd>Every special cause above is signalled, on the flight listed. Run on these files, the tool signals on exactly the
          flights where the technician acted - checked for all 30 drone charts in the tests.</dd>
      </dl>
    </div>
  )
}

const Fold = ({ summary, children }) => (
  <details className="fold"><summary>{summary}</summary><div className="fold-body">{children}</div></details>
)

export default function Guide({ onEnter }) {
  const { data: g, error } = useApi(getGuide, 'guide')
  const parts = g && g.example_parts.map((p) => ({
    ...p,
    status: p.status === 1 ? 'yes' : 'no (still OK)',
    end_date: p.end_date ?? '(still in use)',
    life_value: `${p.life_value} ${p.component_type === 'battery' ? 'charges' : 'flight hours'}`,
  }))
  return (
    <div className="intro">
      <div className="hero">
        <div className="intro-wrap">
          <p className="eyebrow">Six Sigma Hackathon · Team Flight Control</p>
          <h1>Drone Fleet Reliability Monitor</h1>
          <p className="lede">Catch wear before it becomes a mid-air failure. Every morning, the fleet maintenance technician
            sees which of the 10 drones can fly, which parts to swap next - and why.</p>
          <div className="hero-stats">
            <span className="stat-chip">10 drones</span><span className="stat-chip">3,000 flights</span>
            <span className="stat-chip">every replacement logged</span>
          </div>
          <div className="hero-cta">
            <button className="btn-hero" onClick={onEnter}>Open the dashboard  →</button>
            <span className="hero-hint">or read on - everything below explains what you will see</span>
          </div>
        </div>
      </div>
      <div className="intro-wrap intro-body">
        <h2>What you get</h2>
        <div className="grid-3">{WHAT_YOU_GET.map(([n, d]) => <div key={n} className="info-card tab-card"><h3>{n}</h3><p>{d}</p></div>)}</div>

        <h2>How it works</h2>
        <div className="grid-3">{STEPS.map(([n, t, b]) => <div key={n} className="step"><span className="step-num">{n}</span><h3>{t}</h3><p>{b}</p></div>)}</div>

        <h2>The test fleet</h2>
        <div className="callout">
          <p><strong>One invented fleet, flying for three months.</strong> Parts wear out and get replaced, and random problems
            strike - the kind a real delivery fleet sees. Because we generated it, we know every problem we put in, so we can
            check the tool catches each one, like testing a smoke alarm with real smoke.</p>
        </div>
        {error && <Failed error={error} />}
        {!g && !error && <Loading what="the test fleet" />}
        {g && <FleetCard g={g} />}

        <h2>The data, from the drone up</h2>
        <p className="section-note">We don't have a real startup's records, so we invented realistic ones: one small delivery
          fleet flying for three months.</p>
        <Fold summary="The drone and the 5 things the technician measures">
          <div className="diagram-card">
            <DroneDiagram />
            <table className="parts">
              <thead><tr><th /><th>Part</th><th>What the technician writes down</th><th>Column in the data</th></tr></thead>
              <tbody>
                {PARTS.map(([n, part, what, rec, cols]) => (
                  <tr key={n}><td><span className="num-badge">{n}</span></td><td><strong>{part}</strong><div className="muted">{what}</div></td>
                    <td>{rec}</td><td><code>{cols}</code></td></tr>
                ))}
              </tbody>
            </table>
          </div>
        </Fold>
        <Fold summary="One flight, three moments">
          <p className="section-note">Every line of the flight logbook is one whole flight, with readings from before, during and after it.</p>
          <div className="grid-3 moments">
            {MOMENTS.map(([when, who, items], i) => (
              <div key={when} className="info-card moment">
                <div className="moment-head"><span className="step-num">{i + 1}</span><h3>{when}</h3></div>
                <p className="moment-who">{who}</p>
                <ul className="moment-list">{items.map(([w, c]) => <li key={c}>{w}<code>{c}</code></li>)}</ul>
              </div>
            ))}
          </div>
        </Fold>
        <Fold summary="Example rows from the data files">
          {g && (
            <div className="stack">
              <div className="info-card"><h3>flights.csv: the flight logbook</h3>
                <p>One line per flight - here, the first 3 flights of D-01. The gray text under each heading is the column's name in the file.</p>
                <ExampleTable rows={g.example_flights} cols={FLIGHT_COLS} /></div>
              <div className="info-card"><h3>components.csv: the parts history</h3>
                <p>One line per part, from install to failure, removal or today - three examples from that table.</p>
                <ExampleTable rows={parts} cols={PART_COLS} /></div>
            </div>
          )}
        </Fold>

        <h2>Key terms</h2>
        <Fold summary="Open the key terms (baseline, sigma, signal, EWMA, B10 ...)">
          <div className="terms">{TERMS.map(([t, d]) => <div key={t} className="term"><dt>{t}</dt><dd>{d}</dd></div>)}</div>
        </Fold>

        <div className="continue-row">
          <button className="btn-continue" onClick={onEnter}>Continue to the dashboard  →</button>
          <p className="section-note">You can come back to this page any time from the header.</p>
        </div>
      </div>
    </div>
  )
}

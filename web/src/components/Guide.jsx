// The guide & data reference page: what you get, how it works, the test fleet, then
// reference material folded away. Plain content: edit the wording here freely. The
// fleet numbers and example rows come from the API, so they always match the data.
import useApi from '../useApi.js'
import { getGuide } from '../api.js'
import { Failed, Loading } from './common.jsx'

const WHAT_YOU_GET = [
  ['Fleet status', 'Every drone: can fly, warning or do not fly, with the reason and the next part due.'],
  ['Maintenance timeline', 'Every replacement, failure and special cause, flight by flight, per drone and per part.'],
  ['Retirement slider', 'Pick when parts retire (B1 to B30) and see how many parts it costs and how many close calls it leaves.'],
]

const STEPS = [
  ['1', 'Log each flight', 'A minute of readings after landing; log every part you replace.'],
  ['2', 'Check against normal', 'Each drone\'s first 50 flights set its limits; every later flight is tested with 8 rules and an EWMA.'],
  ['3', 'Replace before it fails', 'A warning (replace-at age reached, or a chart shows wear) means swap the part before the next flight.'],
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
  ['Baseline', 'A drone\'s first 50 flights. They set its limits, which never move. Meanwhile readings are checked against the fleet\'s range (rule 1 only).'],
  ['Control limits', 'Baseline mean ± 3σ, with σ = average jump between consecutive readings ÷ 1.128. A healthy drone stays inside 99.7% of the time.'],
  ['The 8 rules', 'Rule 1: one point beyond 3σ. Rules 2–8: patterns (a run on one side, a trend, a zig-zag, points near a limit, too flat).'],
  ['EWMA', 'A running average weighted to recent flights (λ = 0.2); catches slow wear early.'],
  ['Restart', 'After any logged action the EWMA and the rules start again; the limits stay.'],
  ['Special cause', 'Something that changed (a worn part, a strike, a loose connector), as opposed to ordinary flight-to-flight noise.'],
  ['False alarm', 'A signal with nothing wrong: about 2% of readings with all 8 rules. Shown on the charts, no action needed.'],
  ['Temperature rise / voltage sag', 'Hottest motor − air temperature; voltage drop per flight minute.'],
  ['B_p (replace-at age)', 'The age by which p% of a part type fails, from a Weibull fit with censoring. The slider picks p; the default is B10.'],
  ['R / F / S', 'Warned and replaced / failed in flight / special cause fixed (filled ◆ = part replaced, hollow ◇ = repaired, no part). All before the next flight.'],
]


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
    cls: e.fix === 'repaired' ? 'wear' : 'bad',   // red: a part was replaced; brown: repaired
    label: `${e.drone_id}: ${e.cause} (rule ${e.rule_shape} shape), caught after flight ${e.detected_after_flight} by ${e.detected_by}`,
  })).sort((a, b) => a.f - b.f)
  return (
    <>
      <div className="tl">
        <div className="tl-bar" />
        {marks.map((m, i) => <span key={i} className={`tl-dot ${m.cls}`} style={{ left: `${((m.f - 1) / (n - 1)) * 100}%` }} />)}
        <div className="tl-ends"><span>flight 1</span><span>flight {n}</span></div>
      </div>
      <p className="tl-legend"><span className="tl-dot bad" /> part replaced · <span className="tl-dot wear" /> repaired, no new
        part · each dot sits on the flight the problem started</p>
      <ul className="tl-list">
        {marks.map((m, i) => <li key={i}><span className={`tl-dot ${m.cls}`} /><b>Flight {m.f}</b> {m.label}</li>)}
      </ul>
    </>
  )
}

function FleetCard({ g }) {
  return (
    <div className="info-card scenario">
      <div className="card-head"><span className="tag">{g.dataset_name}</span><code>data/{g.dataset}/</code></div>
      <h3>10 drones, {g.n_rows.toLocaleString('en-US')} flights, Jul–Sep 2026</h3>
      <p className="mini-cap">The {g.events.length} special causes injected at random (the simulation's answer key)</p>
      <FleetTimeline events={g.events} n={g.n_flights} />
      <dl className="scenario-dl">
        <dt>What happens</dt>
        <dd>Each part wears out at its own random life and, near the end, pushes one reading up (motor → temperature,
          propeller → vibration, battery → voltage sag). The special causes above strike at random.</dd>
        <dt>What the technician did (B10)</dt>
        <dd>{g.n_scheduled} parts replaced at their replace-at age, {g.n_worn} caught worn by a chart.{' '}
          {g.n_failed ? `${g.n_failed} failed in flight.` : 'None failed in flight.'} No drone stopped flying.</dd>
        <dt>Check</dt>
        <dd>Every special cause is caught, and the tool signals on exactly the flights where the technician acted (tested).</dd>
      </dl>
    </div>
  )
}

const Fold = ({ summary, children }) => (
  <details className="fold"><summary>{summary}</summary><div className="fold-body">{children}</div></details>
)

export default function Guide({ dataset, onEnter }) {
  const { data: g, error } = useApi(() => getGuide(dataset), `guide-${dataset}`)
  const parts = g && g.example_parts.map((p) => ({
    ...p,
    status: p.status === 1 ? 'yes' : 'no (still OK)',
    end_date: p.end_date ?? '(still in use)',
    life_value: `${p.life_value} ${p.component_type === 'battery' ? 'charges' : 'flight hours'}`,
  }))
  return (
    <div className="intro welcome-fit">
      <div className="hero">
        <div className="intro-wrap">
          <h1>Drone Fleet Reliability Monitor</h1>
          <p className="lede">Catch wear before it becomes a mid-air failure. Every morning, the fleet maintenance technician
            sees which of the 10 drones can fly, which parts to swap next - and why.</p>
          <div className="hero-cta">
            <button className="btn-hero" onClick={onEnter}>Open the dashboard  →</button>
          </div>
        </div>
      </div>
      <div className="intro-wrap intro-body">
        <div className="welcome-split">
          <div className="welcome-boxes">
            <section className="welcome-box">
              <h2>The problem</h2>
              <p>A drone delivery startup is experiencing mid-air failures, but it only investigates after a crash.
                Technicians need a way to log wear and tear before and during each flight, and to use it to manage and
                improve the fleet's reliability.</p>
            </section>
            <section className="welcome-box">
              <h2>What the dashboard does</h2>
              <ul className="welcome-list">{WHAT_YOU_GET.map(([n, d]) => <li key={n}><b>{n}:</b> {d}</li>)}</ul>
            </section>
            <section className="welcome-box">
              <h2>How it works</h2>
              <ol className="welcome-list">{STEPS.map(([n, t, b]) => <li key={n}><b>{t}:</b> {b}</li>)}</ol>
            </section>
          </div>
          <figure className="welcome-drone">
            <DroneDiagram />
            <figcaption>The parts the tool tracks</figcaption>
          </figure>
        </div>

        <div className="welcome-folds">
        <span className="welcome-more">More details</span>
        <Fold summary="Test fleet">
          <div className="callout">
            <p><strong>Invented data, on purpose.</strong> Because we generated the fleet, we know every problem in it and can
              check the tool catches each one, like testing a smoke alarm with real smoke.</p>
          </div>
          {error && <Failed error={error} />}
          {!g && !error && <Loading what="the test fleet" />}
          {g && <FleetCard g={g} />}
        </Fold>
        <Fold summary="What is measured">
          <table className="parts">
            <thead><tr><th /><th>Part</th><th>What the technician writes down</th><th>Column in the data</th></tr></thead>
            <tbody>
              {PARTS.map(([n, part, what, rec, cols]) => (
                <tr key={n}><td><span className="num-badge">{n}</span></td><td><strong>{part}</strong><div className="muted">{what}</div></td>
                  <td>{rec}</td><td><code>{cols}</code></td></tr>
              ))}
            </tbody>
          </table>
        </Fold>
        <Fold summary="One flight">
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
        <Fold summary="Example rows">
          {g && (
            <div className="stack">
              <div className="info-card"><h3>flights.csv: the flight logbook</h3>
                <p>One line per flight (the first 3 of D-01); gray text = the column name.</p>
                <ExampleTable rows={g.example_flights} cols={FLIGHT_COLS} /></div>
              <div className="info-card"><h3>components.csv: the parts history</h3>
                <p>One line per part, from install to removal or today.</p>
                <ExampleTable rows={parts} cols={PART_COLS} /></div>
            </div>
          )}
        </Fold>

        <Fold summary="Key terms">
          <div className="terms">{TERMS.map(([t, d]) => <div key={t} className="term"><dt>{t}</dt><dd>{d}</dd></div>)}</div>
        </Fold>

        </div>
      </div>
    </div>
  )
}

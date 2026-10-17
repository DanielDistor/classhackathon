import { useState } from 'react'
import useApi from '../useApi.js'
import { getReliability } from '../api.js'
import ReliabilityChart from '../charts/ReliabilityChart.jsx'
import { Failed, LifeBar, Loading, Panel, Used } from './common.jsx'
import { PART_NAME, PART_TITLE, flightsPhrase, fmt, partClass } from '../format.js'

function RelCards({ fits, retire }) {
  return (
    <div className="grid-3 mb-3">
      {fits.map((r) => (
        <div key={r.component_type} className="info-card rel-card">
          <h3>{PART_TITLE[r.component_type]}</h3>
          {r.note ? <p>Not enough failures to fit: {r.note}.</p> : (
            <>
              <div className="rc-main">
                <span className="rc-label">Replace at B{retire} =</span>
                <span className="rc-value">{fmt(r.replace_at)}</span>
                <span className="rc-unit">{r.unit}</span>
              </div>
              <p className="rc-sub">≈ {fmt(r.replace_at_flights)} flights · fit on all data: β = {fmt(r.beta, 2)}, η = {fmt(r.eta)}</p>
            </>
          )}
        </div>
      ))}
    </div>
  )
}

function StatsTable({ fits }) {
  return (
    <>
      <div className="scroll-x">
        <table className="numbers">
          <thead><tr><th>Component type</th><th>Censored sample</th><th>Shape <span className="greek">β</span> (95% CI)</th><th>Characteristic life <span className="greek">η</span> (95% CI)</th><th>B10</th><th>MTTF</th><th>Unit</th></tr></thead>
          <tbody>
            {fits.filter((r) => r.eta != null).map((r) => (
              <tr key={r.component_type}>
                <td><b>{PART_TITLE[r.component_type]}</b></td>
                <td className="num">{r.n_failed} failed / {r.n} total</td>
                <td className="num">{fmt(r.beta, 2)} ({fmt(r.beta_lo, 2)}–{fmt(r.beta_hi, 2)})</td>
                <td className="num">{fmt(r.eta)} ({fmt(r.eta_lo)}–{fmt(r.eta_hi)})</td>
                <td className="num"><b>{fmt(r.b10)}</b></td>
                <td className="num">{fmt(r.mean_life)}</td>
                <td>{r.unit}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="rule-note">
        Maximum likelihood with right-censoring: a part found worn counts as a failure; damaged, retired or still-flying
        parts are censored. β &gt; 1 means wear-out, which is why retiring early pays off.
      </p>
    </>
  )
}

function PartsByDrone({ plan, warnFlights }) {
  const drones = [...new Set(plan.map((p) => p.drone_id))].sort()
  return (
    <div className="pd-list">
      {drones.map((drone) => {
        const mine = plan.filter((p) => p.drone_id === drone)
        const due = mine.filter((p) => p.due)
        const next = [...mine].sort((a, b) => a.flights_left - b.flights_left)[0]
        const rows = [...mine].sort((a, b) => a.component_type.localeCompare(b.component_type) || a.position - b.position)
        return (
          <details key={drone} className="pd-item">
            <summary>
              <span className="pd-id">{drone}</span>
              <span className="pd-action">
                {due.length ? <><b className="over-t">Due within {warnFlights} flights ({due.length}):</b>{' '}
                  {due.map((p) => `${p.component_type} ${p.position}`).join(', ')}</>
                  : `Next: ${next.component_type} ${next.position} ${flightsPhrase(next.flights_left)}`}
              </span>
              <span className="pd-more">{mine.length} parts ▾</span>
            </summary>
            <table className="mini-parts">
              <thead><tr><th>Part</th><th>Used / B10</th><th>Life used</th><th>Replace</th></tr></thead>
              <tbody>
                {rows.map((p) => (
                  <tr key={p.component_id}>
                    <td>{PART_NAME[p.component_type]} {p.position}</td>
                    <td className="num"><Used p={p} /></td>
                    <LifeBar part={p} />
                    <td className={`num when ${partClass(p)}`}>{flightsPhrase(p.flights_left)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </details>
        )
      })}
    </div>
  )
}

export default function ReliabilityTab({ retire, dataset }) {
  const { data: d, error } = useApi(() => getReliability(retire, dataset), `rel-${dataset}-${retire}`)
  const [type, setType] = useState('propeller')
  if (error) return <Failed error={error} />
  if (!d) return <Loading what="the Weibull fits" />
  const curve = d.curves.find((c) => c.type === type) || d.curves[0]
  return (
    <div className="pt-3">
      <p className="section-note">
        Each part type's life, R(t) = exp(−(t/η)^β). Parts retire at B{retire}: the age by which {retire}% of that type
        fails. The replace-at ages come from the parts history before the log.
      </p>
      <RelCards fits={d.fits} retire={retire} />
      <Panel title="Reliability curve: Weibull fit vs. the data (Kaplan-Meier)">
        <div className="chart-controls">
          <select value={curve.type} onChange={(e) => setType(e.target.value)} aria-label="Part type">
            {d.curves.map((c) => <option key={c.type} value={c.type}>{PART_TITLE[c.type]}</option>)}
          </select>
        </div>
        <ReliabilityChart curve={curve} retire={retire} />
      </Panel>
      <Panel collapsed title="Fitted parameters and 95% confidence intervals"><StatsTable fits={d.fits} /></Panel>
      <Panel collapsed title="Replacement schedule, every drone"><PartsByDrone plan={d.plan} warnFlights={d.warn_flights} /></Panel>
    </div>
  )
}

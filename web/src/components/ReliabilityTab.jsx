import useApi from '../useApi.js'
import { getReliability } from '../api.js'
import ReliabilityChart from '../charts/ReliabilityChart.jsx'
import { Failed, LifeBar, Loading, Panel, Used } from './common.jsx'
import { PART_NAME, PART_TITLE, flightsPhrase, fmt, partClass } from '../format.js'

function RelCards({ fits }) {
  return (
    <div className="grid-3 mb-3">
      {fits.map((r) => (
        <div key={r.component_type} className="info-card rel-card">
          <h3>{PART_TITLE[r.component_type]}</h3>
          {r.note ? <p>Not enough failures to fit: {r.note}.</p> : (
            <>
              <div className="rc-main">
                <span className="rc-label">Replace at B10 =</span>
                <span className="rc-value">{fmt(r.replace_at)}</span>
                <span className="rc-unit">{r.unit}</span>
              </div>
              <p className="rc-sub">
                ≈ {fmt(r.replace_at_flights)} drone flights · the shop's schedule, fitted before the log. Refit on all data
                now: B10 = {fmt(r.b10)}, β = {fmt(r.beta, 2)}, η = {fmt(r.eta)}
              </p>
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
        Two-parameter Weibull fitted by maximum likelihood with right-censoring. A part found worn at inspection counts as a
        (potential) failure; a part damaged by a special cause, replaced on schedule or still flying counts as censored.
        Shape β &gt; 1 means wear-out (the failure rate rises with age), which is what makes replacing at
        B10 = η(−ln 0.9)^(1/β) worthwhile.
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

export default function ReliabilityTab() {
  const { data: d, error } = useApi(getReliability, 'rel')
  if (error) return <Failed error={error} />
  if (!d) return <Loading what="the Weibull fits" />
  return (
    <div className="pt-3">
      <p className="section-note">
        Weibull survival models R(t) = exp(−(t/η)^β) fitted by maximum likelihood with right-censoring. Each part is
        replaced at B10, the age by which 10% of parts fail (R(B10) = 90%): the warning fires when a part reaches it, and
        the part is replaced before the next flight. The schedule uses the shop's replace-at ages, fitted on the parts
        history before the log; the refit on all data is shown next to them.
      </p>
      <RelCards fits={d.fits} />
      <Panel title="Weibull reliability curves R(t) vs. Kaplan-Meier survival from the data">
        <ReliabilityChart curves={d.curves} />
        <p className="rule-note">Blue curve = fitted two-parameter Weibull R(t). Gray steps = Kaplan-Meier estimate from the same censored data, no model. Red dashed line = B10.</p>
      </Panel>
      <Panel title="Fitted Weibull parameters & 95% confidence intervals"><StatsTable fits={d.fits} /></Panel>
      <Panel title="Replacement schedule, every drone"><PartsByDrone plan={d.plan} warnFlights={d.warn_flights} /></Panel>
    </div>
  )
}

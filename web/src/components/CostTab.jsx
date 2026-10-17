import { useEffect, useState } from 'react'
import useApi from '../useApi.js'
import { getCost } from '../api.js'
import { COLORS as C, linear, linePath, niceTicks } from '../charts/scale.js'
import { Failed, Loading, Panel } from './common.jsx'
import { PART_TITLE, fmt } from '../format.js'

// Estimates: planned = part + labour + downtime; failure = a crashed drone, its package and recovery.
const DEFAULTS = { motor: [280, 6000], propeller: [75, 6000], battery: [300, 6000] }
const asText = (c) => Object.fromEntries(Object.entries(c).map(([k, v]) => [k, v.map(String)]))
const asNumbers = (c) => Object.fromEntries(Object.entries(c).map(([k, v]) => [k, v.map(Number)]))
const money = (x, d = 0) => `$${fmt(x, d)}`

/** Cost per drone-flight vs the retirement %: the age-only model (line) and the simulated runs with the charts (dots). */
function CostChart({ d, retire }) {
  const W = 1000
  const H = 300
  const M = { top: 20, right: 24, bottom: 40, left: 64 }
  const xs = d.model_total.map((r) => r.retire_pct)
  const yMax = Math.max(...d.model_total.map((r) => r.cost_per_flight), ...d.runs.map((r) => r.cost_per_flight)) * 1.08
  const x = linear([0, Math.max(...xs)], [M.left, W - M.right])
  const y = linear([0, yMax], [H - M.bottom, M.top])
  return (
    <figure className="svg-chart">
      <div className="svg-wrap">
        <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label="Cost per drone-flight against the retirement percentage">
          <rect x={M.left} y={M.top} width={W - M.left - M.right} height={H - M.top - M.bottom} fill={C.surface} />
          {niceTicks(0, yMax, 5).map((t) => (
            <g key={t}>
              <line x1={M.left} x2={W - M.right} y1={y(t)} y2={y(t)} stroke={C.grid} />
              <text x={M.left - 8} y={y(t) + 4} textAnchor="end" className="tick">${fmt(t, 2)}</text>
            </g>
          ))}
          {niceTicks(0, Math.max(...xs), 8).map((t) => (
            <text key={t} x={x(t)} y={H - 20} textAnchor="middle" className="tick">{t}%</text>
          ))}
          <text x={(M.left + W - M.right) / 2} y={H - 4} textAnchor="middle" className="tick">retire at B_p: p = share of parts that would fail first</text>
          <line x1={x(retire)} x2={x(retire)} y1={M.top} y2={H - M.bottom} stroke={C.ink2} strokeDasharray="4 4" />
          <text x={x(retire) + 6} y={M.top + 14} className="tick">slider: B{retire}</text>
          <path d={linePath(xs, d.model_total.map((r) => r.cost_per_flight), x, y)} fill="none" stroke={C.series} strokeWidth={2.4} />
          <circle cx={x(d.best_pct)} cy={y(d.best_cost)} r={7} fill="none" stroke={C.critical} strokeWidth={2} />
          <text x={x(d.best_pct) + 10} y={y(d.best_cost) - 10} className="tick b10">lowest cost with no charts: replace at {fmt(d.best_pct, d.best_pct % 1 ? 1 : 0)}% → {money(d.best_cost, 2)} per flight</text>
          <path d={linePath(d.runs.map((r) => r.retire_pct), d.runs.map((r) => r.cost_per_flight), x, y)} fill="none" stroke={C.ewma} strokeWidth={1.2} opacity={0.5} />
          {d.runs.map((r) => <circle key={r.retire_pct} cx={x(r.retire_pct)} cy={y(r.cost_per_flight)} r={5} fill={C.ewma} stroke={C.surface} />)}
        </svg>
      </div>
      <ul className="chart-legend">
        <li><svg width="22" height="10"><line x1="0" x2="22" y1="5" y2="5" stroke={C.series} strokeWidth="2.5" /></svg>no charts: replace by age only, and p% of parts fail in flight first (Weibull model)</li>
        <li><svg width="14" height="14"><circle cx="7" cy="7" r="5" fill={C.ewma} /></svg>with charts: actual parts cost in the simulation (worn parts caught on the ground, no failures)</li>
      </ul>
    </figure>
  )
}

/** The headline: the cheapest choice without charts against the charts at the current setting, and the saving.
 *  (Not no-charts at the same setting: nobody without charts would pick it, so that would overstate the saving.) */
function Savings({ d, retire }) {
  const r = d.runs.find((x) => x.retire_pct === retire)
  if (!r) return null
  const save = d.best_cost - r.cost_per_flight
  const best = fmt(d.best_pct, d.best_pct % 1 ? 1 : 0)
  return (
    <div className="savings">
      <div><span className="sv-label">No charts: cheapest choice, replace at {best}%</span><span className="sv-value">{money(d.best_cost, 2)}</span><span className="sv-unit">per drone-flight</span></div>
      <div><span className="sv-label">With charts: replace at {retire}% (slider)</span><span className="sv-value">{money(r.cost_per_flight, 2)}</span><span className="sv-unit">per drone-flight</span></div>
      <div className={save > 0 ? 'sv-save' : ''}><span className="sv-label">{save > 0 ? 'The charts save' : 'Extra cost'}</span><span className="sv-value">{money(Math.abs(save) * r.n_flights)}</span><span className="sv-unit">over these {fmt(r.n_flights)} flights ({money(Math.abs(save), 2)} each)</span></div>
    </div>
  )
}

/** One row per slider setting: what each run used, and both costs. */
function Table({ d, retire }) {
  return (
    <div className="scroll-x">
      <table className="numbers">
        <thead><tr><th>Replace at</th><th>Parts replaced</th><th>of which caught worn</th><th>Failed in flight</th><th>No charts ($/flight)</th><th>With charts ($/flight)</th></tr></thead>
        <tbody>
          {d.runs.map((r) => (
            <tr key={r.retire_pct} className={r.retire_pct === retire ? 'row-on' : ''}>
              <td>B{r.retire_pct}</td><td className="num">{r.planned}</td><td className="num">{r.caught_worn}</td>
              <td className="num">{r.failed}</td><td className="num">{fmt(r.no_charts_per_flight, 2)}</td>
              <td className="num">{fmt(r.cost_per_flight, 2)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="rule-note">"Caught worn" are the parts the no-charts line counts as failures: without charts they would have
        failed in flight. Special-cause repairs are the same at every setting and left out.</p>
    </div>
  )
}

/**
 * The Cost & savings tab: the age-replacement model (qc.retirement_cost) without charts against the
 * simulated runs with charts, at editable estimated prices.
 */
export default function CostTab({ dataset, retire }) {
  const [draft, setDraft] = useState(() => asText(DEFAULTS))     // what is typed, as text
  const [costs, setCosts] = useState(DEFAULTS)
  useEffect(() => {                              // refetch shortly after typing stops
    const t = setTimeout(() => setCosts(asNumbers(draft)), 500)
    return () => clearTimeout(t)
  }, [draft])
  const valid = Object.values(costs).every(([cp, cf]) => cp > 0 && cf > 0)
  const { data: d, error } = useApi(() => getCost(dataset, costs), `cost-${dataset}-${JSON.stringify(costs)}`)
  // typing only: keep digits and one decimal point
  const clean = (v) => v.replace(/[^0-9.]/g, '').replace(/(\..*)\./g, '$1')
  const set = (type, i, v) => setDraft({ ...draft, [type]: draft[type].map((x, j) => (j === i ? clean(v) : x)) })
  return (
    <div className="pt-3">
      {valid && d && <Savings d={d} retire={retire} />}
      <Panel title="Prices (estimates: change them to your own)">
        <div className="scroll-x">
          <table className="numbers cost-inputs">
            <thead><tr><th>$</th>{Object.keys(DEFAULTS).map((t) => <th key={t}>{PART_TITLE[t]}</th>)}</tr></thead>
            <tbody>
              {[['Planned replacement (part + labour + downtime)', 0], ['Failure in flight (drone, package, recovery)', 1]].map(([label, i]) => (
                <tr key={label}>
                  <td>{label}</td>
                  {Object.keys(DEFAULTS).map((t) => (
                    <td key={t}><input type="text" inputMode="decimal" value={draft[t][i]} onChange={(e) => set(t, i, e.target.value)}
                                       aria-label={`${label}, ${t}`} /></td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {!valid && <p className="rule-note">Every price must be above 0.</p>}
      </Panel>
      {valid && error && <Failed error={error} />}
      {valid && !d && !error && <Loading what="the costs" />}
      {valid && d && (
        <>
          <Panel title="Cost per drone-flight by retirement setting"><CostChart d={d} retire={retire} /></Panel>
          <Panel collapsed title="Every setting in numbers"><Table d={d} retire={retire} /></Panel>
        </>
      )}
    </div>
  )
}

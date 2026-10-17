import { useEffect, useState } from 'react'
import useApi from '../useApi.js'
import { getCost } from '../api.js'
import { COLORS as C, linear, linePath, niceTicks } from '../charts/scale.js'
import { Failed, Loading } from './common.jsx'
import { PART_TITLE, fmt } from '../format.js'

const DEFAULTS = { motor: [120, 2500], propeller: [15, 2000], battery: [90, 1500] }

/** Cost per drone-flight vs the retirement %: the age-only model (line) and the simulated runs with the charts (dots). */
function CostChart({ d, retire }) {
  const W = 1000
  const H = 300
  const M = { top: 20, right: 24, bottom: 40, left: 64 }
  const xs = d.model_total.map((r) => r.retire_pct)
  const yMax = Math.max(...d.model_total.map((r) => r.cost_per_flight), ...d.runs.map((r) => r.cost_per_flight)) * 1.08
  const x = linear([0, Math.max(...xs)], [M.left, W - M.right])
  const y = linear([0, yMax], [H - M.bottom, M.top])
  const run = d.runs.find((r) => r.retire_pct === retire)
  const model = d.model_total.find((r) => r.retire_pct === retire)
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
          <text x={x(d.best_pct) + 10} y={y(d.best_cost) + 18} className="tick b10">cheapest without charts: B{fmt(d.best_pct, d.best_pct % 1 ? 1 : 0)}, ${fmt(d.best_cost, 2)}</text>
          <path d={linePath(d.runs.map((r) => r.retire_pct), d.runs.map((r) => r.cost_per_flight), x, y)} fill="none" stroke={C.ewma} strokeWidth={1.2} opacity={0.5} />
          {d.runs.map((r) => <circle key={r.retire_pct} cx={x(r.retire_pct)} cy={y(r.cost_per_flight)} r={5} fill={C.ewma} stroke={C.surface} />)}
        </svg>
      </div>
      <ul className="chart-legend">
        <li><svg width="22" height="10"><line x1="0" x2="22" y1="5" y2="5" stroke={C.series} strokeWidth="2.5" /></svg>age rule only (model): planned replacements + expected failures</li>
        <li><svg width="14" height="14"><circle cx="7" cy="7" r="5" fill={C.ewma} /></svg>with the charts (simulated runs): what the parts actually cost</li>
      </ul>
      {run && model && (
        <p className="chart-line">
          At B{retire}: ${fmt(model.cost_per_flight, 2)} per drone-flight by age alone vs ${fmt(run.cost_per_flight, 2)} with the
          charts ({run.planned} planned replacements, {run.failed} failures in flight).
        </p>
      )}
    </figure>
  )
}

/**
 * The cost of the retirement choice (age-replacement model, qc.retirement_cost). The prices are
 * placeholders: change them and the curve and its cheapest point move.
 */
export default function CostPanel({ dataset, retire }) {
  const [draft, setDraft] = useState(DEFAULTS)
  const [costs, setCosts] = useState(DEFAULTS)
  useEffect(() => {                              // refetch shortly after typing stops
    const t = setTimeout(() => setCosts(draft), 500)
    return () => clearTimeout(t)
  }, [draft])
  const valid = Object.values(costs).every(([cp, cf]) => cp > 0 && cf > 0)
  const { data: d, error } = useApi(() => getCost(dataset, costs), `cost-${dataset}-${JSON.stringify(costs)}`)
  const set = (type, i, v) => setDraft({ ...draft, [type]: draft[type].map((x, j) => (j === i ? Number(v) : x)) })
  return (
    <>
      <div className="scroll-x">
        <table className="numbers cost-inputs">
          <thead><tr><th>Price ($)</th>{Object.keys(DEFAULTS).map((t) => <th key={t}>{PART_TITLE[t]}</th>)}</tr></thead>
          <tbody>
            {[['Planned replacement', 0], ['Failure in flight', 1]].map(([label, i]) => (
              <tr key={label}>
                <td>{label}</td>
                {Object.keys(DEFAULTS).map((t) => (
                  <td key={t}><input type="number" min="1" value={draft[t][i]} onChange={(e) => set(t, i, e.target.value)}
                                     aria-label={`${label} cost, ${t}`} /></td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {!valid && <p className="rule-note">Every price must be above 0.</p>}
      {valid && error && <Failed error={error} />}
      {valid && !d && !error && <Loading what="the cost curve" />}
      {valid && d && <CostChart d={d} retire={retire} />}
      <p className="rule-note">
        Placeholder prices. The model assumes nothing warns before a failure, so p% of parts fail first; in these runs the
        charts caught every worn part, so no part failed in flight.
      </p>
    </>
  )
}

import { COLORS as C, linear, linePath, niceTicks } from './scale.js'
import { PART_TITLE, fmt } from '../format.js'

/** One panel: fitted Weibull R(t), Kaplan-Meier steps from the same data, and the B10 line. */
function Panel({ c }) {
  const W = 340
  const H = 250
  const M = { top: 34, right: 14, bottom: 40, left: 44 }
  const tMax = c.t[c.t.length - 1]
  const x = linear([0, tMax], [M.left, W - M.right])
  const y = linear([-0.02, 1.04], [H - M.bottom, M.top])
  // Kaplan-Meier is a step function: hold each survival value until the next time.
  let km = ''
  c.km.forEach((p, i) => {
    km += i === 0 ? `M${x(p.t)},${y(p.survival)}` : `H${x(p.t)}V${y(p.survival)}`
  })
  km += `H${x(tMax)}`

  return (
    <figure className="svg-chart rel-panel">
      <figcaption><b>{PART_TITLE[c.type] || c.type}</b> (β = {fmt(c.beta, 2)}, η = {fmt(c.eta)})</figcaption>
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label={`${c.type} reliability curve, B10 ${fmt(c.b10)} ${c.unit}`}>
        <rect x={M.left} y={M.top} width={W - M.left - M.right} height={H - M.top - M.bottom} fill={C.surface} />
        {[0, 0.25, 0.5, 0.75, 1].map((t) => (
          <g key={t}>
            <line x1={M.left} x2={W - M.right} y1={y(t)} y2={y(t)} stroke={C.grid} />
            <text x={M.left - 6} y={y(t) + 4} textAnchor="end" className="tick">{t}</text>
          </g>
        ))}
        {niceTicks(0, tMax, 4).map((t) => <text key={t} x={x(t)} y={H - 22} textAnchor="middle" className="tick">{t}</text>)}
        <text x={(M.left + W - M.right) / 2} y={H - 4} textAnchor="middle" className="tick">{c.unit}</text>
        <line x1={M.left} x2={W - M.right} y1={y(0.9)} y2={y(0.9)} stroke={C.grid} strokeWidth={1.4} />
        <path d={km} fill="none" stroke={C.ink2} strokeWidth={1.3} opacity={0.8} />
        <path d={linePath(c.t, c.r, x, y)} fill="none" stroke={C.series} strokeWidth={2.4} />
        <line x1={x(c.b10)} x2={x(c.b10)} y1={M.top} y2={H - M.bottom} stroke={C.critical} strokeWidth={1.3} strokeDasharray="5 3" />
        <text x={x(c.b10) + 6} y={y(0.9) - 8} className="tick b10">B10 = {fmt(c.b10)}</text>
      </svg>
    </figure>
  )
}

export default function ReliabilityChart({ curves }) {
  return (
    <div>
      <div className="grid-3 rel-grid">{curves.map((c) => <Panel key={c.type} c={c} />)}</div>
      <ul className="chart-legend">
        <li><svg width="22" height="10"><line x1="0" x2="22" y1="5" y2="5" stroke={C.series} strokeWidth="2.5" /></svg>Weibull fit R(t)</li>
        <li><svg width="22" height="10"><path d="M0,2H10V8H22" fill="none" stroke={C.ink2} strokeWidth="1.4" /></svg>from the data (Kaplan-Meier)</li>
        <li><svg width="22" height="10"><line x1="0" x2="22" y1="5" y2="5" stroke={C.critical} strokeWidth="1.5" strokeDasharray="5 3" /></svg>B10: the replace-at age</li>
      </ul>
    </div>
  )
}

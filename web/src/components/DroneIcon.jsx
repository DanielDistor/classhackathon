import { STATUS_COLOR, STATUS_SYMBOL } from '../format.js'

const ARMS = [[28, 28], [92, 28], [92, 92], [28, 92]]

/** A small top-view quadcopter drawn in the status colour, with the status symbol on its body. */
export default function DroneIcon({ status }) {
  const c = STATUS_COLOR[status]
  return (
    <svg className="dc-icon" viewBox="0 0 120 120" aria-hidden="true">
      {ARMS.map(([x, y]) => <line key={`a${x}${y}`} x1="60" y1="60" x2={x} y2={y} stroke="#9aa3ad" strokeWidth="7" strokeLinecap="round" />)}
      {ARMS.map(([x, y]) => (
        <g key={`p${x}${y}`}>
          <circle cx={x} cy={y} r="22" fill={c} fillOpacity="0.13" stroke={c} strokeOpacity="0.55" strokeWidth="2" strokeDasharray="4 3" />
          <line x1={x - 18} y1={y + 5} x2={x + 18} y2={y - 5} stroke="#6b7682" strokeWidth="3.5" strokeLinecap="round" opacity="0.6" />
          <circle cx={x} cy={y} r="6.5" fill="#3a4450" />
        </g>
      ))}
      <rect x="42" y="44" width="36" height="32" rx="9" fill={c} />
      <text x="60" y="66.5" textAnchor="middle" fontSize="19" fontWeight="700" fill="#fff">{STATUS_SYMBOL[status]}</text>
    </svg>
  )
}

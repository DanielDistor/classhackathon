// Words, colours and number formatting for the dashboard. No statistics here:
// every number arrives already computed by app/qc.py through the API.

export const STATUS_WORD = { ground: 'Do not fly', watch: 'Warning', go: 'Can fly', 'not enough data': 'Not enough data' }
export const STATUS_CLASS = { ground: 'ground', watch: 'watch', go: 'go', 'not enough data': 'na' }
export const STATUS_SYMBOL = { go: '✓', watch: '!', ground: '✕', 'not enough data': '?' }
export const STATUS_COLOR = { go: '#0a7d32', watch: '#c98500', ground: '#c62f2f', 'not enough data': '#5f6670' }
export const PART_NAME = { motor: 'Motor', propeller: 'Propeller', battery: 'Battery' }
export const PART_TITLE = { motor: 'Motors', propeller: 'Propellers', battery: 'Batteries' }

/** "now", "in 1 flight", "in 12 flights". */
export function flightsPhrase(n) {
  const k = Math.round(n)
  if (k <= 0) return 'now'
  return `in ${k} flight${k !== 1 ? 's' : ''}`
}

/** First letter upper case. */
export const cap = (s) => (s ? s[0].toUpperCase() + s.slice(1) : s)

/** One short line for a drone card: the first reason, as a sentence. */
export const cardText = (reason) => `${cap(reason.split(';')[0])}.`

/** Fixed decimals, with a thousands separator. */
export const fmt = (x, d = 0) =>
  x == null || Number.isNaN(x) ? '–' : Number(x).toLocaleString('en-US', { minimumFractionDigits: d, maximumFractionDigits: d })

/** Bar colour class for a part's countdown. */
export const partClass = (p) => (p.overdue ? 'over' : p.due ? 'soon' : 'ok')

export const plural = (n, word) => `${n} ${word}${n !== 1 ? 's' : ''}`

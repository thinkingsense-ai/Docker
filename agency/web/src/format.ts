// Cell formatting: thousands separators for numbers, a readable date for ISO dates, everything else untouched.
const NUM = /^-?\d+(\.\d+)?$/
const ISO = /^\d{4}-\d{2}-\d{2}(T[\d:.]+Z?)?$/

export function formatCell(v: string | null): string {
  if (v === null || v === '') return '—'
  if (NUM.test(v)) {
    if (/^-?0\d/.test(v)) return v                                  // a code such as 007, not a number
    const [i, f] = v.split('.')
    if (i.replace('-', '').length >= 16) return v                  // beyond safe integer precision: show as is
    return Number(i).toLocaleString('en-US') + (f ? '.' + f : '')
  }
  if (ISO.test(v)) {
    const d = new Date(v.length === 10 ? v + 'T00:00:00Z' : v)
    if (!isNaN(d.getTime())) return v.length === 10 ? d.toLocaleDateString('en-GB', { timeZone: 'UTC', day: 'numeric', month: 'short', year: 'numeric' }) : d.toLocaleString('en-GB')
  }
  return v
}

export function isNumeric(v: string | null): boolean { return v !== null && NUM.test(v) && !/^-?0\d/.test(v) }

export function badges(p: { editions: string[]; licence: { nonCommercial?: boolean; data?: string }; needsEmbeddingModel: boolean; capabilities: string[] }): string[] {
  const out: string[] = [p.editions.includes('free') ? 'free + commercial' : p.editions.includes('commercial') ? 'commercial only' : 'Docker only']
  if (p.licence.nonCommercial) out.push('non-commercial data')
  if (p.needsEmbeddingModel) out.push('needs embedding model')
  for (const c of p.capabilities) out.push(c)
  return out
}

export function scopeLine(s: 'server-backends' | 'agency-hint' | 'none'): string {
  if (s === 'server-backends') return 'Scope enforced by the Server (limits data sources, not schemas)'
  if (s === 'agency-hint') return 'Scope applied by Agency, not enforced by the Server'
  return 'No scope: asked in All data'
}

const WORDS: Record<string, string> = { usd: 'USD', eur: 'EUR', gbp: 'GBP', id: 'ID', avg: 'average', amt: 'amount', qty: 'quantity', num: 'number', pct: '%', ytd: 'YTD' }
const SYMBOL: Record<string, string> = { usd: '$', eur: '€', gbp: '£' }

/** A column name as a person would say it: usd_amount -> "USD amount", avg_error_pct -> "Average error %". Only names that look like column names (underscores) are touched. */
export function humanName(name: string): string {
  if (!/^[a-z0-9]+(_[a-z0-9]+)+$/i.test(name)) return name.replace(/_/g, ' ')
  const out = name.toLowerCase().split('_').map((w) => WORDS[w] ?? w)
  const pct = out[out.length - 1] === '%'
  const text = out.filter((w) => w !== '%').join(' ')
  return (text.charAt(0).toUpperCase() + text.slice(1)) + (pct ? ' (%)' : '')
}

/** The currency symbol a measure's name announces (total_usd, usd_amount), or ''. */
export function currencySymbol(name: string): string {
  const m = /(?:^|_)(usd|eur|gbp)(?:$|_)/i.exec(name)
  return m ? SYMBOL[m[1].toLowerCase()] : ''
}

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

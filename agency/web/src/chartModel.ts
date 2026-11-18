// What to draw for a result, decided from its shape alone (no model call, so it is fast and predictable). Written for Agency; it borrows the idea of Ask's shape-based detection,
// not its code. Everything here is pure so it is unit-tested.
import { isNumeric } from './format'

export type Kind = 'bar' | 'line' | 'donut'
export interface ChartPlan {
  kind: Kind
  category: number                 // column index of the category (or date) axis
  categoryName: string
  labels: string[]                 // one label per plotted row
  measures: { name: string; index: number; values: number[] }[]
  horizontal: boolean              // long or many labels read better on the left of horizontal bars
  panels: boolean                  // measures differ by orders of magnitude: one panel each, never one shared axis
  omitted: number                  // rows left out after keeping the top MAX_BARS
  options: Kind[]                  // the kinds that make sense for this result
  candidates: string[]             // every column that could be a measure (the person may switch them)
  note?: string
}

export const MAX_ROWS = 100, MAX_BARS = 12, MAX_MEASURES = 3, PANEL_RATIO = 20
const DATE = /^\d{4}-\d{2}-\d{2}([ T]\d{2}:\d{2}(:\d{2})?(\.\d+)?Z?)?$/
const ID = /(^|_)(id|key|no|num|number|code|zip|postcode)$/i

export type Role = 'measure' | 'id' | 'date' | 'text' | 'empty'
export function classify(columns: string[], rows: (string | null)[][]): Role[] {
  return columns.map((name, i) => {
    const v = rows.map((r) => r[i]).filter((x): x is string => x !== null && x.trim() !== '')
    if (!v.length) return 'empty'
    if (v.every(isNumeric)) return ID.test(name) ? 'id' : 'measure'
    if (v.every((x) => DATE.test(x.trim()))) return 'date'
    return 'text'
  })
}

/** Measures that are the same quantity twice: keep the normalised one (`amount` next to `amount_usd` is mixed currencies beside one comparable column). */
export function dropRaw(names: string[]): string[] {
  return names.filter((n) => !names.some((m) => m !== n && /_(usd|eur|gbp|normalized|normalised|converted)$/i.test(m) && m.toLowerCase().startsWith(n.toLowerCase() + '_')))
}

const num = (v: string | null) => (v === null || v === '' ? 0 : Number(v))
const distinct = (a: (string | null)[]) => new Set(a).size

export function planChart(columns: string[], rows: (string | null)[][], want?: { kind?: Kind; measures?: string[] }): ChartPlan | null {
  if (rows.length < 2 || rows.length > MAX_ROWS || columns.length < 2) return null
  const roles = classify(columns, rows)
  const idx = (r: Role) => roles.map((x, i) => (x === r ? i : -1)).filter((i) => i >= 0)
  const dates = idx('date'), texts = idx('text'), ids = idx('id')
  const candidates = dropRaw(idx('measure').map((i) => columns[i])), cand = candidates.length ? candidates : []
  if (!cand.length) return null
  // the category: a date whose values are all different makes a trend; otherwise a text column whose values are all different; otherwise an id (labelled with the first text column);
  // a lone text column that repeats; and nothing when it is ambiguous. A date that repeats is an attribute of each row, not an axis.
  const uniq = (i: number) => distinct(rows.map((r) => r[i])) === rows.length
  const uDates = dates.filter(uniq)
  let category = -1, kind: Kind = 'bar'
  if (uDates.length === 1) { category = uDates[0]; kind = 'line' }
  else if (uDates.length > 1) return null
  else if (texts.find(uniq) !== undefined) category = texts.find(uniq) as number
  else if (ids.length) category = ids.find(uniq) ?? ids[0]
  else if (texts.length === 1) category = texts[0]
  else return null
  const textLabel = ids.includes(category) && texts.length ? texts[0] : -1                // an id on its own says little: add the first text column beside it
  const labels = rows.map((r) => (textLabel >= 0 ? `${r[category] ?? ''} · ${r[textLabel] ?? ''}` : r[category] ?? ''))
  let chosen = (want?.measures?.length ? want.measures.filter((m) => cand.includes(m)) : []).slice(0, MAX_MEASURES)
  if (!chosen.length) chosen = cand.slice(0, MAX_MEASURES)
  const all = chosen.map((name) => ({ name, index: columns.indexOf(name), values: rows.map((r) => num(r[columns.indexOf(name)])) }))
  const nonNegative = all.length === 1 && all[0].values.every((v) => v >= 0) && all[0].values.some((v) => v > 0)
  const options: Kind[] = kind === 'line' ? ['line', 'bar'] : nonNegative && rows.length <= 6 ? ['bar', 'donut'] : ['bar']
  if (want?.kind && options.includes(want.kind)) kind = want.kind
  // large results: bars sorted high to low and cut to the top 12; a trend keeps its order and its rows
  let order = rows.map((_, i) => i), omitted = 0
  if (kind !== 'line') {
    order = order.sort((a, b) => all[0].values[b] - all[0].values[a])
    if (order.length > MAX_BARS) { omitted = order.length - MAX_BARS; order = order.slice(0, MAX_BARS) }
  }
  const pick = <T,>(a: T[]) => order.map((i) => a[i])
  const spans = all.map((m) => Math.max(...m.values.map(Math.abs), 0)).filter((s) => s > 0)
  const panels = all.length > 1 && spans.length > 1 && Math.max(...spans) / Math.min(...spans) > PANEL_RATIO
  const longest = Math.max(...pick(labels).map((l) => l.length))
  return { kind, category, categoryName: columns[category], labels: pick(labels), measures: all.map((m) => ({ ...m, values: pick(m.values) })), horizontal: kind === 'bar' && (longest > 10 || order.length > 7), panels, omitted, options, candidates: cand,
           note: omitted ? `Showing the top ${MAX_BARS} of ${rows.length} rows.` : undefined }
}

/** 1,200 -> 1.2K, 3,400,000 -> 3.4M: for axis ticks and value labels, never for the table. */
export function compact(n: number): string {
  const a = Math.abs(n), s = n < 0 ? '-' : ''
  for (const [lim, suf] of [[1e12, 'T'], [1e9, 'B'], [1e6, 'M'], [1e3, 'K']] as const) if (a >= lim) { const v = a / lim; return s + (v >= 100 ? v.toFixed(0) : v >= 10 ? v.toFixed(1).replace(/\.0$/, '') : v.toFixed(2).replace(/\.?0+$/, '')) + suf }
  return s + (Number.isInteger(a) ? String(a) : a.toFixed(a < 1 ? 3 : 2).replace(/\.?0+$/, ''))
}

/** Axis ticks: about `count` round values from 0 (or the lowest value if negative) to the highest. */
export function niceTicks(min: number, max: number, count = 4): number[] {
  const lo = Math.min(0, min), hi = Math.max(0, max)
  if (hi === lo) return [0, 1]
  const raw = (hi - lo) / count, mag = Math.pow(10, Math.floor(Math.log10(raw))), step = [1, 2, 2.5, 5, 10].map((m) => m * mag).find((s) => s >= raw) ?? raw
  const out: number[] = []
  for (let v = Math.floor(lo / step) * step; ; v += step) { out.push(Math.round(v / step) * step); if (v >= hi - step * 0.0001) break }
  return out
}

/** A sentence for screen readers and for the caption: what is drawn, and the largest value. */
export function describePlan(p: ChartPlan, _columns?: string[]): string {
  const first = p.measures[0]; const top = first.values.reduce((b, v, i) => (v > first.values[b] ? i : b), 0)
  const m = p.measures.map((x) => x.name).join(' and ')
  return `${p.kind === 'donut' ? 'Donut' : p.kind === 'line' ? 'Line' : p.horizontal ? 'Horizontal bar' : 'Bar'} chart of ${m} by ${p.categoryName}, ${p.labels.length} rows${p.omitted ? ` (top ${p.labels.length} of ${p.labels.length + p.omitted})` : ''}. ` +
         `The highest ${first.name} is ${compact(first.values[top])} for ${p.labels[top]}.`
}

/** One or a few numbers and nothing to compare them against: show them large instead of a table or a chart. */
export function statTiles(columns: string[], rows: (string | null)[][]): { label: string; value: string }[] | null {
  if (rows.length !== 1) return null
  const roles = classify(columns, rows), out = columns.map((c, i) => ({ c, i })).filter(({ i }) => roles[i] === 'measure').map(({ c, i }) => ({ label: c, value: rows[0][i] as string }))
  return out.length >= 1 && out.length <= 4 ? out : null
}

// The answer card's pure parts (written for Agency, not copied from the Ask app): the first sentence as a headline, the trust chips, the "worth knowing" notes and which columns to show.
import { humanName } from './format'

export interface Confidence { score?: number; level?: string }
export interface CardInput {
  evidence: { origin: string | null; sources: { id: string }[]; checks: { id: string; status: string }[]; answeredWithoutDataSources: boolean; warnings: string[]; elapsedMs: number } | null
  confidence?: Confidence | null; answerConfidence?: string | null
  assumptions?: string[] | null; truncated?: boolean | null; rowCap?: number | null
}
export interface Chip { id: string; tone: 'good' | 'warn' | 'plain'; label: string; title?: string }

const ABBREVIATIONS = new Set(['e.g', 'i.e', 'etc', 'vs', 'approx', 'incl', 'excl', 'est', 'avg', 'no', 'nos', 'fig', 'dept', 'inc', 'ltd', 'co', 'corp', 'mr', 'mrs', 'ms', 'dr', 'st',
  'jan', 'feb', 'mar', 'apr', 'jun', 'jul', 'aug', 'sep', 'sept', 'oct', 'nov', 'dec', 'u.s', 'u.k', 'a.m', 'p.m'])
const MAX_HEADLINE = 240

/** Column names inside a sentence read as a person would say them: "(usd_amount 75,617,590)" -> "(USD amount 75,617,590)". Only underscore names are touched. */
export function plainColumns(text: string): string {
  return text.replace(/\b[a-z][a-z0-9]*(?:_[a-z0-9]+)+\b/gi, (m) => humanName(m))
}

function endsSentence(text: string, at: number): boolean {
  const ch = text[at]
  if (ch === '!' || ch === '?') return true
  if (/\d/.test(text[at - 1] ?? '') && /\d/.test(text[at + 1] ?? '')) return false          // 1.5, v0.10.23
  const before = text.slice(0, at)
  const word = (/([A-Za-z.]+)$/.exec(before)?.[1] ?? '').toLowerCase()
  if (ABBREVIATIONS.has(word)) return false
  if (/(^|\s)[A-Z]$/.test(before)) return false                                              // an initial: "J. Smith"
  return true
}

/** The first sentence of an answer and the rest. A list, a heading, one sentence or a first sentence over 240 characters comes back whole, as the headline. */
export function splitHeadline(answer: string): { headline: string; rest: string } {
  const text = answer.trim()
  if (!text) return { headline: '', rest: '' }
  if (/^([-*•#>]|\d+[.)]\s|\|)/.test(text)) return { headline: text, rest: '' }
  const nl = text.indexOf('\n'); const stop = nl >= 0 ? nl : text.length
  for (let i = 0; i < stop; i++) {
    const ch = text[i]
    if (ch !== '.' && ch !== '!' && ch !== '?') continue
    let end = i + 1
    while (end < stop && /["'”’)\]*_]/.test(text[end])) end += 1
    if (end >= stop) break
    if (!/\s/.test(text[end])) continue
    const next = text.slice(end).trimStart()[0] ?? ''
    if (!/[A-Z0-9"“'‘([$£€*_]/.test(next)) continue
    if (!endsSentence(text, i)) continue
    const head = text.slice(0, end).trim()
    return head.length > MAX_HEADLINE ? { headline: text, rest: '' } : { headline: head, rest: text.slice(end).trim() }
  }
  if (nl >= 0) { const head = text.slice(0, nl).trim(); if (head && head.length <= MAX_HEADLINE) return { headline: head, rest: text.slice(nl).trim() } }
  return { headline: text, rest: '' }
}

const LEVEL: Record<string, string> = { high: 'High', medium: 'Medium', low: 'Low', moderate: 'Medium' }
function level(c?: Confidence | null, fallback?: string | null): string | null {
  const raw = (c?.level ?? fallback ?? '').toString().toLowerCase()
  return LEVEL[raw] ?? null
}

/** The few facts that say how far to trust an answer, always visible: where it came from, which sources, how sure, what was checked. */
export function trustChips(a: CardInput): Chip[] {
  const out: Chip[] = []
  const ev = a.evidence
  if (ev?.origin === 'question_bank') out.push({ id: 'origin', tone: 'good', label: 'Matches an approved question', title: 'An admin approved this question and its SQL.' })
  else if (ev?.origin === 'generated') out.push({ id: 'origin', tone: 'plain', label: 'Written for this question', title: 'No approved question matched, so the SQL was written for this question.' })
  if (ev) {
    const hidden = ev.warnings.some((w) => /source names are hidden/i.test(w))
    if (ev.answeredWithoutDataSources) out.push({ id: 'sources', tone: 'warn', label: 'No data source used' })
    else if (hidden) out.push({ id: 'sources', tone: 'plain', label: 'Sources hidden' })
    else if (ev.sources.length) { const ids = ev.sources.map((s) => s.id); out.push({ id: 'sources', tone: 'plain', label: 'Source: ' + (ids.length > 3 ? `${ids.slice(0, 3).join(', ')} +${ids.length - 3}` : ids.join(', ')), title: 'The data sources used' }) }
  }
  const lv = level(a.confidence, a.answerConfidence)
  if (lv) out.push({ id: 'confidence', tone: lv === 'High' ? 'good' : lv === 'Low' ? 'warn' : 'plain', label: `${lv} confidence`, title: a.confidence?.score != null ? `Score ${a.confidence.score} of 100` : undefined })
  if (ev) {
    const ran = ev.checks.filter((c) => c.status !== 'skipped'); const failed = ran.filter((c) => c.status !== 'pass'); const passed = ran.length - failed.length
    if (failed.length) out.push({ id: 'checks', tone: 'warn', label: `${humanName(failed[0].id)} ${failed[0].status === 'fail' ? 'failed' : failed[0].status}${failed.length > 1 ? ` (+${failed.length - 1})` : ''}` })
    else if (ran.length) out.push({ id: 'checks', tone: 'good', label: `${passed} check${passed === 1 ? '' : 's'} passed` })
  }
  return out
}

/** What a reader should know before relying on the numbers: stated assumptions, a cut result, a check that failed. Scope notes stay in the details pane. */
export function worthKnowing(a: CardInput): string[] {
  const out: string[] = []
  for (const s of a.assumptions ?? []) if (s && s.trim()) out.push(s.trim())
  if (a.truncated) out.push(a.rowCap ? `Only the first ${a.rowCap.toLocaleString('en-US')} rows are shown; the result was longer.` : 'The result was cut at the Server\'s row limit.')
  for (const c of a.evidence?.checks ?? []) if (c.status !== 'pass' && c.status !== 'skipped') out.push(`The ${humanName(c.id).toLowerCase()} check did not pass.`)
  if (level(a.confidence, a.answerConfidence) === 'Low') out.push('Confidence is low: check the SQL or ask an admin before relying on this.')
  return out
}

const isIdName = (c: string) => /(^|_)id$/i.test(c.trim())

/** Columns to show: an ID column is hidden when another column can name the row (some other column that is not an ID and holds text). Never hides everything. */
export function visibleColumns(columns: string[], rows: (string | null)[][], raw: boolean): { show: number[]; hidden: string[] } {
  const all = columns.map((_, i) => i)
  if (raw) return { show: all, hidden: [] }
  const ids = all.filter((i) => isIdName(columns[i]))
  const namers = all.filter((i) => !isIdName(columns[i]) && rows.some((r) => r[i] != null && r[i] !== '' && !/^-?\d+(\.\d+)?$/.test(String(r[i]))))
  if (!ids.length || !namers.length) return { show: all, hidden: [] }
  return { show: all.filter((i) => !ids.includes(i)), hidden: ids.map((i) => columns[i]) }
}

/** A column header as a person would say it: "usd_amount" -> "USD amount", "entity" -> "Entity". */
export function columnTitle(name: string): string {
  const t = humanName(name)
  return t.charAt(0).toUpperCase() + t.slice(1)
}

/** The reasons a thumbs-down can give. The ids are the Server's own (QueryFeedback.Reason). */
export const REASONS: [string, string][] = [['WRONG_DATA', 'Wrong data or rows'], ['WRONG_CALCULATION', 'Wrong numbers or calculation'], ['MISREAD_QUESTION', 'Misread my question'], ['WRONG_TIME_PERIOD', 'Wrong time period'], ['PRESENTATION', 'Chart or presentation']]

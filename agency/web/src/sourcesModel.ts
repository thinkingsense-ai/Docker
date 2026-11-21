// The feeds Watch reads and their health (docs/agency-it-risk-flow.md, section 5). One approved question, composed here. Pure, so it is unit-tested.
// Health only: the feed adapter stores a headline, its link and date per item, never article text.
import { records, type Table } from './rcaBrief'

export const SOURCES_QUESTION = 'Which feeds are we reading, and when did each last answer?'
/** The adapter polls every 30 minutes by default; a feed with no answer for three polls is late. */
export const LATE_MINUTES = 90

export const KINDS: Record<string, { label: string; meaning: string }> = {
  reporting: { label: 'Reporting', meaning: 'News and security sites. A story here can start a candidate; it is only ever a lead, never evidence of a cause.' },
  official: { label: 'Official', meaning: 'Government advisories and operators. These can ground a cause once a person has read the primary source.' },
  context: { label: 'Context', meaning: 'Analysis and commentary, shown as reading. Never starts a candidate and never counts as a source for a link.' },
}
export const kindLabel = (k: string) => KINDS[k]?.label ?? k

export interface Source { name: string; kind: string; status: string; lastSuccess: Date | null; itemsLastRun: number; itemsTotal: number; matchedTotal: number; error: string }
export type State = 'ok' | 'late' | 'failing' | 'blocked' | 'never'
export interface Health { state: State; text: string }

const num = (s: string | undefined) => { const v = Number(s); return Number.isFinite(v) ? v : 0 }

/** The Server returns a timestamp as `2026-11-20 10:30:00` or ISO; the adapter writes UTC. A value that does not parse is no date, never a wrong one. */
export function parseWhen(s: string | undefined): Date | null {
  const v = (s ?? '').trim(); if (!v) return null
  const d = new Date(/[zZ]|[+-]\d\d:?\d\d$/.test(v) ? v : v.replace(' ', 'T') + 'Z')
  return Number.isNaN(d.getTime()) ? null : d
}

const KIND_ORDER = ['reporting', 'official', 'context']   // the feeds that can start a candidate first, reading-only last
export function composeSources(t: Table | undefined): Source[] {
  return records(t).map((r) => ({ name: r.source, kind: r.kind, status: r.last_status, lastSuccess: parseWhen(r.last_success_at), itemsLastRun: num(r.items_last_run), itemsTotal: num(r.items_total), matchedTotal: num(r.matched_total), error: r.last_error }))
    .sort((a, b) => (KIND_ORDER.indexOf(a.kind) + 1 || 9) - (KIND_ORDER.indexOf(b.kind) + 1 || 9) || a.name.localeCompare(b.name))
}

export function ago(d: Date, now: Date): string {
  const m = Math.max(0, Math.round((now.getTime() - d.getTime()) / 60000))
  if (m < 2) return 'just now'
  if (m < 90) return `${m} minutes ago`
  const h = Math.round(m / 60); return h < 36 ? `${h} hours ago` : `${Math.round(h / 24)} days ago`
}

export function health(s: Source, now: Date): Health {
  if (s.status === 'blocked_by_robots') return { state: 'blocked', text: "Not read: the site's robots.txt does not allow it." }
  const last = s.lastSuccess ? `last answered ${ago(s.lastSuccess, now)}` : 'has never answered'
  if (['http_error', 'parse_error', 'unreachable'].includes(s.status)) return { state: 'failing', text: `Failing (${s.error || s.status.replace('_', ' ')}); ${last}.` }
  if (!s.lastSuccess) return { state: 'never', text: 'Not read yet.' }
  if (now.getTime() - s.lastSuccess.getTime() > LATE_MINUTES * 60000) return { state: 'late', text: `Not updated since ${s.lastSuccess.toISOString().slice(0, 16).replace('T', ' ')} UTC (${ago(s.lastSuccess, now)}).` }
  return { state: 'ok', text: `Answered ${ago(s.lastSuccess, now)}.` }
}

/** One line for the top of Watch and Sources: how many feeds are healthy, and which are not, by name. */
export function summaryLine(list: Source[], now: Date): { ok: boolean; text: string } {
  if (!list.length) return { ok: false, text: 'No feed has reported yet: the feed adapter is not running on this stack.' }
  const bad = list.map((s) => ({ s, h: health(s, now) })).filter((x) => x.h.state !== 'ok')
  if (!bad.length) return { ok: true, text: `All ${list.length} feeds answered recently.` }
  return { ok: false, text: `${list.length - bad.length} of ${list.length} feeds answered recently. Not healthy: ${bad.map((x) => x.s.name).join(', ')}.` }
}

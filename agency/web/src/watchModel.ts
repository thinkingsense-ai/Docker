// The Watch list (docs/agency-it-risk-flow.md, section 5): candidates composed from one approved question. Pure, so it is unit-tested.
// Nothing here reaches data: the question goes through the Server as the signed-in person.
import { records, type Table } from './rcaBrief'

export const WATCH_QUESTION = 'Which incident candidates are we watching, and has each been traced?'

export const CIA_QUESTION = 'How does the CIA and ODNI breach of November 2026 read, layer by layer?'

export const CLAIM_TYPES: Record<string, { label: string; meaning: string }> = {
  'ai-attack-claimed': { label: 'AI attack claimed', meaning: 'Someone says an AI-driven attack caused it. Only a claim until an official source says otherwise.' },
  'ai-attack-confirmed': { label: 'AI attack confirmed', meaning: 'An operator or regulator says an AI-driven attack caused it.' },
  'ai-adjacent': { label: 'AI adjacent', meaning: 'An outage or vulnerability story that mentions AI without claiming an attack.' },
}
export const claimLabel = (t: string) => CLAIM_TYPES[t]?.label ?? t

export interface Candidate {
  id: string; caseId: string; title: string; claimType: string; status: 'traced' | 'not_yet_traced'; firstSeen: string; summary: string
  verdict: string; openIncidents: number; incidents: number; sources: number; leadSource: string; leadUrl: string
}

/** Only an http or https address is ever made a link: a feed is outside data. */
export const safeUrl = (u: string | undefined) => (/^https?:\/\/[^\s]+$/i.test((u ?? '').trim()) ? (u as string).trim() : '')
const n = (s: string | undefined) => { const v = Number(s); return Number.isFinite(v) ? v : 0 }

/** Newest first. An unknown status is treated as not yet traced, so nothing looks tested that is not. */
export function composeWatch(t: Table | undefined): Candidate[] {
  return records(t).map((r) => ({
    id: r.candidate_id, caseId: r.case_id ?? '', title: r.title, claimType: r.claim_type, status: r.status === 'traced' ? 'traced' as const : 'not_yet_traced' as const,
    firstSeen: r.first_seen, summary: r.summary, verdict: r.verdict, openIncidents: n(r.open_incidents), incidents: n(r.incidents), sources: n(r.sources), leadSource: r.lead_source ?? '', leadUrl: safeUrl(r.lead_url),
  })).sort((a, b) => b.firstSeen.localeCompare(a.firstSeen))
}

/** What can be done with a candidate. The November case has the full brief; the July case is read layer by layer through an approved question; an untraced one, which comes from the live feed, is a lead only: the trace step is not built yet. */
export type Action = { kind: 'brief' } | { kind: 'ask'; question: string; label: string } | { kind: 'wait'; why: string }
export function actionFor(c: Candidate): Action {
  if (c.status !== 'traced') return { kind: 'wait', why: 'A lead from the feed, not yet traced. The trace step (finding the primary source and grading each link) is not built yet.' }
  if (c.caseId === 'cia-odni-nov-2026') return { kind: 'ask', question: CIA_QUESTION, label: 'Read it layer by layer' }
  if (c.caseId === 'jul-2026-breakout') return { kind: 'ask', question: 'How does the July 2026 breakout read, layer by layer?', label: 'Read it layer by layer' }
  if (c.caseId === 'nov-2026-cluster' || (!c.caseId && c.claimType === 'ai-attack-claimed')) return { kind: 'brief' }
  return { kind: 'ask', question: 'How does the July 2026 breakout read, layer by layer?', label: 'Read it layer by layer' }
}

export function statusText(c: Candidate): string {
  return c.status === 'traced' ? `Traced: ${c.incidents} incident${c.incidents === 1 ? '' : 's'}, ${c.sources} source${c.sources === 1 ? '' : 's'}` : 'Claim not yet tested'
}

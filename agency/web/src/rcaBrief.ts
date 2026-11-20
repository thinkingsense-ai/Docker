// The IT-risk root-cause brief (docs/agency-risk-it.md), composed from the answers to five approved questions. Pure, so it is unit-tested.
// Nothing here reaches data: the questions go through the Server as the signed-in person, so access and approved SQL stay the Server's.
export const BRIEF_PACK = 'it-risk'
export const BRIEF_QUESTIONS = {
  causes: 'For each November 2026 incident, what is the cause and how well is it supported?',
  open: 'Which links in the November 2026 cluster are only inferred or still to be tested?',
  verdict: 'What is the verdict on the claim that the November outages are AI hacking?',
  controls: 'Which control owns each root condition, and which framework category does it map to?',
  speakers: 'Who said each confirmed cause, and where?',
} as const
export type BriefKey = keyof typeof BRIEF_QUESTIONS
export type Table = { columns: string[]; rows: (string | null)[][] }
export type Answers = Partial<Record<BriefKey, Table>>

export const GRADES: Record<string, { label: string; meaning: string; fact: boolean }> = {
  confirmed: { label: 'Confirmed', meaning: 'An operator or regulator states it and no official source contradicts it.', fact: true },
  stated: { label: 'Stated', meaning: 'One party states it; nobody corroborates it.', fact: true },
  disputed: { label: 'Disputed', meaning: 'Two official sources disagree.', fact: false },
  not_named: { label: 'Not named', meaning: 'No official cause has been published.', fact: false },
  inferred: { label: 'Inferred', meaning: 'Our reasoning; no source says it.', fact: false },
  to_be_tested: { label: 'To be tested', meaning: "A hypothesis that needs the firm's own records.", fact: false },
}
export const gradeLabel = (g: string) => GRADES[g]?.label ?? g
const VERDICTS: Record<string, string> = { supported: 'Supported', not_supported: 'Not supported', insufficient_evidence: 'Insufficient evidence' }
export const verdictLabel = (v: string) => VERDICTS[v] ?? v

export interface Incident { operator: string; cause: string; grade: string; sources: number; supported?: string }   // supported: set only when the sources back less than the grade (the link judge's finding)
export interface OpenItem { layer: string; statement: string; grade: string; reason: string }
export interface ControlRow { condition: string; grade: string; control: string; owner: string; framework: string; category: string; caseId: string }
export interface Check { rule: string; ok: boolean; detail: string }
export interface Brief {
  incidents: Incident[]; open: OpenItem[]; controls: ControlRow[]; checks: Check[]
  claim: { text: string; verdict: string; sentence: string } | null
  counts: { total: number; confirmed: number; stated: number; openIncidents: Incident[] }
  complete: boolean
}

// A Server answer as a list of records keyed by lower-cased column name.
export function records(t: Table | undefined): Record<string, string>[] {
  if (!t) return []
  const cols = t.columns.map((c) => c.toLowerCase())
  return t.rows.map((r) => Object.fromEntries(cols.map((c, i) => [c, r[i] ?? ''])))
}

const n = (s: string | undefined) => { const v = Number(s); return Number.isFinite(v) ? v : 0 }

/** Which of the six rules (section 6.3 of the design note) can be checked from these answers, and whether each holds. */
export function checks(incidents: Incident[], speakers: Record<string, string>[], claimVerdict: string | null, sentence: string): Check[] {
  const out: Check[] = []
  const unsourced = incidents.filter((i) => i.sources === 0 && !['inferred', 'to_be_tested'].includes(i.grade))
  out.push({ rule: 'No cause without evidence', ok: unsourced.length === 0,
    detail: unsourced.length ? `${unsourced.map((i) => i.operator).join(', ')}: a cause with no source can only be inferred or to be tested.` : 'Every cause on this page has at least one source.' })
  const weak = incidents.filter((i) => i.grade === 'confirmed' && !speakers.some((s) => s.operator === i.operator && ['operator', 'regulator'].includes(s.speaker_kind)))
  out.push({ rule: 'Confirmed means an operator or regulator said it', ok: weak.length === 0,
    detail: weak.length ? `${weak.map((i) => `${i.operator} cause is graded confirmed but its sources support stated: only reporting, a union or a reference page says it; no operator or regulator statement`).join('; ')}. Needs a primary source.` : 'Every confirmed cause has an operator or regulator behind it.' })
  const open = incidents.filter((i) => i.grade !== 'confirmed')
  const named = open.every((i) => sentence.includes(i.operator))
  out.push({ rule: 'No flat "no attack" while a cause is open', ok: claimVerdict !== null && (claimVerdict !== 'not_supported' || open.length === 0 || named),
    detail: claimVerdict === null ? 'The verdict answer is missing, so this cannot be checked.' : open.length ? (named ? `The verdict names the ${open.length} open incident${open.length === 1 ? '' : 's'}.` : 'The verdict must name every open incident.') : 'No incident is open.' })
  return out
}

export function composeBrief(a: Answers): Brief {
  const speakers = records(a.speakers)
  const incidents: Incident[] = records(a.causes).map((r) => {
    const i: Incident = { operator: r.operator, cause: r.cause, grade: r.grade, sources: n(r.sources) }
    if (i.grade === 'confirmed' && !speakers.some((s) => s.operator === i.operator && ['operator', 'regulator'].includes(s.speaker_kind))) i.supported = i.sources > 0 ? 'stated' : 'inferred'
    return i
  })
  const open: OpenItem[] = records(a.open).map((r) => ({ layer: r.layer, statement: r.statement, grade: r.grade, reason: r.reason }))
  const controls: ControlRow[] = records(a.controls).map((r) => ({ condition: r.root_condition, grade: r.grade, control: r.owning_control, owner: r.owner_role, framework: r.framework, category: r.category, caseId: r.case_id }))
  const v = records(a.verdict)[0]
  const confirmed = incidents.filter((i) => i.grade === 'confirmed')
  const stated = incidents.filter((i) => i.grade !== 'not_named')
  const openIncidents = incidents.filter((i) => i.grade !== 'confirmed')
  const total = incidents.length
  let sentence = ''
  if (v) {
    const names = openIncidents.map((i) => `${i.operator} (${gradeLabel(i.grade).toLowerCase()})`)
    sentence = v.verdict === 'not_supported'
      ? `No official source attributes any of the ${total} incidents to an attack` + (names.length ? `, but ${names.join(' and ')} ${names.length === 1 ? 'is' : 'are'} still open.` : '.')
      : v.verdict === 'supported' ? 'An official source supports the claim.' : 'There is not enough evidence to test the claim yet.'
  }
  return {
    incidents, open, controls, claim: v ? { text: v.claim, verdict: v.verdict, sentence } : null,
    counts: { total, confirmed: confirmed.length, stated: stated.length, openIncidents },
    checks: checks(incidents, speakers, v?.verdict ?? null, sentence),
    complete: incidents.length > 0 && !!v,
  }
}

export function headline(b: Brief): string {
  const c = b.counts
  if (!b.complete) return 'The brief could not be completed from the approved questions.'
  const attack = b.claim?.verdict === 'not_supported' ? 'no official source points to an attack' : b.claim?.verdict === 'supported' ? 'an official source supports the claim' : 'the claim cannot be tested yet'
  return `${c.confirmed} of ${c.total} causes are confirmed, ${c.stated} of ${c.total} are stated, and ${attack}.${c.openIncidents.length ? ` ${c.openIncidents.length} stay open.` : ''}${b.incidents.some((i) => i.supported) ? ` ${b.incidents.filter((i) => i.supported).length} confirmed grade${b.incidents.filter((i) => i.supported).length === 1 ? ' is' : 's are'} higher than the sources support.` : ''}`
}

/** Plain text of the brief, for copying into an email or a ticket. */
export function briefText(b: Brief): string {
  const L: string[] = ['IT risk root-cause brief: November 2026 incident cluster', headline(b), b.claim ? `Claim: ${b.claim.text} Verdict: ${verdictLabel(b.claim.verdict)}. ${b.claim.sentence}` : '', '']
  for (const i of b.incidents) L.push(`- ${i.operator}: ${i.cause} [${gradeLabel(i.grade)}${i.supported ? `; sources support only ${gradeLabel(i.supported).toLowerCase()}` : ''}, ${i.sources} source${i.sources === 1 ? '' : 's'}]`)
  if (b.open.length) { L.push('', 'Not established:'); for (const o of b.open) L.push(`- ${gradeLabel(o.grade)}: ${o.statement} (${o.reason})`) }
  if (b.controls.length) { L.push('', 'Control to fix:'); for (const c of b.controls.filter((x) => x.caseId === 'nov-2026-cluster')) L.push(`- ${c.control} (${c.owner}); ${c.framework} ${c.category}`) }
  const bad = b.checks.filter((c) => !c.ok); if (bad.length) { L.push('', 'Checks that failed:'); for (const c of bad) L.push(`- ${c.rule}: ${c.detail}`) }
  return L.filter((x, i, a) => x !== '' || a[i - 1] !== '').join('\n')
}

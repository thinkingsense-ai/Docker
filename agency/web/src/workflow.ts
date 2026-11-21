// Types and wording for workflow runs (the Server's v0.10.19 API as relayed by the layer). Pure, so it is unit-tested.
export interface Definition { id: string; title: string; entity?: string; keyField: string | null; approverGroup?: string; requiredApprovals: number }
export interface Rule { name: string; passed: boolean; detail: string }
export interface Run {
  id: string; definition: string; key: string; title: string; initiator: string; stage: string; stageOrder: string[]
  recommendation: { action: string; reason: string; source?: string } | null; rules: Rule[]; evidence: Record<string, unknown>
  approvals: { user: string; at: string }[]; requiredApprovals: number; payloadHash: string | null
  rejection: { user: string; reason: string; at: string } | null
  writeBack: { mode: string; status: string; call: string; at: string } | null
  createdAt?: string; updatedAt?: string; you: { canApprove: boolean; reason: string | null }
}
export interface DecisionEntry { seq: number; ts: string; type: string; actor: string; details: Record<string, unknown> }
export interface Decisions { chainValid: boolean; firstBadSeq: number | null; totalEntries: number | null; count: number; source: 'server' | 'file'; entriesVerified: boolean; entries: DecisionEntry[] }

export const TERMINAL = ['written_back', 'rejected']

const STAGE: Record<string, string> = {
  facts: 'Gathering facts', rules: 'Checking rules', recommendation: 'Preparing a recommendation', awaiting_approval: 'Waiting for approval',
  approved: 'Approved', written_back: 'Done (dry run)', rejected: 'Rejected',
}
export const stageLabel = (s: string) => STAGE[s] ?? s

// The Server's refusal codes in plain words (spec FR-26). Used for a refused click and for the reason a button is disabled.
const REASON: Record<string, string> = {
  missing_grant: 'Your account has no permission for this. An admin grants it under Admin > users.',
  initiator_cannot_approve: 'You started this run, so someone else has to approve it.',
  non_human_identity: 'Only a person can approve; this account is an automated identity.',
  already_approved: 'You have already approved this run. A different person has to give the next approval.',
  not_an_approver: 'You are not on the approver list for this workflow.',
  not_awaiting_approval: 'This run is not waiting for approval any more.',
  payload_hash_mismatch: 'The facts changed since you opened this card. It has been reloaded: read it again before approving.',
  engine_unavailable: 'The workflow engine could not be reached. Try again in a moment.',
  unknown_run: 'That run no longer exists.',
  workflows_off: 'Workflows are off on this Server: they need the commercial edition and an enabled workflow engine.',
}
export const reasonText = (code: string | null | undefined) => (code ? REASON[code] ?? `Refused (${code}).` : '')

export const shortHash = (h: string | null) => (h ? h.slice(0, 12) + '…' : 'not available yet')

export function dryRunLine(w: Run['writeBack']): string {
  if (!w) return ''
  if (w.mode === 'dry_run') return `Dry run: this would call ${w.call}. Nothing was sent to any system.`
  if (/register\./.test(w.call)) return `Added to the risk register: ${w.call.replace(/^INSERT /, '')}. The register is append-only: earlier ratings stay.`
  return `Write-back (${w.mode}, ${w.status}): ${w.call}`
}

export function approvalLine(r: Run): string {
  const names = r.approvals.map((a) => a.user)
  return `${r.approvals.length} of ${r.requiredApprovals} approvals${names.length ? ` (${names.join(', ')})` : ''}`
}

/** Which result columns can start a workflow: a column named like a definition's key field, and the definition. Matching is case-insensitive on the exact name. */
export function startable(columns: string[], defs: Definition[]): { column: number; def: Definition }[] {
  const out: { column: number; def: Definition }[] = []
  for (const d of defs) {
    if (!d.keyField) continue
    const j = columns.findIndex((c) => c.toLowerCase() === d.keyField!.toLowerCase())
    if (j >= 0) out.push({ column: j, def: d })
  }
  return out
}

// The incident brief (docs/agency-risk-it.md): approving carries out what the run recommends, publishing the brief or recording a hold; rejecting declines it. The Server has no "hold" state,
// so a hold or a send-back is a rejection whose reason starts with a fixed phrase, and the card reads it back.
export const INCIDENT = 'incident-cluster-rca'
export const ON_HOLD = 'On hold: '
export const SENT_BACK = 'Sent back: '
export const isIncident = (r: Pick<Run, 'definition'>) => r.definition === INCIDENT
// The risk assessment (docs/agency-risk-register-plan.md): a first-line person proposes a rating for one system; the second line records it in the risk register or sends it back. Approving adds one row to the register
// (never an edit); a send-back is a rejection whose reason starts with the same fixed phrase.
export const ASSESSMENT = 'risk-assessment'
// The major-incident decision (docs/agency-risk-register-plan.md, section 5): a second-line person records that an incident is MAJOR, which starts the regulators' notification clocks. No rule decides it.
// Approving IS the decision; a rejection records nothing and no clock starts. Nothing is sent to any regulator.
export const MAJOR = 'major-incident'
export const NOT_MAJOR = 'Not major: '
export const isMajor = (r: Pick<Run, 'definition'>) => r.definition === MAJOR
export const majorWords = () => ({ approve: 'Record as major', decline: 'Not major…', prefix: NOT_MAJOR, ask: 'Why is it not major, or what is missing?', submit: 'Not major' })
export function majorStage(r: Run, s: string): string {
  if (s === 'written_back') return 'Recorded as major: clocks started'
  if (s === 'rejected') return r.rejection?.reason.startsWith(NOT_MAJOR) ? 'Not recorded as major' : 'Declined'
  return stageLabel(s)
}
export const isAssessment = (r: Pick<Run, 'definition'>) => r.definition === ASSESSMENT
export const assessmentWords = (r: Run) => {
  const record = r.recommendation?.action === 'record'
  return { approve: record ? 'Record in the register' : 'Confirm hold', decline: 'Send back…', prefix: SENT_BACK, ask: 'What should change before it comes back?', submit: 'Send back' }
}
export function assessmentStage(r: Run, s: string): string {
  if (s === 'written_back') return r.writeBack?.mode === 'dry_run' ? 'Recorded (dry run)' : r.recommendation?.action === 'hold' ? 'Hold recorded' : 'Recorded in the register'
  if (s === 'rejected') return r.rejection?.reason.startsWith(SENT_BACK) ? 'Sent back' : 'Declined'
  return stageLabel(s)
}
export const incidentWords = (r: Run) => {
  const publish = r.recommendation?.action === 'publish'
  return {
    approve: publish ? 'Publish problem record' : 'Confirm hold', decline: publish ? 'Hold it…' : 'Send back…', prefix: publish ? ON_HOLD : SENT_BACK,
    ask: publish ? 'What is it waiting for?' : 'What should change before it comes back?', submit: publish ? 'Hold' : 'Send back',
  }
}
export function incidentStage(r: Run, s: string): string {
  if (s === 'written_back') return r.recommendation?.action === 'hold' ? 'Hold recorded (dry run)' : 'Published (dry run)'
  if (s === 'rejected') return r.rejection?.reason.startsWith(ON_HOLD) ? 'On hold' : r.rejection?.reason.startsWith(SENT_BACK) ? 'Sent back' : 'Declined'
  return stageLabel(s)
}
export function incidentRejection(r: Run): string {
  const x = r.rejection; if (!x) return ''
  if (x.reason.startsWith(ON_HOLD)) return `Put on hold by ${x.user}: ${x.reason.slice(ON_HOLD.length)}`
  if (x.reason.startsWith(SENT_BACK)) return `Sent back by ${x.user}: ${x.reason.slice(SENT_BACK.length)}`
  if (x.reason.startsWith(NOT_MAJOR)) return `Not recorded as major, by ${x.user}: ${x.reason.slice(NOT_MAJOR.length)}. No clock starts.`
  return `Declined by ${x.user}: ${x.reason}`
}

/** How a rule line is introduced. The gateway names the rules that stopped something "block", plain observations "note", and the allowed actions "allowed_actions"; the rest are named checks. */
export function ruleLabel(r: Rule): string {
  if (r.name === 'block') return 'Blocked:'
  if (r.name === 'note') return 'Note:'
  if (r.name === 'allowed_actions') return 'Allowed:'
  return `${r.passed ? 'Passed' : 'Failed'} ${r.name.replace(/_/g, ' ')}:`
}

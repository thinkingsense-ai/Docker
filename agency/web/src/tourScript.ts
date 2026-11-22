// The guided click-through of the IT-risk demo (docs: agency/local/README.md, "Guided tour"). Pure data, so it is unit-tested: who does each step, which screen it is on, what to say, and
// which real buttons the tour presses for you. Nothing here reaches data: the tour clicks the same buttons a person would, as the demo person for that step.
import type { View } from './shell'

export type Persona = 'curator' | 'alice' | 'bob' | 'carol'
/** One press: wait for `click` to exist and be enabled, press it, then wait for `until` (any element matching), or `settleMs`. A missing target is not an error: the step says it was already done. */
export interface Action { label: string; click?: string; until?: string; waitMs?: number; settleMs?: number; skipIf?: string; findMs?: number; refresh?: string }     // skipIf: do not press when this is already on the screen (the result is already there); findMs: how long to wait for the button (a run takes a while to reach its approver); refresh: a control to press while waiting, for a list that does not update itself
export interface TourStep {
  id: string
  act: string                 // the act of the demo this belongs to
  title: string
  persona: Persona
  view: View
  say: string                 // what to tell the audience
  look: string                // what to point at on the screen
  actions: Action[]
}

export const PERSONAS: Record<Persona, string> = {
  curator: 'Curator: sees everything, can start and read the audit',
  alice: 'Alice: first line, proposes and starts',
  bob: 'Bob: second line, approves',
  carol: 'Carol: second line, the second approver',
}

const LEFT = 'article.run[data-stage]:not([data-stage="awaiting_approval"])'          // a run card that has moved past waiting
export const STEPS: TourStep[] = [
  { id: 'watch', act: 'Act 1. Watch', title: 'Events under review', persona: 'alice', view: 'watch',
    say: 'Agency reads public feeds all day. Anything that looks like AI hacking becomes an event under review. A headline is a lead, never a conclusion.',
    look: 'Each card says where the lead came from and what is claimed. Two older ones were already traced.',
    actions: [{ label: 'Load the events', until: '[data-tour="watch-card"]', waitMs: 300000 }] },
  { id: 'sources', act: 'Act 1. Watch', title: 'Where the feed comes from', persona: 'alice', view: 'sources',
    say: 'Every source has a kind: reporting, official, or context. Only official sources can confirm a cause. Context is for reading and never counts.',
    look: 'The health column: when each feed was last read, and any that failed.',
    actions: [{ label: 'Load the sources', until: '[data-tour="sources-table"]', waitMs: 300000 }] },
  { id: 'record', act: 'Act 2. Problem record', title: 'Build the problem record', persona: 'alice', view: 'briefs',
    say: 'Five approved questions are asked as you, one new conversation each, and composed into one page: each incident, its cause, and how well the cause is supported.',
    look: 'Confirmed is not stated. The verdict names FAA and United as still open, and one confirmed grade is higher than its sources support.',
    actions: [{ label: 'Build the problem record', click: '[data-tour="brief-build"]', until: '[data-tour="brief-headline"]', waitMs: 300000 }] },
  { id: 'send', act: 'Act 2. Problem record', title: 'Send it for approval', persona: 'alice', view: 'briefs',
    say: 'Alice, first line, sends the record for a decision. She cannot approve it herself. The run re-reads the sources, checks the rules and recommends publish or hold.',
    look: 'The recommendation is a rule, not a model: it holds because one cause is graded above its sources.',
    actions: [
      { label: 'Build the problem record', click: '[data-tour="brief-build"]', until: '[data-tour="brief-headline"]', waitMs: 300000, skipIf: '[data-tour="brief-headline"]' },
      { label: 'Send for approval', click: '[data-tour="brief-send"]', until: '[data-tour="wf-card"]', waitMs: 60000 }] },
  { id: 'hold', act: 'Act 2. Problem record', title: 'A named approver decides', persona: 'bob', view: 'approvals',
    say: 'Bob, second line, sees it waiting. His approval is bound to the exact record by a hash. Publishing and holding are dry runs: nothing is sent.',
    look: 'Approvals n of m, the payload hash, and the decision record line once he approves.',
    actions: [{ label: 'Approve the recommendation', click: '[data-tour="wf-approve"]', until: LEFT, waitMs: 90000, findMs: 240000, refresh: '[data-tour="queue-refresh"]' }] },
  { id: 'exposure', act: 'Act 3. Exposure', title: 'Could it reach our systems?', persona: 'alice', view: 'exposure',
    say: 'Five approved questions over a simulated estate, each scored by a stated rule. The overall rating is the highest score, never an average, and it names the questions that set it.',
    look: 'Critical, set by the unpatched domain controllers and the untested recovery. Unknown is shown as unknown, never as zero.',
    actions: [{ label: 'Rate the exposure', click: '[data-tour="exposure-run"]', until: '[data-tour="exposure-done"]', waitMs: 300000 }] },
  { id: 'priorities', act: 'Act 4. Priorities', title: 'Which systems to fix first', persona: 'alice', view: 'priorities',
    say: 'Each system gets likelihood and impact on one four-value scale. Four triggers can lift it. Every row says why. It is a method, not a standard, and the thresholds are demo constants.',
    look: 'The top row, its reasons, and "Not in the risk register yet".',
    actions: [{ label: 'Rank the systems', click: '[data-tour="priorities-run"]', until: '[data-tour="priorities-list"]', waitMs: 300000 }] },
  { id: 'assess', act: 'Act 5. Register', title: 'Send the top system for assessment', persona: 'alice', view: 'priorities',
    say: 'Alice proposes a rating for the top system. The register only ever grows: nothing is edited or deleted, and residual risk is never computed here.',
    look: 'A run card appears under the system with the proposed rating and the control evidence.',
    actions: [
      { label: 'Rank the systems', click: '[data-tour="priorities-run"]', until: '[data-tour="priorities-list"]', waitMs: 300000, skipIf: '[data-tour="priorities-list"]' },
      { label: 'Send for assessment', click: '[data-tour="assess"]', until: '[data-tour="wf-card"]', waitMs: 60000 }] },
  { id: 'second1', act: 'Act 5. Register', title: 'First second-line approval', persona: 'bob', view: 'approvals',
    say: 'A Critical rating needs two people. Bob approves first.', look: 'The card now says one of two approvals.',
    actions: [{ label: 'Approve', click: '[data-tour="wf-approve"]', settleMs: 5000, findMs: 240000, refresh: '[data-tour="queue-refresh"]' }] },
  { id: 'second2', act: 'Act 5. Register', title: 'Second approver, and the register row', persona: 'carol', view: 'approvals',
    say: 'Carol is the second person. Neither the proposer nor the AI can approve. When she does, one row is added to the register.',
    look: 'The run completes and names both approvers.',
    actions: [{ label: 'Approve', click: '[data-tour="wf-approve"]', until: LEFT, waitMs: 90000, findMs: 240000, refresh: '[data-tour="queue-refresh"]' }] },
  { id: 'clocks', act: 'Act 6. Notifications', title: 'A major incident starts the clocks', persona: 'alice', view: 'clocks',
    say: 'No rule decides that an incident is major: a person records it. Only then do the regulator clocks start, and nothing is ever sent to a regulator.',
    look: 'Three invented incidents. The first has no decision, so it has no clock.',
    actions: [
      { label: 'Load the incidents', click: '[data-tour="clocks-load"]', until: '[data-tour="clocks-send"]', waitMs: 300000 },
      { label: 'Send for a major-incident decision', click: '[data-tour="clocks-send"]', until: '[data-tour="wf-card"]', waitMs: 60000 }] },
  { id: 'major', act: 'Act 6. Notifications', title: 'The second line decides', persona: 'bob', view: 'approvals',
    say: 'Bob records the decision. Approving it is the decision: there is no recommendation step on purpose.',
    look: 'After this the Notifications screen shows each deadline to the minute: DORA and MAS.',
    actions: [{ label: 'Record it as major', click: '[data-tour="wf-approve"]', until: LEFT, waitMs: 90000, findMs: 240000, refresh: '[data-tour="queue-refresh"]' }] },
  { id: 'clocks2', act: 'Act 6. Notifications', title: 'The clocks', persona: 'alice', view: 'clocks',
    say: 'Hours count from classification, awareness, or the previous report, whichever the rule says. The later DORA stages are the latest possible times.',
    look: 'Due times in UTC, time left or overdue, and why each deadline is what it is.',
    actions: [{ label: 'Refresh', click: '[data-tour="clocks-load"]', settleMs: 4000 }] },
  { id: 'audit', act: 'Act 7. Audit', title: 'Prove it', persona: 'curator', view: 'audit',
    say: 'Every finished run left one hash-chained entry. The check compares the record with the register row by row. A mismatch is a finding, never explained away.',
    look: 'The chain verifies and the record agrees with the register. Had a row been removed since (a reset does that), it would show as a finding, on purpose.',
    actions: [
      { label: 'Show the record', click: '[data-tour="audit-show"]', until: '[data-tour="audit-check"]', waitMs: 60000 },
      { label: 'Check against the register', click: '[data-tour="audit-check"]', until: '[data-tour="audit-result"]', waitMs: 300000 }] },
]

export type StepState = 'todo' | 'doing' | 'done' | 'skipped' | 'failed'
export const stepLabel = (i: number) => `Step ${i + 1} of ${STEPS.length}`

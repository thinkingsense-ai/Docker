import { describe, expect, it } from 'vitest'
import { approvalLine, dryRunLine, reasonText, shortHash, stageLabel, startable, TERMINAL, type Definition, type Run } from './workflow'

const pay: Definition = { id: 'payment-exception', title: 'Payment exception', keyField: 'payment_id', requiredApprovals: 2 }
const run = (o: Partial<Run>): Run => ({ id: 'r', definition: 'd', key: '1', title: 't', initiator: 'a', stage: 'facts', stageOrder: [], recommendation: null, rules: [], evidence: {}, approvals: [], requiredApprovals: 2, payloadHash: null, rejection: null, writeBack: null, you: { canApprove: false, reason: null }, ...o })

describe('reasonText', () => {
  it('says every refusal the Server can give in plain words', () => {
    for (const c of ['missing_grant', 'initiator_cannot_approve', 'non_human_identity', 'already_approved', 'not_an_approver', 'not_awaiting_approval', 'payload_hash_mismatch', 'engine_unavailable', 'workflows_off'])
      expect(reasonText(c)).not.toMatch(/^Refused/)
  })
  it('tells the person to read the card again after a hash mismatch', () => { expect(reasonText('payload_hash_mismatch')).toMatch(/reloaded/) })
  it('does not hide an unknown code', () => { expect(reasonText('brand_new')).toBe('Refused (brand_new).'); expect(reasonText(null)).toBe('') })
})

describe('startable', () => {
  it('finds the key column case-insensitively and by exact name only', () => {
    expect(startable(['Entity', 'Payment_ID', 'amount'], [pay])).toEqual([{ column: 1, def: pay }])
    expect(startable(['payment_id_old', 'x'], [pay])).toEqual([])
  })
  it('skips definitions without a key field', () => { expect(startable(['payment_id'], [{ ...pay, keyField: null }])).toEqual([]) })
})

describe('run wording', () => {
  it('labels stages and knows which are final', () => { expect(stageLabel('awaiting_approval')).toBe('Waiting for approval'); expect(TERMINAL).toEqual(['written_back', 'rejected']) })
  it('never calls a dry run a write', () => {
    expect(dryRunLine({ mode: 'dry_run', status: 'simulated', call: 'POST /payments/35/hold', at: '' })).toMatch(/Nothing was sent/)
    expect(dryRunLine(null)).toBe('')
  })
  it('counts approvals and shortens the hash', () => {
    expect(approvalLine(run({ approvals: [{ user: 'bob', at: '' }] }))).toBe('1 of 2 approvals (bob)')
    expect(shortHash('9b74c9897bac770ffc029102a200c5de')).toBe('9b74c9897bac…'); expect(shortHash(null)).toBe('not available yet')
  })
})

import { ruleLabel, incidentRejection, incidentStage, incidentWords, isIncident, ON_HOLD, SENT_BACK } from './workflow'
describe('the incident brief run', () => {
  const r = (o: Partial<Run>) => run({ definition: 'incident-cluster-rca', ...o })
  it('words the buttons after what the run recommends', () => {
    expect(incidentWords(r({ recommendation: { action: 'publish', reason: '' } }))).toMatchObject({ approve: 'Publish problem record', decline: 'Hold it…', prefix: ON_HOLD })
    expect(incidentWords(r({ recommendation: { action: 'hold', reason: '' } }))).toMatchObject({ approve: 'Confirm hold', decline: 'Send back…', prefix: SENT_BACK })
    expect(isIncident(r({}))).toBe(true); expect(isIncident(run({}))).toBe(false)
  })
  it('reads a rejection back as a hold, a send-back or a plain decline', () => {
    const x = (reason: string) => r({ stage: 'rejected', rejection: { user: 'bob', reason, at: '' } })
    expect(incidentStage(x(ON_HOLD + 'a primary source'), 'rejected')).toBe('On hold'); expect(incidentRejection(x(ON_HOLD + 'a primary source'))).toBe('Put on hold by bob: a primary source')
    expect(incidentStage(x(SENT_BACK + 'regrade NSANet'), 'rejected')).toBe('Sent back'); expect(incidentRejection(x(SENT_BACK + 'regrade NSANet'))).toBe('Sent back by bob: regrade NSANet')
    expect(incidentStage(x('no'), 'rejected')).toBe('Declined')
  })
  it('names the finished stage after the action', () => {
    expect(incidentStage(r({ recommendation: { action: 'publish', reason: '' } }), 'written_back')).toBe('Published (dry run)')
    expect(incidentStage(r({ recommendation: { action: 'hold', reason: '' } }), 'written_back')).toBe('Hold recorded (dry run)')
  })
})

describe('ruleLabel', () => {
  it('introduces the gateway rule lines in plain words and keeps named checks', () => {
    expect(ruleLabel({ name: 'block', passed: false, detail: '' })).toBe('Blocked:'); expect(ruleLabel({ name: 'note', passed: true, detail: '' })).toBe('Note:')
    expect(ruleLabel({ name: 'allowed_actions', passed: true, detail: '' })).toBe('Allowed:'); expect(ruleLabel({ name: 'patch_within_policy', passed: false, detail: '' })).toBe('Failed patch within policy:')
  })
})

import { assessmentStage, assessmentWords, isAssessment, isMajor, majorStage, majorWords } from './workflow'
describe('risk assessment wording', () => {
  const run = (o: object) => ({ definition: 'risk-assessment', recommendation: { action: 'record', reason: '', source: 'workflow' }, rejection: null, writeBack: null, ...o }) as never
  it('words approve and send back for the second line', () => {
    expect(isAssessment(run({}))).toBe(true)
    expect(assessmentWords(run({}))).toMatchObject({ approve: 'Record in the register', decline: 'Send back…', prefix: 'Sent back: ' })
    expect(assessmentWords(run({ recommendation: { action: 'hold', reason: '' } })).approve).toBe('Confirm hold')
  })
  it('says where it ended, and does not claim a dry run before anything is written', () => {
    expect(assessmentStage(run({}), 'written_back')).toBe('Recorded in the register')
    expect(assessmentStage(run({ writeBack: { mode: 'dry_run', status: 'simulated', call: 'x', at: '' } }), 'written_back')).toBe('Recorded (dry run)')
    expect(assessmentStage(run({ writeBack: { mode: 'live', status: 'sent', call: 'INSERT register.assessments #4', at: '' } }), 'written_back')).toBe('Recorded in the register')
    expect(assessmentStage(run({ rejection: { user: 'bob', reason: 'Sent back: x', at: '' } }), 'rejected')).toBe('Sent back')
  })
  it('describes a register write as an addition, not a dry run', () => {
    expect(dryRunLine({ mode: 'live', status: 'sent', call: 'INSERT register.assessments #4', at: '' })).toBe('Added to the risk register: register.assessments #4. The register is append-only: earlier ratings stay.')
  })
})

describe('major-incident wording', () => {
  const run = (o: object) => ({ definition: 'major-incident', recommendation: null, rejection: null, writeBack: null, ...o }) as never
  it('words the decision as the approver\'s, with no recommendation behind it', () => {
    expect(isMajor(run({}))).toBe(true); expect(majorWords()).toMatchObject({ approve: 'Record as major', decline: 'Not major…', prefix: 'Not major: ' })
  })
  it('says the clocks started only when it was recorded, and that a refusal starts none', () => {
    expect(majorStage(run({}), 'written_back')).toBe('Recorded as major: clocks started')
    expect(majorStage(run({ rejection: { user: 'bob', reason: 'Not major: 15 minutes, no customer impact', at: '' } }), 'rejected')).toBe('Not recorded as major')
    expect(incidentRejection(run({ rejection: { user: 'bob', reason: 'Not major: small', at: '' } }))).toBe('Not recorded as major, by bob: small. No clock starts.')
  })
})

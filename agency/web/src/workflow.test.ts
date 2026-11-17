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

import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'
import type { AuditRow } from './api'
import { RECONCILE_QUESTION, claimedRow, reconcile } from './reconcile'

const row = (o: Partial<AuditRow>): AuditRow => ({ n: 1, runId: 'assess-3', definition: 'risk-assessment', outcome: 'approved', outcomeText: '', startedAt: null, decidedAt: null, approvers: ['bob'], rejectedBy: null, rejectionReason: null, action: 'record', controls: [],
  recommendation: null, rulesBlocked: [], writeBack: { mode: 'live', call: 'register.assessments #4', note: null }, hash: 'h', prev: 'p', evidenceDigest: 'd3', ...o })
const reg = (rows: string[][]) => ({ columns: ['kind', 'row_id', 'run_id', 'evidence_digest', 'about', 'set_by'], rows })

describe('record against register', () => {
  it('asks the approved question word for word', () => {
    const bank = JSON.parse(readFileSync(new URL('../../../demos/it-risk-register/demo-questions-register.json', import.meta.url), 'utf8')) as { question: string }[]
    expect(bank.map((b) => b.question)).toContain(RECONCILE_QUESTION)
  })
  it('reads the row an entry says it wrote, and nothing for a dry run or a hold', () => {
    expect(claimedRow(row({}))).toEqual({ kind: 'assessment', id: '4' })
    expect(claimedRow(row({ writeBack: { mode: 'live', call: 'register.major_incident_decisions #1', note: null } }))).toEqual({ kind: 'major incident', id: '1' })
    expect(claimedRow(row({ writeBack: { mode: 'dry-run', call: '/briefs/x/publish', note: null } }))).toBeNull(); expect(claimedRow(row({ writeBack: null }))).toBeNull()
    expect(claimedRow(row({ writeBack: { mode: 'live', call: 'register.other #1', note: null } }))).toBeNull()
  })
  it('agrees when the row is there with the same run, id and digest', () => {
    expect(reconcile([row({})], reg([['assessment', '4', 'assess-3', 'd3', 'DC', 'bob']]))).toEqual({ checked: 1, agree: 1, findings: [] })
  })
  it('PLANTED: an entry that says it wrote a row that is not there is a finding (a wiped or never-written row)', () => {
    const r = reconcile([row({})], reg([])); expect(r.agree).toBe(0); expect(r.findings).toEqual([expect.objectContaining({ kind: 'no_row', runId: 'assess-3' })])
    expect(reconcile([row({})], reg([['assessment', '9', 'assess-3', 'd3', 'DC', 'bob']])).findings[0].kind).toBe('no_row')           // a row, but not the one the record names
  })
  it('PLANTED: a row whose evidence digest differs from the one the approval was bound to is a finding', () => {
    expect(reconcile([row({})], reg([['assessment', '4', 'assess-3', 'OTHER', 'DC', 'bob']])).findings[0].kind).toBe('digest_differs')
  })
  it('PLANTED: a register row no entry accounts for is a finding', () => {
    const r = reconcile([row({})], reg([['assessment', '4', 'assess-3', 'd3', 'DC', 'bob'], ['assessment', '7', 'assess-9', 'x', 'HR', 'eve']]))
    expect(r.agree).toBe(1); expect(r.findings).toEqual([expect.objectContaining({ kind: 'no_record', runId: 'assess-9' })])
  })
  it('is not fooled by the padding the Server puts on a literal in a UNION (found walking the demo: a real row was reported missing)', () => {
    expect(reconcile([row({})], reg([['assessment    ', '4', 'assess-3', 'd3', 'DC', 'bob']]))).toEqual({ checked: 1, agree: 1, findings: [] })
  })
  it('a dry run or a hold needs no row, and an unanswered question is not an agreement', () => {
    expect(reconcile([row({ writeBack: { mode: 'dry-run', call: 'x', note: null } })], reg([]))).toEqual({ checked: 0, agree: 0, findings: [] })
    expect(reconcile([row({})], undefined).findings[0].kind).toBe('no_row')
  })
})

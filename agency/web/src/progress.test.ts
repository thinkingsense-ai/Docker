import { describe, expect, it } from 'vitest'
import { checkLabel, checkState, fmtMs, summarize, type ProgressEvent } from './progress'

// The order the Server really sent for an approved question (seen on app 0.10.21): note "sql" before "planned" and checks after "executing".
const real = (t0: number): ProgressEvent[] => [['understanding', 0], ['sql', 200], ['planned', 400, { backends: ['pg'], source: 'question_bank' }], ['ontology', 600], ['check', 800, { status: 'pass' }], ['check', 900, { status: 'pass' }],
  ['check', 1000, { status: 'skipped' }], ['executing', 1500], ['check', 1600, { status: 'pass' }], ['explain_plan', 2500], ['confidence', 2600], ['plan_narrative', 2700], ['results', 9000], ['answering', 9500]]
  .map(([step, dt, extra]) => ({ step: step as string, t: t0 + (dt as number), ...((extra as object) ?? {}) }))

describe('summarize', () => {
  it('turns a dozen internal steps into six plain stages', () => {
    const p = summarize(real(1000), 1000 + 10_000, 1000)
    expect(p.stages.map((s) => s.label)).toEqual(['Reading your question', 'Choosing where to look', 'Writing the query', 'Checking it is safe and sound', 'Getting the data', 'Writing the answer'])
    expect(p.stages.map((s) => s.state)).toEqual(['done', 'done', 'done', 'done', 'done', 'now'])
  })
  it('never goes back when a check arrives after the query started running', () => { const p = summarize(real(0).slice(0, 9), 3000, 0); expect(p.stages.find((s) => s.state === 'now')!.id).toBe('run') })
  it('says what an approved question reused, where it looked, and how many checks passed', () => {
    const p = summarize(real(0), 10_000, 0)
    expect(p.reused).toBe(true); expect(p.stages[1].detail).toBe('Matched an approved question; looking in pg'); expect(p.stages[2].detail).toBe('Reused the approved query'); expect(p.stages[3].detail).toBe('3 of 4 checks passed')
  })
  it('times each stage until the next one starts, and the current one against the clock', () => {
    const p = summarize(real(0), 10_000, 0); expect(p.stages[4].ms).toBe(9500 - 1500); expect(p.stages[5].ms).toBe(10_000 - 9500); expect(p.totalMs).toBe(10_000)
  })
  it('before any event, the first stage is in progress and the clock runs', () => {
    const p = summarize([], 5000, 2000); expect(p.stages[0]).toMatchObject({ state: 'now', ms: 3000 }); expect(p.stages.slice(1).every((s) => s.state === 'next')).toBe(true); expect(p.totalMs).toBe(3000)
  })
  it('a done event finishes every stage and stops the clock at the last event', () => {
    const p = summarize([...real(0), { step: 'done', t: 9800 }], 99_999, 0); expect(p.finished).toBe(true); expect(p.stages.every((s) => s.state === 'done')).toBe(true); expect(p.totalMs).toBe(9800)
  })
  it('a generated query has no "reused" wording', () => {
    const p = summarize([{ step: 'understanding', t: 0 }, { step: 'planned', t: 100, backends: ['pg', 'mdb'], source: 'generated' }, { step: 'sql', t: 200 }], 300, 0)
    expect(p.reused).toBe(false); expect(p.stages[1].detail).toBe('looking in pg, mdb'); expect(p.stages[2].detail).toBeUndefined()
  })
  it('a stopped run is reported and its clock stops', () => { const p = summarize([{ step: 'understanding', t: 0 }, { step: 'stopped', t: 500 }], 9000, 0); expect(p.stopped).toBe(true); expect(p.totalMs).toBe(500) })
  it('ignores steps it does not know instead of showing them', () => { expect(summarize([{ step: 'something_new', t: 5 }], 10, 0).stages.filter((s) => s.state !== 'next').length).toBe(1) })
})

describe('words', () => {
  it('formats durations for a person', () => { expect([fmtMs(300), fmtMs(1200), fmtMs(14_400), fmtMs(75_000)]).toEqual(['<1 s', '1.2 s', '14 s', '1 min 15 s']) })
  it('names the Server checks in plain words and tolerates new ones', () => {
    expect(checkLabel('dml_safety')).toBe('Only reads data, never changes it'); expect(checkLabel('row_limit_guard')).toBe('Row limit guard')
  })
  it('says pass, skipped and failure in words, not colour alone', () => {
    expect(checkState('pass')).toEqual({ text: 'passed', ok: true }); expect(checkState('skipped')).toEqual({ text: 'not needed', ok: null }); expect(checkState('fail')).toEqual({ text: 'failed', ok: false }); expect(checkState('warn').text).toBe('warning')
  })
})

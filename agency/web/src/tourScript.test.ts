import { describe, expect, it } from 'vitest'
import { NAV } from './shell'
import { PERSONAS, STEPS, stepsFor } from './tourScript'

describe('the guided tour script', () => {
  it('has unique step ids and only known people and screens', () => {
    expect(new Set(STEPS.map((s) => s.id)).size).toBe(STEPS.length)
    for (const s of STEPS) { expect(Object.keys(PERSONAS)).toContain(s.persona); expect(NAV.map((n) => n.id)).toContain(s.view); expect(s.say.length).toBeGreaterThan(20); expect(s.look.length).toBeGreaterThan(10) }
  })
  it('only presses buttons the screens mark for the tour', () => {
    const sels = STEPS.flatMap((s) => s.actions.flatMap((a) => [a.click, a.until].filter(Boolean) as string[]))
    const known = ['brief-build', 'brief-headline', 'brief-send', 'wf-card', 'wf-approve', 'exposure-run', 'exposure-done', 'priorities-run', 'priorities-list', 'assess', 'clocks-load', 'clocks-send', 'audit-show', 'audit-check', 'audit-result', 'queue-refresh', 'watch-card', 'sources-table']
    for (const q of sels) { const m = q.match(/data-tour="([a-z-]+)"/); if (m) expect(known).toContain(m[1]) }
  })
  it('puts approvals in the hands of people who may approve, and never lets the proposer approve', () => {
    for (const s of STEPS.filter((x) => x.actions.some((a) => a.click?.includes('wf-approve')))) expect(['bob', 'carol']).toContain(s.persona)
    for (const s of STEPS.filter((x) => x.actions.some((a) => /brief-send|assess|clocks-send/.test(a.click ?? '')))) expect(['alice', 'curator']).toContain(s.persona)
  })
  it('every data-tour name in the script exists in a screen file', async () => {
    const { readFileSync } = await import('node:fs')
    const src = ['Brief', 'Workflows', 'Exposure', 'Priorities', 'Clocks', 'Audit', 'Watch', 'Sources'].map((f) => readFileSync(`src/${f}.tsx`, 'utf8')).join('\n')
    for (const q of STEPS.flatMap((s) => s.actions.flatMap((a) => [a.click, a.until, a.refresh].filter(Boolean) as string[]))) { const m = q.match(/data-tour="([a-z-]+)"/); if (m) expect(src).toContain(`data-tour="${m[1]}"`) }
  })
})

describe('the read-only tour', () => {
  const ro = stepsFor(true)
  it('has only the screens that read, and starts nothing', () => {
    expect(ro.map((s) => s.id)).toEqual(['watch', 'sources', 'record', 'exposure', 'priorities', 'clocks'])
    const clicks = ro.flatMap((s) => s.actions.map((a) => a.click ?? ''))
    for (const bad of ['brief-send', 'assess', 'clocks-send', 'wf-approve', 'wf-reject']) expect(clicks.join(' ')).not.toContain(bad)
  })
  it('keeps the full tour whole when it is not read-only', () => { expect(stepsFor(false).length).toBe(STEPS.length); expect(stepsFor(false).some((s) => s.id === 'hold')).toBe(true) })
  it('only the first action of the notifications step runs', () => { expect(ro.find((s) => s.id === 'clocks')!.actions.length).toBe(1) })
})

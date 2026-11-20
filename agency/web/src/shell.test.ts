import { describe, expect, it } from 'vitest'
import { NAV, navFor, startWorkspace, viewFor, workspaceChoices } from './shell'
import type { Pack } from './api'

const pack = (id: string) => ({ id, title: id.toUpperCase() } as unknown as Pack)

describe('navigation', () => {
  it('lists Watch, Exposure, Briefs, Approvals, Sources and Ask in that order', () => {
    expect(NAV.map((n) => n.id)).toEqual(['watch', 'exposure', 'briefs', 'approvals', 'sources', 'ask'])
  })
  it('hides Approvals without the approve grant and shows it with', () => {
    expect(navFor({ canApprove: false }).map((n) => n.id)).not.toContain('approvals')
    expect(navFor({ canApprove: true }).map((n) => n.id)).toContain('approvals')
  })
  it('falls back to Watch when the person can no longer open the view', () => {
    expect(viewFor('approvals', { canApprove: false })).toBe('watch')
    expect(viewFor('approvals', { canApprove: true })).toBe('approvals')
    expect(viewFor('briefs', { canApprove: false })).toBe('briefs')
  })
  it('marks the screens whose build step has not landed, so they say so', () => {
    expect(NAV.filter((n) => !n.built).map((n) => n.id)).toEqual(['exposure', 'sources'])
  })
})

describe('workspace menu', () => {
  it('offers only IT risk when the stack carries it', () => {
    expect(workspaceChoices([pack('bom'), pack('it-risk'), pack('treasury')]).map((p) => p.id)).toEqual(['it-risk'])
  })
  it('offers every pack when the stack has no IT risk, so the menu is never empty', () => {
    expect(workspaceChoices([pack('bom'), pack('treasury')]).map((p) => p.id)).toEqual(['bom', 'treasury'])
  })
  it('starts in IT risk even if a remembered choice is another pack', () => {
    expect(startWorkspace([pack('bom'), pack('it-risk')], 'bom')).toBe('it-risk')
  })
  it('keeps a remembered choice that is on offer, and returns none for no packs', () => {
    expect(startWorkspace([pack('bom'), pack('treasury')], 'treasury')).toBe('treasury')
    expect(startWorkspace([], 'it-risk')).toBeNull()
  })
})

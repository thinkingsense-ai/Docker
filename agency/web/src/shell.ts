// The IT-risk shell (docs/agency-it-risk-flow.md, sections 4 and 7): which screens exist, which the signed-in person sees, and which Workspaces the dropdown offers. Pure, so it is unit-tested.
import type { Pack } from './api'
import { BRIEF_PACK } from './rcaBrief'

export type View = 'watch' | 'exposure' | 'priorities' | 'briefs' | 'approvals' | 'sources' | 'ask'

export interface NavItem { id: View; label: string; hint: string; built: boolean }

// Order is the order in the left navigation. `built` is false for a screen whose build step has not landed (none now).
export const NAV: NavItem[] = [
  { id: 'watch', label: 'Watch', hint: 'Incidents in the news that may be AI hacking', built: true },
  { id: 'exposure', label: 'Exposure', hint: 'Could this happen to our systems', built: true },
  { id: 'priorities', label: 'Priorities', hint: 'Which systems to fix first', built: true },
  { id: 'briefs', label: 'Problem records', hint: 'Root-cause problem records and their approval', built: true },
  { id: 'approvals', label: 'Approvals', hint: 'Problem records waiting for you', built: true },
  { id: 'sources', label: 'Sources', hint: 'Where the feed comes from', built: true },
  { id: 'ask', label: 'Ask a question', hint: 'Approved and free-form questions', built: true },
]

/** The navigation this person sees: Approvals only with the approve grant (the Server enforces it again on every call). */
export function navFor(g: { canApprove: boolean }): NavItem[] {
  return NAV.filter((n) => n.id !== 'approvals' || g.canApprove)
}

/** A view the person cannot open (their grant went away, or they signed out and in as someone else) falls back to Watch. */
export function viewFor(want: View, g: { canApprove: boolean }): View {
  return navFor(g).some((n) => n.id === want) ? want : 'watch'
}

/**
 * The Workspaces the dropdown offers. For now one: IT risk. A stack that does not carry it (the layer's catalogue has no `it-risk`)
 * lists every pack instead, so the app stays usable rather than showing an empty menu.
 */
export function workspaceChoices(packs: Pack[]): Pack[] {
  const it = packs.filter((p) => p.id === BRIEF_PACK)
  return it.length ? it : packs
}

/** The Workspace to start in: the remembered one if it is on offer, else the first on offer, else none. */
export function startWorkspace(packs: Pack[], want: string | null | undefined): string | null {
  const options = workspaceChoices(packs)
  return (options.find((p) => p.id === want) ?? options[0])?.id ?? null
}

/** The line the person holds, as far as it can be told. The Server has grants for starting and approving; a read-only grant for audit does not exist yet, so the third line is inferred from having neither. */
export function roleLabel(g: { canStart: boolean; canApprove: boolean }): { text: string; note: string } {
  const note = 'Inferred from your grants: starting a run is the first line, approving is the second, and neither is read-only (the third line). The Server enforces the grants on every call.'
  if (g.canStart && g.canApprove) return { text: 'First and second line', note }
  if (g.canApprove) return { text: 'Second line: you approve', note }
  if (g.canStart) return { text: 'First line: you propose', note }
  return { text: 'Read only', note }
}

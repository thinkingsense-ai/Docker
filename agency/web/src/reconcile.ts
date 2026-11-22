// Record against register (docs/agency-risk-register-plan.md, step 8g): every register row a workflow wrote should have a decision-record entry that says so, and every entry that says it wrote a row
// should find that row, with the same run and the same evidence digest. Pure, so it is unit-tested. A mismatch is a FINDING for a person, not a verdict: it says what does not line up, not why.
import type { AuditRow } from './api'
import { records, type Table } from './rcaBrief'

export const RECONCILE_QUESTION = 'Which workflow runs wrote the risk register and the major-incident decisions?'
export type Finding = { kind: 'no_row' | 'digest_differs' | 'no_record'; runId: string; detail: string }
export interface Reconciliation { checked: number; agree: number; findings: Finding[] }

const TABLES: Record<string, string> = { 'register.assessments': 'assessment', 'register.major_incident_decisions': 'major incident' }

/** The register row an entry says it wrote: {kind, id}, or null for a dry run, a hold or an entry that wrote nothing. */
export function claimedRow(r: AuditRow): { kind: string; id: string } | null {
  if (r.writeBack?.mode !== 'live' || !r.writeBack.call) return null
  const m = /^(register\.\w+) #(\d+)$/.exec(r.writeBack.call)
  return m && TABLES[m[1]] ? { kind: TABLES[m[1]], id: m[2] } : null
}

export function reconcile(audit: AuditRow[], registerTable: Table | undefined): Reconciliation {
  // The Server types a string literal in a UNION to the longest branch and pads it ('assessment    '), so every value is trimmed before it is compared.
  const reg = records(registerTable).map((r) => Object.fromEntries(Object.entries(r).map(([k, v]) => [k, String(v ?? '').trim()]))); const byRun = new Map(reg.map((r) => [r.run_id, r])); const claimed = new Set<string>()
  const findings: Finding[] = []; let checked = 0, agree = 0
  for (const r of audit) {
    const c = claimedRow(r); if (!c) continue
    checked++; claimed.add(r.runId)
    const row = byRun.get(r.runId)
    if (!row || row.kind !== c.kind || row.row_id !== c.id) findings.push({ kind: 'no_row', runId: r.runId, detail: `The record says this run wrote ${c.kind} row #${c.id}, but the register has no such row for it.` })
    else if (r.evidenceDigest && row.evidence_digest !== r.evidenceDigest) findings.push({ kind: 'digest_differs', runId: r.runId, detail: `Row #${c.id} exists, but its evidence digest is not the one the approval was bound to.` })
    else agree++
  }
  for (const row of reg) if (!claimed.has(row.run_id)) findings.push({ kind: 'no_record', runId: row.run_id, detail: `The register has ${row.kind} row #${row.row_id} from this run, but no decision-record entry says it wrote it (or the entry is outside the current filter).` })
  return { checked, agree, findings }
}

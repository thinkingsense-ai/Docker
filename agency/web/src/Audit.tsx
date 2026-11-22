import { useCallback, useState } from 'react'
import { api, ask, ApiError, auditQuery, type AuditFilters, type AuditView } from './api'
import { BRIEF_PACK, type Table } from './rcaBrief'
import { RECONCILE_QUESTION, reconcile, type Reconciliation } from './reconcile'

const short = (h: string) => `${h.slice(0, 10)}…`
const when = (s: string | null) => (s ? s.replace('T', ' ').replace(/(\.\d+)?(\+00:00|Z)$/, '') + ' UTC' : '')
const OUTCOME_WORD: Record<string, string> = { approved: 'Approved', declined: 'Declined', expired: 'Expired', escalated: 'Escalated' }

/** Audit: the workflow decision record, for someone who reads it. Every finished run (payment, vulnerability, incident brief, risk assessment, major incident) has one hash-chained entry; this view lists them,
 *  filters by workflow, actor, outcome, control and date, shows whether the chain still verifies, and downloads the selection as JSON lines. It is NOT signed: a signature has to come from the Server, which has none yet. */
export default function Audit({ onSignedOut }: { onSignedOut: () => void }) {
  const [f, setF] = useState<AuditFilters>({})
  const [v, setV] = useState<AuditView | null>(null)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  const [rec, setRec] = useState<Reconciliation | null>(null)
  const [checking, setChecking] = useState(false)
  async function check() {
    if (!v) return
    setChecking(true); setErr('')
    try { const a = await ask(RECONCILE_QUESTION, BRIEF_PACK, null, () => {}, new AbortController().signal); const t: Table = { columns: a.columns ?? [], rows: a.rows ?? [] }; setRec(reconcile(v.rows, t)) }
    catch (e) { if (e instanceof ApiError && e.status === 401) return onSignedOut(); setErr(e instanceof Error ? e.message : 'The register could not be read.') }
    finally { setChecking(false) }
  }
  const set = (k: keyof AuditFilters) => (e: { target: { value: string } }) => setF((x) => ({ ...x, [k]: e.target.value }))

  const load = useCallback(async (filters: AuditFilters) => {
    setBusy(true); setErr('')
    try { setV(await api.auditRecords(filters)); setRec(null) }
    catch (e) {
      if (e instanceof ApiError && e.status === 401) return onSignedOut()
      setErr(e instanceof ApiError ? (e.status === 403 ? 'Your account is not on this deployment\'s audit list.' : e.message) : (e as Error).message)
    } finally { setBusy(false) }
  }, [onSignedOut])
  const clear = () => { setF({}); void load({}) }
  const q = auditQuery(f)

  return (
    <section className="audit" aria-label="Audit">
      <header className="brief-head">
        <h2>Audit: the decision record</h2>
        <p className="notbuilt" role="note"><strong>Not signed.</strong> Each run that finished left one hash-chained entry, so a changed, deleted or reordered line is detectable. A signature an auditor can trust has to come from the Server, which has none yet; until then an export carries the chain and its head, and nobody has signed it. Access to this screen is a list kept by this deployment, not a Server-enforced role.</p>
        <form className="auditform" onSubmit={(e) => { e.preventDefault(); void load(f) }}>
          <label>Workflow <select value={f.definition ?? ''} onChange={set('definition')}><option value="">All</option>{(v?.definitions ?? []).map((d) => <option key={d} value={d}>{d}</option>)}</select></label>
          <label>Outcome <select value={f.outcome ?? ''} onChange={set('outcome')}><option value="">All</option>{Object.entries(OUTCOME_WORD).map(([k, w]) => <option key={k} value={k}>{w}</option>)}</select></label>
          <label>Person <input value={f.actor ?? ''} onChange={set('actor')} placeholder="approver or rejector" maxLength={100} /></label>
          <label>Control <input value={f.control ?? ''} onChange={set('control')} placeholder="control, category or regulator" maxLength={100} list="audit-controls" /></label>
          <datalist id="audit-controls">{(v?.controls ?? []).map((c) => <option key={c} value={c} />)}</datalist>
          <label>Run <input value={f.run ?? ''} onChange={set('run')} placeholder="e.g. assess-3" maxLength={100} /></label>
          <label>From <input type="date" value={f.since ?? ''} onChange={set('since')} /></label>
          <label>To <input type="date" value={f.until ?? ''} onChange={set('until')} /></label>
          <div className="brief-actions"><button className="primary" disabled={busy}>{busy ? 'Loading…' : v ? 'Apply filters' : 'Show the record'}</button>
            {v && <button type="button" onClick={clear} disabled={busy}>Clear</button>}
            {v && <a className="button" href={'/audit/export' + (q ? '?' + q : '')} download="decision-record.jsonl">Download these {v.rows.length} as JSON lines</a>}</div>
        </form>
        {err && <p role="alert" className="error">{err}</p>}
      </header>
      {v && (
        <>
          <p role="status" className={v.chainValid ? '' : 'error'}><strong>{v.chainValid ? 'The hash chain verifies' : `The hash chain is BROKEN at entry ${v.firstBadEntry}`}</strong> across all {v.total} runs in the record (head <code title={v.head}>{short(v.head)}</code>). {v.rows.length === v.total ? 'All of them are shown.' : `${v.rows.length} match the filters.`}</p>
          <p className="brief-actions"><button onClick={check} disabled={checking || v.rows.length === 0}>{checking ? 'Reading the register…' : 'Check these against the register'}</button>
            <span className="muted small">Asks the register, as you, which rows these runs wrote, and compares run, row and evidence digest.</span></p>
          {rec && (rec.findings.length === 0
            ? <p role="status"><strong>The record and the register agree</strong> for the {rec.checked} run{rec.checked === 1 ? '' : 's'} that wrote a row.</p>
            : <div role="alert" className="error"><p><strong>{rec.findings.length} thing{rec.findings.length === 1 ? '' : 's'} do not line up</strong> ({rec.agree} of {rec.checked} runs that wrote a row agree). A mismatch is a finding for a person, not a verdict on why.</p>
              <ul className="plain small">{rec.findings.map((x, i) => <li key={i}><code>{x.runId}</code>: {x.detail}</li>)}</ul></div>)}
          {v.rows.length === 0 ? <p className="muted">No run matches these filters.</p> : (
            <div className="tablewrap"><table>
              <thead><tr><th>Decided</th><th>Run</th><th>Workflow</th><th>Outcome</th><th>By</th><th>Controls</th><th>What was done</th></tr></thead>
              <tbody>{v.rows.map((r) => (
                <tr key={r.n}>
                  <td>{when(r.decidedAt)}</td><td><code>{r.runId}</code></td><td>{r.definition}</td>
                  <td><span className={'score ' + (r.outcome === 'approved' ? 's1' : r.outcome === 'declined' ? 's2' : 's3')}>{OUTCOME_WORD[r.outcome]}</span></td>
                  <td>{r.approvers.length ? r.approvers.join(', ') : r.rejectedBy ?? ''}</td><td className="small">{r.controls.join(', ')}</td>
                  <td className="small">{r.writeBack ? `${r.writeBack.mode === 'dry-run' ? 'Dry run: ' : r.writeBack.mode === 'live' ? 'Written: ' : ''}${r.writeBack.call ?? r.writeBack.note ?? ''}` : r.rejectionReason ?? r.outcomeText}
                    <details><summary>Detail</summary>
                      <ul className="plain small">
                        <li>Outcome text: {r.outcomeText}</li>
                        {r.recommendation && <li>Recommendation: {r.recommendation}</li>}
                        {r.rulesBlocked.length > 0 && <li>Rules blocked: {r.rulesBlocked.join('; ')}</li>}
                        {r.evidenceDigest && <li>Digest the approval was bound to: <code title={r.evidenceDigest}>{short(r.evidenceDigest)}</code></li>}
                        <li>Entry {r.n}: <code title={r.hash}>{short(r.hash)}</code> after <code title={r.prev}>{short(r.prev)}</code></li>
                      </ul></details></td>
                </tr>))}</tbody></table></div>)}
        </>
      )}
    </section>
  )
}

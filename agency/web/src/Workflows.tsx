import { useCallback, useEffect, useRef, useState } from 'react'
import { api, ApiError } from './api'
import { approvalLine, dryRunLine, incidentRejection, incidentStage, incidentWords, isIncident, reasonText, ruleLabel, shortHash, stageLabel, TERMINAL, type Decisions, type Run } from './workflow'

interface Props { initial: Run; me: string; onSignedOut: () => void; onChange?: (run: Run) => void }

/** One workflow run: progress, rules, the AI recommendation, who approved, and the buttons the Server allows. The Server enforces every rule; this card only shows and relays. */
export function RunCard({ initial, me, onSignedOut, onChange }: Props) {
  const [run, setRun] = useState<Run>(initial)
  const [note, setNote] = useState('')
  const [busy, setBusy] = useState(false)
  const [rejecting, setRejecting] = useState(false)
  const [reason, setReason] = useState('')
  const [dec, setDec] = useState<Decisions | null>(null)
  const [decNote, setDecNote] = useState('')
  const alive = useRef(true)
  useEffect(() => () => { alive.current = false }, [])

  const fail = useCallback((e: unknown) => {
    if (e instanceof ApiError && e.status === 401) return onSignedOut()
    setNote(e instanceof ApiError ? reasonText(e.code) || e.message : (e as Error).message)
  }, [onSignedOut])

  const reload = useCallback(async () => {
    try { const r = await api.workflowRun(run.id); if (alive.current) setRun(r.run) } catch (e) { if (alive.current) fail(e) }
  }, [run.id, fail])

  // stages move on their own: poll quickly while it works, slowly while it waits for people, not at all once it is finished
  useEffect(() => {
    if (TERMINAL.includes(run.stage)) return
    const t = setInterval(reload, run.stage === 'awaiting_approval' ? 5000 : 1500)
    return () => clearInterval(t)
  }, [run.stage, reload])

  async function act(f: () => Promise<{ run: Run }>) {
    setBusy(true); setNote('')
    try { const r = await f(); setRun(r.run); setRejecting(false); setReason(''); onChange?.(r.run) }
    catch (e) { fail(e); if (e instanceof ApiError && ['payload_hash_mismatch', 'not_awaiting_approval'].includes(e.code)) await reload() }
    finally { setBusy(false) }
  }

  async function showRecord() {
    setDecNote('')
    try { setDec(await api.decisions(run.id)) } catch (e) { setDecNote(e instanceof ApiError ? e.message : (e as Error).message) }
  }

  const waiting = run.stage === 'awaiting_approval'
  const canReject = waiting && (run.you.canApprove || run.initiator === me)
  const withdraw = !run.you.canApprove && run.initiator === me      // the Server lets the person who started a run withdraw it, though not approve it
  const simulated = run.recommendation?.source === 'stub'
  const inc = isIncident(run); const words = incidentWords(run)
  const stageText = (st: string) => (inc ? incidentStage(run, st) : stageLabel(st))
  const order = run.stageOrder?.length ? run.stageOrder : ['facts', 'rules', 'recommendation', 'awaiting_approval', 'approved', 'written_back']
  const evidence = Object.entries(run.evidence ?? {}).filter(([k]) => k !== 'definition' && k !== 'key')

  return (
    <article className="run" aria-label={`${run.title} ${run.key}`}>
      <h3>{run.title} <span className="tag">{run.key}</span> <span className="muted small">started by {run.initiator}</span></h3>
      <ol className="stages" aria-label="Progress">
        {order.filter((s) => s !== 'approved' || run.stage === 'approved').map((s) => (
          <li key={s} aria-current={s === run.stage ? 'step' : undefined} className={s === run.stage ? 'now' : order.indexOf(s) < order.indexOf(run.stage) ? 'past' : ''}>{stageText(s)}</li>
        ))}
        {run.stage === 'rejected' && <li aria-current="step" className="now">{stageText('rejected')}</li>}
      </ol>
      {evidence.length > 0 && simulated && <p className="muted small">These values come from the local simulator's example data, not from this payment.</p>}
      {evidence.length > 0 && <dl className="facts small">{evidence.map(([k, v]) => <div key={k}><dt>{k}</dt><dd>{String(v)}</dd></div>)}</dl>}
      {run.rules.length > 0 && <ul className="rules small" aria-label="Rules">{run.rules.map((r, i) => <li key={r.name + i}><strong>{ruleLabel(r)}</strong> {r.detail}</li>)}</ul>}
      {run.recommendation && (
        <p className="rec"><strong>Recommendation: {run.recommendation.action}.</strong> {run.recommendation.reason}{' '}
          <span className="muted small">{run.recommendation.source === 'stub' ? '(simulated by the local engine, not a model)' : run.recommendation.source ? `(source: ${run.recommendation.source})` : ''}</span></p>
      )}
      {(waiting || run.approvals.length > 0) && <p className="small">{approvalLine(run)}.{waiting && <> Each approval is bound to hash <code title={run.payloadHash ?? ''}>{shortHash(run.payloadHash)}</code> of exactly what you see here.</>}</p>}
      {run.rejection && (inc ? <p className="small"><strong>{incidentRejection(run)}</strong></p> : <p className="small"><strong>Rejected by {run.rejection.user}:</strong> {run.rejection.reason}</p>)}
      {run.writeBack && <p className="small">{dryRunLine(run.writeBack)}</p>}
      {waiting && (
        <div className="actions">
          <button className="primary" disabled={busy || !run.you.canApprove || !run.payloadHash} onClick={() => act(() => api.approveWorkflow(run.id, run.payloadHash!))}>{inc ? words.approve : 'Approve'}</button>
          {canReject && !rejecting && <button disabled={busy} onClick={() => setRejecting(true)}>{inc ? (withdraw ? 'Withdraw…' : words.decline) : withdraw ? 'Withdraw…' : 'Reject…'}</button>}
          {!run.you.canApprove && <span className="muted small" role="note">You cannot approve: {reasonText(run.you.reason) || 'not available.'}</span>}
        </div>
      )}
      {rejecting && (
        <form className="actions" onSubmit={(e) => { e.preventDefault(); if (reason.trim()) act(() => api.rejectWorkflow(run.id, (inc && !withdraw ? words.prefix : '') + reason.trim())) }}>
          <label className="sr" htmlFor={`why-${run.id}`}>{inc ? words.ask : 'Reason for rejecting'}</label>
          <input id={`why-${run.id}`} value={reason} onChange={(e) => setReason(e.target.value)} placeholder={withdraw ? 'Why are you withdrawing this?' : inc ? words.ask : 'Why are you rejecting this?'} maxLength={1000} />
          <button className="primary" disabled={busy || !reason.trim()}>{withdraw ? 'Withdraw' : inc ? words.submit : 'Reject'}</button> <button type="button" className="link" onClick={() => setRejecting(false)}>Cancel</button>
        </form>
      )}
      {note && <p role="alert" className="error small">{note}</p>}
      <p className="small"><button className="link" onClick={showRecord}>Decision record</button>{decNote && <span className="muted"> {decNote}</span>}</p>
      {dec && (
        <div className="small" role="region" aria-label="Decision record">
          <p>{dec.chainValid ? 'The Server says the hash chain verifies' : `The Server says the hash chain is BROKEN at entry ${dec.firstBadSeq}`}{dec.totalEntries != null ? ` (${dec.totalEntries} entries in the file)` : ''}.{' '}
            {dec.entriesVerified ? `Each of this run's ${dec.count} entries was recomputed here and matches its hash.` : 'An entry of this run does not match its hash: it was edited after it was written.'}</p>
          <ol>{dec.entries.map((e) => <li key={e.seq}>{new Date(e.ts).toLocaleTimeString()} {e.type.replace(/_/g, ' ')} by {e.actor || 'the system'}</li>)}</ol>
        </div>
      )}
    </article>
  )
}

/** "Waiting for me": the runs this user could approve right now (the Server decides; newest first). */
export function Queue({ me, onSignedOut, onCount }: { me: string; onSignedOut: () => void; onCount: (n: number) => void }) {
  const [runs, setRuns] = useState<Run[] | null>(null)
  const [handled, setHandled] = useState<Run[]>([])        // runs acted on in this view stay on screen, so the result of a click can be read, even though the Server no longer lists them for this user
  const [err, setErr] = useState('')
  const load = useCallback(async () => {
    try { const q = await api.workflowQueue(); setRuns(q.runs); onCount(q.count); setErr('') }
    catch (e) { if (e instanceof ApiError && e.status === 401) onSignedOut(); else setErr(e instanceof ApiError ? reasonText(e.code) || e.message : (e as Error).message) }
  }, [onSignedOut, onCount])
  useEffect(() => { load() }, [load])
  return (
    <section aria-label="Waiting for me">
      <h2>Waiting for me</h2>
      <p className="small"><button className="link" onClick={load}>Refresh</button></p>
      {err && <p role="alert" className="error">{err}</p>}
      {runs && runs.length === 0 && handled.length === 0 && !err && <p className="muted">Nothing is waiting for your approval. Runs you started yourself never appear here: someone else has to approve them.</p>}
      {runs?.filter((r) => !handled.some((h) => h.id === r.id)).map((r) => <RunCard key={r.id} initial={r} me={me} onSignedOut={onSignedOut} onChange={(run) => { setHandled((h) => [run, ...h.filter((x) => x.id !== run.id)]); load() }} />)}
      {handled.length > 0 && <><h3>Handled just now</h3>{handled.map((r) => <RunCard key={r.id} initial={r} me={me} onSignedOut={onSignedOut} onChange={(run) => setHandled((h) => h.map((x) => (x.id === run.id ? run : x)))} />)}</>}
    </section>
  )
}

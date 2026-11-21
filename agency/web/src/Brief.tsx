import { useCallback, useEffect, useRef, useState } from 'react'
import { api, ask, ApiError } from './api'
import { RunCard } from './Workflows'
import { INCIDENT, reasonText, type Definition, type Run } from './workflow'
import { BRIEF_PACK, BRIEF_QUESTIONS, GRADES, briefText, composeBrief, gradeLabel, headline, verdictLabel, type Answers, type BriefKey } from './rcaBrief'

const ORDER: BriefKey[] = ['causes', 'open', 'verdict', 'controls', 'speakers']

export const Grade = ({ g }: { g: string }) => <span className={`grade g-${g}`} title={GRADES[g]?.meaning}>{gradeLabel(g)}</span>

/** The one-page IT-risk root-cause brief (design note docs/agency-risk-it.md). It asks five approved questions as the signed-in person and composes the page; nothing is published or sent. */
const CLAIM = '1'     // the November claim (rca.claims): the run is keyed by it, so its id is rca-1

export default function Brief({ onSignedOut, me, canStart, defs }: { onSignedOut: () => void; me: string; canStart: boolean; defs: Definition[] }) {
  const [answers, setAnswers] = useState<Answers | null>(null)
  const [step, setStep] = useState<number | null>(null)
  const [err, setErr] = useState('')
  const [copied, setCopied] = useState(false)
  const abort = useRef<AbortController | null>(null)
  const [runState, setRunState] = useState<Run | null | undefined>(undefined)       // undefined = looking, null = none yet
  const [starting, setStarting] = useState(false)
  const [startErr, setStartErr] = useState('')
  const offered = defs.some((d) => d.id === INCIDENT)
  useEffect(() => {
    if (!offered) return
    let live = true
    api.workflowRun('rca-' + CLAIM).then((r) => live && setRunState(r.run)).catch((e) => { if (!live) return; if (e instanceof ApiError && e.status === 401) onSignedOut(); else setRunState(null) })
    return () => { live = false }
  }, [offered, onSignedOut])
  async function send() {
    setStarting(true); setStartErr('')
    try { setRunState((await api.startWorkflow(INCIDENT, CLAIM)).run) }
    catch (e) { if (e instanceof ApiError && e.status === 401) return onSignedOut(); setStartErr(e instanceof ApiError ? reasonText(e.code) || e.message : (e as Error).message) }
    finally { setStarting(false) }
  }

  const run = useCallback(async () => {
    setErr(''); setAnswers(null); setCopied(false); abort.current = new AbortController()
    const got: Answers = {}
    try {
      for (let i = 0; i < ORDER.length; i++) {
        setStep(i)
        // A new conversation for each question on purpose: the Server answers a follow-up in the same conversation from the previous rows without running a query (seen live), which would leave a hole in the brief.
        const a = await ask(BRIEF_QUESTIONS[ORDER[i]], BRIEF_PACK, null, () => {}, abort.current.signal)
        got[ORDER[i]] = { columns: a.columns ?? [], rows: a.rows ?? [] }
      }
      setAnswers(got)
    } catch (e) {
      if (e instanceof ApiError && e.status === 401) return onSignedOut()
      if (!(e instanceof DOMException && e.name === 'AbortError')) setErr(e instanceof Error ? e.message : 'The problem record could not be built.')
    } finally { setStep(null) }
  }, [onSignedOut])

  const b = answers ? composeBrief(answers) : null
  const copy = async () => { if (!b) return; try { await navigator.clipboard.writeText(briefText(b)); setCopied(true) } catch { setErr('Copy is blocked in this browser. Select the page text instead.') } }
  const novControls = b?.controls.filter((c) => c.caseId === 'nov-2026-cluster') ?? []

  return (
    <section className="brief" aria-label="Problem record">
      <header className="brief-head">
        <h1>IT risk: problem record (root cause)</h1>
        <p className="muted small">Scope: six outages, 12 to 17 November 2026 (Microsoft 365, FAA, JPMorgan Chase, United, NSANet, Apple). Claim tested: "The November outages are AI hacking."</p>
        <p className="muted small">The specification of the JPMC advisor, on the invented demo data. Causes are the specification's own, checked there against official statements on 19 November 2026; this system fetched nothing.</p>
        <div className="brief-actions">
          <button className="primary" onClick={run} disabled={step !== null}>{b ? 'Build it again' : 'Build the problem record'}</button>
          {step !== null && <button onClick={() => abort.current?.abort()}>Cancel</button>}
          {b && <><button onClick={copy}>{copied ? 'Copied' : 'Copy as text'}</button> <button onClick={() => window.print()}>Print</button></>}
        </div>
        {step !== null && <p role="status" aria-live="polite" className="muted small">Asking the approved questions as you: {step + 1} of {ORDER.length}…</p>}
        {err && <p role="alert" className="error">{err}</p>}
      </header>

      {b && !b.complete && <p className="warn">Not every approved question answered, so the problem record cannot be shown. Check that the IT-risk case data is loaded (the demos/it-risk-rca seed) and try again.</p>}

      {b?.complete && <>
        <h2 className="brief-headline">{headline(b)}</h2>
        {b.claim && <div className="verdict"><strong>Verdict on the claim: {verdictLabel(b.claim.verdict)}.</strong> {b.claim.sentence}</div>}

        <h2>Incidents and their causes</h2>
        <div className="tablewrap"><table>
          <thead><tr><th>Incident</th><th>Cause</th><th>Grade</th><th className="num">Sources</th></tr></thead>
          <tbody>{b.incidents.map((i) => <tr key={i.operator}><td>{i.operator}</td><td className="wrap">{i.cause}</td><td><Grade g={i.grade} />{i.supported && <div className="small muted" role="note">Sources support only: <Grade g={i.supported} /></div>}</td><td className="num">{i.sources}</td></tr>)}</tbody>
        </table></div>

        <h2>Not established</h2>
        <ul className="plain">
          {b.counts.openIncidents.map((i) => <li key={i.operator}><Grade g={i.grade} /> <strong>{i.operator}.</strong> {i.cause}</li>)}
          {b.open.map((o) => <li key={o.statement}><Grade g={o.grade} /> {o.statement} <span className="muted">{o.reason}</span></li>)}
        </ul>

        <h2>Control to fix</h2>
        {novControls.length === 0 ? <p className="muted">No control is mapped yet.</p> : <ul className="plain">
          {novControls.map((c) => <li key={c.condition}><strong>{c.control}</strong>, owned by {c.owner}. {c.framework}, {c.category}. Root condition: {c.condition.toLowerCase()} <Grade g={c.grade} /> <span className="muted">The firm's own change and test records are not loaded, so this is a hypothesis.</span></li>)}
        </ul>}

        <h2>Rules checked</h2>
        <ul className="plain checks">{b.checks.map((c) => <li key={c.rule} className={c.ok ? 'ok' : 'bad'}><span aria-hidden>{c.ok ? '✓' : '!'}</span> <strong>{c.rule}.</strong> {c.detail}</li>)}</ul>

        <h2>Decision</h2>
        {!offered && <p className="muted small">The incident workflow is not available on this Server (it needs the commercial edition and a workflow engine), so this page can be read but not sent for approval.</p>}
        {offered && runState === undefined && <p className="muted small" role="status">Looking for a decision on this problem record…</p>}
        {offered && runState === null && <>
          <p className="small">A named approver, not you, publishes this problem record or puts it on hold. The run re-reads the causes and sources, checks the rules, and recommends one of the two; the approval is bound to the exact problem record. Publishing is a dry run: nothing is sent anywhere.</p>
          <div className="brief-actions"><button className="primary" onClick={send} disabled={starting || !canStart}>{starting ? 'Sending…' : 'Send for approval'}</button>{!canStart && <span className="muted small" role="note">Your account cannot start workflows.</span>}</div>
          {startErr && <p role="alert" className="error small">{startErr}</p>}
        </>}
        {offered && runState && <>
          <p className="small muted" role="note">This problem record was already sent for approval{runState.initiator ? ` by ${runState.initiator}` : ''}. The run re-reads the sources and applies the same grading as the table above; its card is below.</p>
          <RunCard initial={runState} me={me} onSignedOut={onSignedOut} />
        </>}
      </>}
    </section>
  )
}

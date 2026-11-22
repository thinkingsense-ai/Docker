import { useCallback, useRef, useState } from 'react'
import { api, ask, ApiError } from './api'
import { RunCard } from './Workflows'
import { ASSESSMENT, reasonText, type Definition, type Run } from './workflow'
import { BRIEF_PACK, type Table } from './rcaBrief'
import { RULES, THRESHOLDS, TRIGGERS, PRIORITY_QUESTION, prioritiesText, prioritise } from './priorityModel'
import { ratingRank, type Rating } from './rating'

const Meter = ({ n }: { n: number }) => <span className="meter" aria-hidden="true">{[0, 1, 2, 3].map((i) => <i key={i} className={i < n ? 'on' : ''} />)}</span>

/** Priorities: which systems to fix first. One approved question over the simulated estate, asked as the signed-in person, ranked by the stated rules in priorityModel.ts. Nothing is written or sent. */
export default function Priorities({ me, canStart, defs, answer, exposureLevel, onAnswer, onSignedOut }: { me: string; canStart: boolean; defs: Definition[]; answer: Table | null; exposureLevel: Rating | null; onAnswer: (t: Table) => void; onSignedOut: () => void }) {
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  const [copied, setCopied] = useState(false)
  const abort = useRef<AbortController | null>(null)
  const [runs, setRuns] = useState<Record<string, Run>>({})
  const [sending, setSending] = useState<string | null>(null)
  const [sendErr, setSendErr] = useState<Record<string, string>>({})
  const offered = defs.some((d) => d.id === ASSESSMENT)
  async function assess(id: string) {
    setSending(id); setSendErr((e) => ({ ...e, [id]: '' }))
    try { const r = await api.startWorkflow(ASSESSMENT, id); setRuns((x) => ({ ...x, [id]: r.run })) }
    catch (e) { if (e instanceof ApiError && e.status === 401) return onSignedOut(); setSendErr((x) => ({ ...x, [id]: e instanceof ApiError ? reasonText(e.code) || e.message : (e as Error).message })) }
    finally { setSending(null) }
  }

  const run = useCallback(async () => {
    setErr(''); setCopied(false); setBusy(true); abort.current = new AbortController()
    try {
      const a = await ask(PRIORITY_QUESTION, BRIEF_PACK, null, () => {}, abort.current.signal)
      onAnswer({ columns: a.columns ?? [], rows: a.rows ?? [] })
    } catch (e) {
      if (e instanceof ApiError && e.status === 401) return onSignedOut()
      if (!(e instanceof DOMException && e.name === 'AbortError')) setErr(e instanceof Error ? e.message : 'The list could not be built.')
    } finally { setBusy(false) }
  }, [onAnswer, onSignedOut])

  const p = answer ? prioritise(answer, { exposureLevel }) : null
  const copy = async () => { if (!p) return; try { await navigator.clipboard.writeText(prioritiesText(p)); setCopied(true) } catch { setErr('Copy is blocked in this browser. Select the page text instead.') } }

  return (
    <section className="priorities" aria-label="Priorities">
      <header className="brief-head">
        <h2>Priorities: which systems to fix first</h2>
        <p className="notbuilt" role="note"><strong>Simulated estate.</strong> Invented data for an invented firm. This is a method, not a standard: likelihood and impact are added on one four-value scale, and a trigger can lift a system to High.</p>
        <p className="muted">One approved question is asked as you; each system is ranked by the stated rules, and every row says why. Business impact is not scored: it needs the firm&apos;s own business services.</p>
        <div className="brief-actions">
          <button className="primary" onClick={run} disabled={busy}>{busy ? 'Asking…' : p ? 'Rank again' : 'Rank the systems'}</button>
          {busy && <button onClick={() => abort.current?.abort()}>Cancel</button>}
          {p?.ok && <><button onClick={copy}>{copied ? 'Copied' : 'Copy as text'}</button><button onClick={() => window.print()}>Print</button></>}
        </div>
        {err && <p role="alert" className="error">{err}</p>}
      </header>
      {!p && !busy && <p className="muted">{PRIORITY_QUESTION}</p>}
      {p && !p.ok && <p role="alert" className="error">{p.sentence}</p>}
      {p?.ok && (
        <>
          <p role="status"><strong>{p.sentence}</strong>{exposureLevel === 'Critical' ? ' The exposure rating is Critical, so systems running the affected technology are at least High.' : ' Run Exposure first to include its trigger.'}</p>
          <ol className="qcards prio">
            {p.rows.map((r, i) => {
              const k = ratingRank(r.rating) ?? 0
              return (
                <li key={r.system} className="qcard">
                  <h3><span className="muted">{i + 1}.</span> {r.system}</h3>
                  <p className={'prio-rating l' + k}><Meter n={k + 1} /> <strong>{r.rating}</strong> <span className="muted small">likelihood {r.likelihood}, impact {r.impact}{r.lifted ? ', lifted by a trigger' : ''}</span></p>
                  <p>{r.reason}</p>
                  {r.lossEvent && <p className="muted small">If it fails: {r.lossEvent}</p>}
                  {r.notes.map((n) => <p key={n} className="muted small">{n}</p>)}
                  <p className="muted small">Business impact: not scored.</p>
                  <p className="small">{r.registered ? <>In the risk register: <strong>{r.registered.rating}</strong>, set by {r.registered.by}{r.registered.at ? ` on ${r.registered.at.slice(0, 10)}` : ''}.</> : 'Not in the risk register yet.'}</p>
                  {offered && r.systemId && !runs[r.systemId] && (
                    <p className="brief-actions"><button onClick={() => assess(r.systemId!)} disabled={!canStart || sending === r.systemId}>{sending === r.systemId ? 'Sending…' : 'Send for assessment'}</button>
                      {!canStart && <span className="muted small" role="note">Your account cannot start workflows. A first-line person proposes; a second-line person records it.</span>}</p>)}
                  {r.systemId && sendErr[r.systemId] && <p role="alert" className="error small">{sendErr[r.systemId]}</p>}
                  {r.systemId && runs[r.systemId] && <RunCard initial={runs[r.systemId]} me={me} onSignedOut={onSignedOut} />}
                </li>
              )
            })}
          </ol>
          <details><summary>Rules and thresholds (demo constants)</summary>
            <ul className="plain small">
              <li><strong>Likelihood:</strong> {RULES.likelihood}</li>
              <li><strong>Impact:</strong> {RULES.impact}</li>
              <li><strong>Rating:</strong> {RULES.rating}</li>
              <li><strong>Order:</strong> {RULES.order}</li>
              <li><strong>Triggers:</strong> {Object.values(TRIGGERS).join(' ')}</li>
              <li>Exploit-score bands {THRESHOLDS.midEpss} and {THRESHOLDS.highEpss}, support {THRESHOLDS.supportDays} days and recovery {THRESHOLDS.recoveryDays} days are demo constants to agree with the head of technology risk.</li>
            </ul>
          </details>
        </>
      )}
    </section>
  )
}

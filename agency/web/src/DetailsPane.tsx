import { useEffect, useState } from 'react'
import type { Answer } from './api'
import { checkLabel, checkState, fmtMs, summarize, type ProgressEvent } from './progress'
import { scopeLine } from './format'

interface RunProps { events: ProgressEvent[]; startedAt: number; onCancel: () => void }

/** While a question runs: six plain stages, what each found, and a clock. */
export function ProgressView({ events, startedAt, onCancel }: RunProps) {
  const [now, setNow] = useState(Date.now())
  useEffect(() => { const t = setInterval(() => setNow(Date.now()), 500); return () => clearInterval(t) }, [])
  const p = summarize(events, now, startedAt)
  const current = p.stages.find((s) => s.state === 'now')
  return (
    <div>
      <h2>Answering your question</h2>
      <p className="muted small" role="status" aria-live="polite">{current ? `${current.label}…` : 'Almost there…'}</p>
      <ol className="stages-list">
        {p.stages.map((s) => (
          <li key={s.id} className={s.state} aria-current={s.state === 'now' ? 'step' : undefined}>
            <span className="mark" aria-hidden="true">{s.state === 'done' ? '✓' : s.state === 'now' ? '●' : '○'}</span>
            <span className="what"><span>{s.label}</span>{s.detail && s.state !== 'next' && <span className="muted small">{s.detail}</span>}</span>
            <span className="muted small time">{s.ms !== undefined && s.state !== 'next' ? fmtMs(s.ms) : ''}</span>
            <span className="sr">{s.state === 'done' ? 'done' : s.state === 'now' ? 'in progress' : 'waiting'}</span>
          </li>))}
      </ol>
      <p className="small"><strong>{fmtMs(p.totalMs)}</strong> so far <button onClick={onCancel}>Cancel</button></p>
    </div>
  )
}

interface AnswerProps { a: Answer | null; question: string; historic?: boolean }

/** After an answer: where it came from, what data it used, the checks it passed, and the SQL on request. */
export function AnswerDetails({ a, question, historic }: AnswerProps) {
  if (!a) return <p className="muted">Ask a question and how it was answered appears here.</p>
  const e = a.evidence
  const origin = e?.origin === 'question_bank' ? 'An approved question' : e?.origin === 'generated' ? 'Written for this question' : e?.origin === 'typed' ? 'SQL you typed' : null
  return (
    <div>
      <h2>How this was answered</h2>
      <p className="small muted pane-q">{question}</p>
      {!e ? <p className="muted">{historic ? 'Details are only kept for answers asked now, not for a conversation you reopened.' : 'The Server sent no details for this answer.'}</p> : (
        <>
          <dl className="facts">
            {origin && <><dt>Came from</dt><dd>{origin}{e.answeredWithoutDataSources ? ' (no data source used)' : ''}</dd></>}
            <dt>Time</dt><dd>{fmtMs(e.elapsedMs)}</dd>
            <dt>Domain</dt><dd>{e.pack && e.pack !== e.workspace ? `${e.pack} (workspace ${e.workspace})` : e.workspace}</dd>
            <dt>Data used</dt><dd>{e.sources.length ? e.sources.map((s) => s.id).join(', ') : 'none reported'}</dd>
            {e.model && <><dt>Model</dt><dd>{e.model}</dd></>}
          </dl>
          <p className="small muted">{scopeLine(e.scopeEnforcedBy)}</p>
          {e.checks.length > 0 && (
            <>
              <h3>Checks</h3>
              <ul className="checks">{e.checks.map((c) => { const s = checkState(c.status); return <li key={c.id}><span aria-hidden="true">{s.ok === true ? '✓' : s.ok === null ? '–' : '!'}</span> {checkLabel(c.id)} <span className="muted small">{s.text}</span></li> })}</ul>
            </>)}
          {e.warnings.length > 0 && <ul className="warnings">{e.warnings.map((w, i) => <li key={i}>{w.replace(/\s*\(Server#\d+\)/g, '')}</li>)}</ul>}
          {e.sql && <details><summary>The query</summary><pre>{e.sql}</pre></details>}
        </>)}
    </div>
  )
}

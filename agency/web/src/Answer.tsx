import { useState } from 'react'
import type { Answer as A } from './api'
import { api, ApiError } from './api'
import { declineExample, emptyNote, formatCell, isNumeric } from './format'
import { RunCard } from './Workflows'
import ResultView from './ResultView'
import Feedback from './Feedback'
import { reasonText, startable, type Definition, type Run } from './workflow'

export interface WorkflowCtx { defs: Definition[]; canStart: boolean; me: string; onSignedOut: () => void; onChange: () => void }
type Start = { column: number; def: Definition }

export function Table({ columns, rows, starts = [], onStart }: { columns: string[]; rows: (string | null)[][]; starts?: Start[]; onStart?: (def: Definition, key: string) => void }) {
  if (!columns.length) return null
  const numeric = columns.map((_, j) => rows.length > 0 && rows.every((r) => r[j] === null || isNumeric(r[j])))
  return (
    <div className="tablewrap" tabIndex={0} role="region" aria-label="Result table">
      <table>
        <thead><tr>{columns.map((c, i) => <th key={i} scope="col" className={numeric[i] ? 'num' : ''}>{c}</th>)}{starts.length > 0 && <th scope="col">Workflow</th>}</tr></thead>
        <tbody>{rows.map((r, i) => <tr key={i}>{r.map((v, j) => <td key={j} className={numeric[j] ? 'num' : ''}>{formatCell(v)}</td>)}
          {starts.length > 0 && <td>{starts.map((s) => r[s.column] != null && r[s.column] !== '' && <button key={s.def.id} className="chip" onClick={() => onStart?.(s.def, String(r[s.column]))} aria-label={`Start ${s.def.title} for ${r[s.column]}`}>Start {s.def.title.toLowerCase()}</button>)}</td>}</tr>)}</tbody>
      </table>
      <p className="muted small">{rows.length} row{rows.length === 1 ? '' : 's'}</p>
    </div>
  )
}

export default function Answer({ a, question, onFollow, wf, onDetails, active }: { a: A; question: string; onFollow: (q: string) => void; wf?: WorkflowCtx; onDetails?: () => void; active?: boolean }) {
  const [runs, setRuns] = useState<Run[]>([])
  const [wfNote, setWfNote] = useState('')
  const starts = wf?.canStart ? startable(a.columns, wf.defs) : []
  async function start(def: Definition, key: string) {
    setWfNote('')
    try {
      const r = await api.startWorkflow(def.id, key)
      setRuns((x) => (x.some((y) => y.id === r.run.id) ? x : [...x, r.run]))
      if (!r.created) setWfNote(`A ${def.title.toLowerCase()} run for ${key} already exists (started by ${r.run.initiator}); showing it.`)
      wf?.onChange()
    } catch (e) { if (e instanceof ApiError && e.status === 401) wf?.onSignedOut(); else setWfNote(e instanceof ApiError ? reasonText(e.code) || e.message : (e as Error).message) }
  }
  return (
    <article className="answer" aria-label="Answer">
      <h2 className="q">{question}</h2>
      {a.answer && <p className="text">{a.answer}</p>}
      {a.answer && declineExample(a.answer) && <p className="small"><button className="chip" onClick={() => onFollow(declineExample(a.answer)!)}>{declineExample(a.answer)}</button></p>}
      {emptyNote(a.columns, a.rows, a.answer)
        ? <p className="empty" role="status">{emptyNote(a.columns, a.rows, a.answer)}</p>
        : <ResultView question={question} columns={a.columns} rows={a.rows} starts={starts} onStart={start} />}
      {wfNote && <p role="status" className="muted small">{wfNote}</p>}
      {wf && runs.map((r) => <RunCard key={r.id} initial={r} me={wf.me} onSignedOut={wf.onSignedOut} onChange={wf.onChange} />)}
      {a.truncated && <p className="warn">The result was cut at the Server's row limit.</p>}
      {a.suggestedQuestions && a.suggestedQuestions.length > 0 && (
        <div className="follow"><span className="muted small">Follow up:</span>{a.suggestedQuestions.map((q) => <button key={q} className="chip" onClick={() => onFollow(q)}>{q}</button>)}</div>
      )}
      <Feedback a={a} question={question} onSignedOut={wf?.onSignedOut} />
      {onDetails && (
        <p className="small prov">
          <span className="muted">{a.evidence ? `${a.evidence.origin === 'question_bank' ? 'Approved question' : a.evidence.origin === 'generated' ? 'Written for this question' : 'Answered'} · ${a.evidence.elapsedMs < 950 ? '<1' : (a.evidence.elapsedMs / 1000).toFixed(a.evidence.elapsedMs < 10000 ? 1 : 0)} s` : 'Answered'}</span>{' '}
          <button className="link" aria-pressed={active} onClick={onDetails}>How this was answered</button>
        </p>)}
    </article>
  )
}

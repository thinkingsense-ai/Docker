import { useState } from 'react'
import type { Answer as A, Evidence } from './api'
import { api, ApiError } from './api'
import { formatCell, isNumeric, scopeLine } from './format'
import { RunCard } from './Workflows'
import ResultView from './ResultView'
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

export function EvidencePane({ e }: { e: Evidence }) {
  const [open, setOpen] = useState(true)
  const origin = e.origin === 'question_bank' ? 'Approved question' : e.origin === 'generated' ? 'Generated SQL' : e.origin === 'typed' ? 'Typed SQL' : e.origin ?? 'Not reported'
  return (
    <aside className="evidence" aria-label="Evidence">
      <button className="link" aria-expanded={open} onClick={() => setOpen(!open)}>{open ? 'Hide evidence' : 'Show evidence'}</button>
      {open && (
        <dl>
          <dt>Workspace</dt><dd>{e.workspace}{e.pack ? ` (pack ${e.pack})` : ''}</dd>
          <dt>Scope</dt><dd>{scopeLine(e.scopeEnforcedBy)}</dd>
          <dt>Answered from</dt><dd>{origin}{e.answeredWithoutDataSources ? ' (no data source used)' : ''}</dd>
          <dt>Sources</dt><dd>{e.sources.length ? e.sources.map((s) => s.id).join(', ') : 'none reported'}</dd>
          {e.intendedSources && <><dt>Pack intends</dt><dd>{e.intendedSources.map((s) => `${s.id}: ${s.schemas.join(', ')}`).join(' · ')}</dd></>}
          {e.model && <><dt>Model</dt><dd>{e.model}</dd></>}
          <dt>Checks</dt><dd>{e.checks.length ? e.checks.map((c) => `${c.id}: ${c.status}`).join(' · ') : 'none reported'}</dd>
          <dt>Time</dt><dd>{(e.elapsedMs / 1000).toFixed(1)} s</dd>
          {e.sql && <><dt>SQL</dt><dd><pre>{e.sql}</pre></dd></>}
        </dl>
      )}
      {open && e.warnings.length > 0 && <ul className="warnings">{e.warnings.map((w, i) => <li key={i}>{w}</li>)}</ul>}
    </aside>
  )
}

export default function Answer({ a, question, onFollow, wf }: { a: A; question: string; onFollow: (q: string) => void; wf?: WorkflowCtx }) {
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
      <ResultView question={question} columns={a.columns} rows={a.rows} starts={starts} onStart={start} />
      {wfNote && <p role="status" className="muted small">{wfNote}</p>}
      {wf && runs.map((r) => <RunCard key={r.id} initial={r} me={wf.me} onSignedOut={wf.onSignedOut} onChange={wf.onChange} />)}
      {a.truncated && <p className="warn">The result was cut at the Server's row limit.</p>}
      {a.suggestedQuestions && a.suggestedQuestions.length > 0 && (
        <div className="follow"><span className="muted small">Follow up:</span>{a.suggestedQuestions.map((q) => <button key={q} className="chip" onClick={() => onFollow(q)}>{q}</button>)}</div>
      )}
      {a.evidence && <EvidencePane e={a.evidence} />}
    </article>
  )
}

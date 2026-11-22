import { useCallback, useRef, useState } from 'react'
import { ask, ApiError } from './api'
import { BRIEF_PACK, type Table } from './rcaBrief'
import { LEVELS, QUESTIONS, RULES, THRESHOLDS, exposureText, rate, type Key, type QScore } from './exposureModel'

export type ExposureAnswers = Partial<Record<Key, Table>>

const Meter = ({ n }: { n: number }) => <span className="meter" aria-hidden="true">{[0, 1, 2, 3].map((i) => <i key={i} className={i < n ? 'on' : ''} />)}</span>

function Card({ s }: { s: QScore }) {
  return (
    <li className="qcard">
      <h3>{s.n}. {s.short}</h3>
      <p className="muted small">{s.question}</p>
      <p><span className={'score ' + (s.score === null ? 'su' : 's' + s.score)}>{s.score === null ? 'Unknown' : `${s.label} (${s.score} of 3)`}</span> {s.reason}</p>
      {s.rows.rows.length > 0 && (
        <details><summary>Rows behind this score ({s.rows.rows.length})</summary>
          <div className="tablewrap"><table><thead><tr>{s.rows.columns.map((c) => <th key={c}>{c}</th>)}</tr></thead>
            <tbody>{s.rows.rows.map((r, i) => <tr key={i}>{r.map((v, j) => <td key={j}>{v ?? ''}</td>)}</tr>)}</tbody></table></div>
        </details>)}
      <details><summary>The rule</summary><p className="small">{s.rule}</p></details>
    </li>
  )
}

/** Exposure: could a similar incident reach our own systems. Five approved questions over the simulated estate, asked as the signed-in person, rated by the rules in exposure.ts. Nothing is published or sent. */
export default function Exposure({ answers, onAnswers, onSignedOut }: { answers: ExposureAnswers | null; onAnswers: (a: ExposureAnswers) => void; onSignedOut: () => void }) {
  const [step, setStep] = useState<number | null>(null)
  const [err, setErr] = useState('')
  const [copied, setCopied] = useState(false)
  const abort = useRef<AbortController | null>(null)

  const run = useCallback(async () => {
    setErr(''); setCopied(false); abort.current = new AbortController()
    const got: ExposureAnswers = {}
    try {
      for (let i = 0; i < QUESTIONS.length; i++) {
        setStep(i)
        // A new conversation for each question on purpose, as the brief does: a follow-up can be answered from the previous rows without a query.
        const a = await ask(QUESTIONS[i].text, BRIEF_PACK, null, () => {}, abort.current.signal)
        got[QUESTIONS[i].key] = { columns: a.columns ?? [], rows: a.rows ?? [] }
      }
      onAnswers(got)
    } catch (e) {
      if (e instanceof ApiError && e.status === 401) return onSignedOut()
      if (!(e instanceof DOMException && e.name === 'AbortError')) setErr(e instanceof Error ? e.message : 'The exposure could not be rated.')
    } finally { setStep(null) }
  }, [onAnswers, onSignedOut])

  const r = answers ? rate(answers) : null
  const tech = answers?.systems ? [...new Set(answers.systems.rows.map((x) => x[answers.systems!.columns.indexOf('technology')]).filter(Boolean))] : []
  const copy = async () => { if (!r) return; try { await navigator.clipboard.writeText(exposureText(r)); setCopied(true) } catch { setErr('Copy is blocked in this browser. Select the page text instead.') } }

  return (
    <section className="exposure" aria-label="Exposure">
      <header className="brief-head">
        <h2>Exposure to a similar incident</h2>
        <p className="notbuilt" role="note"><strong>Simulated estate.</strong> Invented data for an invented firm: no real database, SharePoint, Slack or object store was read.</p>
        <p className="muted">Case: the November 2026 incident cluster (see Problem records). Five approved questions are asked as you, and each is scored by a stated rule. The overall rating is the highest score, never an average.</p>
        <div className="brief-actions">
          <button className="primary" data-tour="exposure-run" onClick={run} disabled={step !== null}>{step !== null ? `Question ${step + 1} of 5: ${QUESTIONS[step].short}…` : r ? 'Rate it again' : 'Rate the exposure'}</button>
          {step !== null && <button onClick={() => abort.current?.abort()}>Cancel</button>}
          {r && <><button data-tour="exposure-done" onClick={copy}>{copied ? 'Copied' : 'Copy as text'}</button><button onClick={() => window.print()}>Print</button></>}
        </div>
        {err && <p role="alert" className="error">{err}</p>}
      </header>
      {!r && step === null && <ol className="plain muted">{QUESTIONS.map((q) => <li key={q.key}>{q.text}</li>)}</ol>}
      {r && (
        <>
          <div className={'rating ' + (r.level ? 'l' + r.score : 'lu')} role="status">
            <Meter n={r.score === null ? 0 : r.score + 1} />
            <div><strong className="level">{r.level ? `${r.complete ? '' : 'At least '}${r.level}` : 'No rating'}</strong><br /><span>{r.sentence}</span></div>
          </div>
          {tech.length > 0 && <p className="small">Affected technology here: {tech.join(', ')}.</p>}
          <ol className="qcards">{r.scores.map((s) => <Card key={s.key} s={s} />)}</ol>
          <details><summary>Rules and thresholds (demo constants)</summary>
            <p className="small">Patch overdue: more than {THRESHOLDS.patchDays} days. Recovery test: older than {THRESHOLDS.recoveryDays} days. Wide: {THRESHOLDS.widePeople} or more people. Levels: {LEVELS.join(', ')}, from the highest of the five scores (0 Low, 1 Medium, 2 High, 3 Critical). A question that cannot be scored is Unknown, never 0. In a real deployment the head of technology risk owns these numbers.</p>
            <ul className="plain small">{QUESTIONS.map((q) => <li key={q.key}><strong>{q.n}. {q.short}:</strong> {RULES[q.key]}</li>)}</ul>
          </details>
        </>
      )}
    </section>
  )
}

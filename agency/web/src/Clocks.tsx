import { useCallback, useMemo, useRef, useState } from 'react'
import { api, ask, ApiError } from './api'
import { BRIEF_PACK, records, type Table } from './rcaBrief'
import { CLOCKS_QUESTIONS, computeClocks, leftText, type ClockRule } from './clockModel'
import { RunCard } from './Workflows'
import { MAJOR, reasonText, type Definition, type Run } from './workflow'

export interface ClockAnswers { incidents: Table; rules: Table }

/** Notifications: what a regulator asks for after a MAJOR incident, and when. The clocks exist only once a person has recorded that an incident is major (a second-line approval); no rule decides it,
 *  nothing is sent to any regulator, and "material" (bad press) is not decided here. Two approved questions are asked as the signed-in person; the deadlines are computed by clockModel.ts. */
export default function Clocks({ me, canStart, defs, answers, onAnswers, onSignedOut }: { me: string; canStart: boolean; defs: Definition[]; answers: ClockAnswers | null; onAnswers: (a: ClockAnswers) => void; onSignedOut: () => void }) {
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  const abort = useRef<AbortController | null>(null)
  const [runs, setRuns] = useState<Record<string, Run>>({})
  const [sending, setSending] = useState<string | null>(null)
  const [sendErr, setSendErr] = useState<Record<string, string>>({})
  const offered = defs.some((d) => d.id === MAJOR)

  const load = useCallback(async () => {
    setErr(''); setBusy(true); abort.current = new AbortController()
    try {
      const got: Partial<ClockAnswers> = {}
      for (const k of ['incidents', 'rules'] as const) {
        // A new conversation for each question on purpose, as the other screens do.
        const a = await ask(CLOCKS_QUESTIONS[k], BRIEF_PACK, null, () => {}, abort.current.signal)
        got[k] = { columns: a.columns ?? [], rows: a.rows ?? [] }
      }
      onAnswers(got as ClockAnswers)
    } catch (e) {
      if (e instanceof ApiError && e.status === 401) return onSignedOut()
      if (!(e instanceof DOMException && e.name === 'AbortError')) setErr(e instanceof Error ? e.message : 'The incidents could not be loaded.')
    } finally { setBusy(false) }
  }, [onAnswers, onSignedOut])

  async function record(id: string) {
    setSending(id); setSendErr((e) => ({ ...e, [id]: '' }))
    try { const r = await api.startWorkflow(MAJOR, id); setRuns((x) => ({ ...x, [id]: r.run })) }
    catch (e) { if (e instanceof ApiError && e.status === 401) return onSignedOut(); setSendErr((x) => ({ ...x, [id]: e instanceof ApiError ? reasonText(e.code) || e.message : (e as Error).message })) }
    finally { setSending(null) }
  }

  const incidents = useMemo(() => records(answers?.incidents), [answers])
  const rules = useMemo(() => records(answers?.rules) as unknown as (ClockRule & { declared: string })[], [answers])
  const declared = useMemo(() => [...new Set(rules.filter((r) => ['true', 't', '1'].includes(String(r.declared).toLowerCase())).map((r) => r.regulator))], [rules])
  const now = Date.now()

  return (
    <section className="clocks" aria-label="Notifications">
      <header className="brief-head">
        <h2>Notification clocks after a major incident</h2>
        <p className="notbuilt" role="note"><strong>Simulated firm. Nothing is sent to any regulator.</strong> The incidents are invented. The rules are our reading of public summaries, checked in secondary sources on 2026-11-21: read the regulation before relying on them.</p>
        <p className="muted">Whether an incident is major is a person&apos;s decision, recorded here by a second-line approval; no rule makes it, and whether it is material (bad press) is not decided at all. The clocks start only after that decision.</p>
        <div className="brief-actions">
          <button className="primary" onClick={load} disabled={busy}>{busy ? 'Loading…' : answers ? 'Refresh' : 'Load the incidents'}</button>
          {busy && <button onClick={() => abort.current?.abort()}>Cancel</button>}
        </div>
        {err && <p role="alert" className="error">{err}</p>}
      </header>
      {answers && declared.length > 0 && <p className="small">Regulators this firm declared: {declared.join(', ')}. A person declares applicability; the product does not work it out.</p>}
      {answers && (
        <ol className="qcards">
          {incidents.map((inc) => {
            const decided = !!inc.classified_at
            const cl = decided ? computeClocks(rules, declared, { awareness_at: inc.awareness_at, classified_at: inc.classified_at }, now) : null
            return (
              <li key={inc.incident_id} className="qcard">
                <h3>{inc.title}</h3>
                <p className="muted small">{inc.summary} The firm became aware {inc.awareness_at.replace(/\.\d+$/, '')} UTC.</p>
                {decided ? <p><span className="score s3">Recorded as major</span> by {inc.set_by} at {inc.classified_at.replace(/\.\d+$/, '')} UTC for {inc.regimes}.</p> : <p><span className="score su">No decision recorded</span> No clock is running.</p>}
                {cl && cl.state === 'clocks' && (
                  <div className="tablewrap"><table><thead><tr><th>Regulator</th><th>Stage</th><th>Due (UTC)</th><th>Now</th><th>Why</th></tr></thead>
                    <tbody>{cl.clocks.map((c) => (
                      <tr key={c.rule_id}><td>{c.regulator}</td><td>{c.title}</td><td>{c.due_at?.replace('T', ' ').replace('Z', '') ?? 'none'}</td>
                        <td><span className={'score ' + (c.state === 'overdue' ? 's3' : 's1')}>{leftText(c.seconds_left)}</span></td>
                        <td className="small">{c.basis}{c.flags.length > 0 && <><br /><em>{c.flags.join('; ')}.</em></>}</td></tr>))}</tbody></table></div>)}
                {cl && cl.state !== 'clocks' && <p className="muted small">{cl.state === 'no_regulator' ? 'No regulator is declared, so there is no clock.' : 'The decision has no readable time, so no clock is shown.'}</p>}
                {!decided && offered && !runs[inc.incident_id] && (
                  <p className="brief-actions"><button onClick={() => record(inc.incident_id)} disabled={!canStart || sending === inc.incident_id}>{sending === inc.incident_id ? 'Sending…' : 'Send for a major-incident decision'}</button>
                    {!canStart && <span className="muted small" role="note">Your account cannot start workflows. A first-line person proposes; a second-line person decides.</span>}</p>)}
                {sendErr[inc.incident_id] && <p role="alert" className="error small">{sendErr[inc.incident_id]}</p>}
                {runs[inc.incident_id] && <RunCard initial={runs[inc.incident_id]} me={me} onSignedOut={onSignedOut} />}
              </li>)
          })}
        </ol>)}
      {answers && (
        <details><summary>The rules and where they come from ({rules.length})</summary>
          <div className="tablewrap"><table><thead><tr><th>Regulator</th><th>Stage</th><th>Hours</th><th>Counted from</th><th>Also</th><th>Source</th><th>Checked</th><th>Note</th></tr></thead>
            <tbody>{rules.map((r) => <tr key={r.rule_id}><td>{r.regulator}</td><td>{r.title}</td><td>{r.hours}</td><td>{r.starts_from.replace('_', ' ')}</td><td>{r.also_within_hours_of_awareness ? `no later than ${r.also_within_hours_of_awareness} h after awareness` : ''}</td>
              <td className="small">{String((r as unknown as Record<string, string>).source)}</td><td className="small">{String((r as unknown as Record<string, string>).checked)}</td><td className="small">{String((r as unknown as Record<string, string>).note ?? '')}</td></tr>)}</tbody></table></div>
        </details>)}
    </section>
  )
}

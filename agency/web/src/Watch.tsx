import { useEffect, useRef, useState } from 'react'
import { ask, ApiError } from './api'
import { BRIEF_PACK, type Table } from './rcaBrief'
import { CLAIM_TYPES, WATCH_QUESTION, actionFor, claimLabel, composeWatch, statusText } from './watchModel'
import { verdictLabel } from './rcaBrief'

/** Watch: the incident stories being followed. The list is one approved question asked as the signed-in person; nothing is traced or published without a button press. */
export default function Watch({ table, onLoaded, onBrief, onAsk, onSignedOut }: {
  table: Table | null; onLoaded: (t: Table) => void; onBrief: () => void; onAsk: (q: string) => void; onSignedOut: () => void
}) {
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  const abort = useRef<AbortController | null>(null)

  async function load() {
    setBusy(true); setErr(''); abort.current = new AbortController()
    try { const a = await ask(WATCH_QUESTION, BRIEF_PACK, null, () => {}, abort.current.signal); onLoaded({ columns: a.columns ?? [], rows: a.rows ?? [] }) }
    catch (e) {
      if (e instanceof ApiError && e.status === 401) return onSignedOut()
      if (!(e instanceof DOMException && e.name === 'AbortError')) setErr(e instanceof Error ? e.message : 'The list could not be loaded.')
    } finally { setBusy(false) }
  }
  useEffect(() => { if (table === null) void load(); return () => abort.current?.abort() }, [])   // eslint-disable-line react-hooks/exhaustive-deps

  const list = table ? composeWatch(table) : []
  return (
    <section className="watch" aria-labelledby="watch-h">
      <header className="watch-head">
        <h2 id="watch-h">Watch</h2>
        <button onClick={load} disabled={busy}>{busy ? 'Loading…' : 'Refresh'}</button>
      </header>
      <p className="muted small">Incident stories being followed. Nothing is traced or published without a person pressing a button. The live feed is not connected yet: these are the two seeded cases, both already traced.</p>
      {err && <p role="alert" className="error">{err}</p>}
      {busy && !table && <p role="status" className="muted">Loading candidates…</p>}
      {table && list.length === 0 && <p className="empty">The Server returned no candidates. This stack may not carry the incident data.</p>}
      <ul className="candidates">
        {list.map((c) => {
          const act = actionFor(c)
          return (
            <li key={c.id} className="candidate">
              <h3>{c.title}</h3>
              <p className="cmeta">
                <span className="grade" title={CLAIM_TYPES[c.claimType]?.meaning}>{claimLabel(c.claimType)}</span>
                <span className={'status ' + c.status}>{statusText(c)}</span>
                <span className="muted small">First seen {c.firstSeen}</span>
              </p>
              <p>{c.summary}</p>
              {c.status === 'traced' && c.verdict && <p className="verdict small">Verdict on the claim: <strong>{verdictLabel(c.verdict)}</strong>{c.openIncidents ? `; ${c.openIncidents} incident${c.openIncidents === 1 ? '' : 's'} still open` : ''}.</p>}
              <p>
                {act.kind === 'brief' && <button className="primary" onClick={onBrief}>Open the brief</button>}
                {act.kind === 'ask' && <button className="primary" onClick={() => onAsk(act.question)}>{act.label}</button>}
                {act.kind === 'wait' && <span className="muted small">{act.why}</span>}
              </p>
            </li>
          )
        })}
      </ul>
    </section>
  )
}

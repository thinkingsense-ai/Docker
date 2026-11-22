import { useEffect, useRef, useState } from 'react'
import { ask, ApiError } from './api'
import { BRIEF_PACK, type Table } from './rcaBrief'
import { KINDS, SOURCES_QUESTION, composeSources, health, kindLabel, summaryLine } from './sourcesModel'

/** Sources: the feeds Watch reads and whether each is healthy. One approved question asked as the signed-in person. Health only: a headline, link and date are kept per item, never article text. */
export default function Sources({ table, onLoaded, onSignedOut }: { table: Table | null; onLoaded: (t: Table) => void; onSignedOut: () => void }) {
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  const abort = useRef<AbortController | null>(null)

  async function load() {
    setBusy(true); setErr(''); abort.current = new AbortController()
    try { const a = await ask(SOURCES_QUESTION, BRIEF_PACK, null, () => {}, abort.current.signal); onLoaded({ columns: a.columns ?? [], rows: a.rows ?? [] }) }
    catch (e) {
      if (e instanceof ApiError && e.status === 401) return onSignedOut()
      if (!(e instanceof DOMException && e.name === 'AbortError')) setErr(e instanceof Error ? e.message : 'The feed list could not be loaded.')
    } finally { setBusy(false) }
  }
  useEffect(() => { if (table === null) void load(); return () => abort.current?.abort() }, [])   // eslint-disable-line react-hooks/exhaustive-deps

  const now = new Date()
  const list = table ? composeSources(table) : []
  const line = table ? summaryLine(list, now) : null
  return (
    <section className="sources" aria-labelledby="sources-h">
      <header className="watch-head">
        <h2 id="sources-h">Sources</h2>
        <button onClick={load} disabled={busy}>{busy ? 'Loading…' : 'Refresh'}</button>
      </header>
      <p className="muted small">The feeds Watch reads, every 30 minutes. For each item the adapter keeps a headline, its link and date, and nothing else: no article text. Reuse terms for these sites have not been read.</p>
      {err && <p role="alert" className="error">{err}</p>}
      {busy && !table && <p role="status" className="muted">Loading feeds…</p>}
      {line && <p className={line.ok ? 'srcline ok' : 'srcline warn'} role="status">{line.text}</p>}
      {table && list.length > 0 && (
        <div className="tablewrap">
          <table data-tour="sources-table">
            <thead><tr><th>Feed</th><th>Kind</th><th>Health</th><th>Items read</th><th>Kept as leads</th></tr></thead>
            <tbody>
              {list.map((s) => {
                const h = health(s, now)
                return (
                  <tr key={s.name}>
                    <td>{s.name}</td>
                    <td><span className="grade" title={KINDS[s.kind]?.meaning}>{kindLabel(s.kind)}</span></td>
                    <td className={'h-' + h.state}>{h.text}</td>
                    <td>{s.itemsTotal}</td>
                    <td>{s.kind === 'context' ? <span className="muted small">reading only</span> : s.matchedTotal}</td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}
    </section>
  )
}

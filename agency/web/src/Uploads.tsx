import { useEffect, useRef, useState } from 'react'
import { api, uploadFile, type Adapter, type Upload } from './api'

interface Props { workspaceId: string | null; onAsk: (q: string) => void; onSignedOut: () => void }

const pct = (n: number) => Math.round(n * 100) + '%'

function AudioSummary({ r }: { r: Record<string, any> }) {
  const exp: any[] = r.expected ?? [], un: any[] = r.unaided ?? [], near: any[] = r.nearest ?? []
  return (
    <div className="aud">
      <p><strong>Among the collection's species:</strong> {exp.length ? exp.map((x) => `${x.common || x.scientific} ${pct(x.confidence)}`).join(', ') : 'nothing confident'}</p>
      <p><strong>Unaided (any species):</strong> {un.length ? un.map((x) => `${x.common || x.scientific} ${pct(x.confidence)}`).join(', ') : 'nothing confident'}</p>
      {near.length > 0 && <>
        <p className="muted small">Nearest recordings by audio vector:</p>
        <ul className="small">{near.map((n) => <li key={n.id}>{n.common || n.species} ({[n.country, n.license].filter(Boolean).join(', ')}) similarity {n.similarity}</li>)}</ul></>}
    </div>
  )
}

function TableSummary({ r }: { r: Record<string, any> }) {
  const cols: any[] = r.columns ?? [], rows: string[][] = r.preview ?? []
  const range = (c: any) => (c.min !== undefined ? `${c.min} to ${c.max}` : c.top ? c.top.map((t: any[]) => `${t[0]} (${t[1]})`).join(', ') : '')
  return (
    <div className="tbl">
      <p>{Number(r.rowsInFile).toLocaleString()} rows, {cols.length} columns{r.truncated ? ` (first ${Number(r.rowsRead).toLocaleString()} read)` : ''}</p>
      <div className="scroll"><table className="small">
        <caption className="muted">Column types are guesses from the values.</caption>
        <thead><tr><th scope="col">Column</th><th scope="col">Type</th><th scope="col">Empty</th><th scope="col">Distinct</th><th scope="col">Range or common values</th></tr></thead>
        <tbody>{cols.map((c) => <tr key={c.name}><th scope="row">{c.name}</th><td>{c.type}</td><td className="num">{c.nulls}</td><td className="num">{c.distinct}</td><td>{range(c)}</td></tr>)}</tbody>
      </table></div>
      {rows.length > 0 && <div className="scroll"><table className="small">
        <caption className="muted">First {rows.length} rows</caption>
        <thead><tr>{cols.map((c) => <th key={c.name} scope="col">{c.name}</th>)}</tr></thead>
        <tbody>{rows.map((row, i) => <tr key={i}>{row.map((v, j) => <td key={j}>{v}</td>)}</tr>)}</tbody>
      </table></div>}
    </div>
  )
}

function Card({ u, onAsk, onDelete }: { u: Upload; onAsk: (q: string) => void; onDelete: () => void }) {
  return (
    <article className="answer" aria-label={`Upload ${u.name}`}>
      <h2 className="q">{u.name} <span className="tag">{u.kind}</span>{u.nonCommercial && <span className="tag caution">non-commercial</span>}</h2>
      {u.kind === 'audio' && u.result ? <AudioSummary r={u.result} /> : u.kind === 'table' && u.result ? <TableSummary r={u.result} /> : u.result && <pre className="small">{JSON.stringify(u.result, null, 2)}</pre>}
      {u.notes.length > 0 && <ul className="warnings">{u.notes.map((n, i) => <li key={i}>{n}</li>)}</ul>}
      {u.licence && <p className="muted small">{u.licence}</p>}
      {u.askPrompts.length > 0 && <div className="follow"><span className="muted small">Ask about this:</span>{u.askPrompts.map((p) => <button key={p} className="chip" onClick={() => onAsk(p)}>{p}</button>)}</div>}
      <p className="muted small">Private to you. The file was not kept; this record expires {new Date(u.expiresAt).toLocaleTimeString()}. <button className="link" onClick={onDelete}>Delete now</button></p>
    </article>
  )
}

export default function Uploads({ workspaceId, onAsk, onSignedOut }: Props) {
  const [adapters, setAdapters] = useState<Adapter[]>([])
  const [accept, setAccept] = useState<string[]>([])
  const [ups, setUps] = useState<Upload[]>([])
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  const [over, setOver] = useState(false)
  const input = useRef<HTMLInputElement>(null)

  useEffect(() => {
    api.adapters().then((a) => { setAdapters(a.adapters); setAccept(a.accept) }).catch(() => {})
    api.uploads().then((u) => setUps(u.uploads)).catch(() => {})
  }, [])

  if (accept.length === 0) return adapters.length ? <p className="muted small">Uploads are off: {adapters.map((a) => `${a.title} ${a.reason ?? 'is disabled'}`).join('; ')}.</p> : null

  async function take(f: File | undefined) {
    if (!f) return
    const ok = accept.some((e) => f.name.toLowerCase().endsWith(e))
    if (!ok) { setErr(`${f.name}: this type is not accepted. Accepted: ${accept.join(' ')}`); return }       // refused before anything is sent
    setBusy(true); setErr('')
    try { const u = await uploadFile(f, workspaceId); setUps((x) => [u, ...x]) }
    catch (e: any) { if (e.status === 401) onSignedOut(); else setErr(e.message) }
    finally { setBusy(false); if (input.current) input.current.value = '' }
  }

  return (
    <section aria-label="Bring a file">
      <h2>Bring a file</h2>
      <div className={'drop' + (over ? ' over' : '')} onDragOver={(e) => { e.preventDefault(); setOver(true) }} onDragLeave={() => setOver(false)}
           onDrop={(e) => { e.preventDefault(); setOver(false); take(e.dataTransfer.files[0]) }}>
        <p>{busy ? 'Reading the file…' : <>Drop a file here or <button className="link" onClick={() => input.current?.click()}>choose one</button>. Accepted: {accept.join(' ')}</>}</p>
        <input ref={input} type="file" accept={accept.join(',')} hidden onChange={(e) => take(e.target.files?.[0])} aria-label="Choose a file to upload" />
        {adapters.filter((a) => a.enabled && a.nonCommercial).map((a) => <p key={a.id} className="warn">{a.title}: {a.licence}</p>)}
      </div>
      {err && <p role="alert" className="error">{err}</p>}
      {ups.map((u) => <Card key={u.id} u={u} onAsk={onAsk} onDelete={() => api.deleteUpload(u.id).then(() => setUps((x) => x.filter((y) => y.id !== u.id))).catch((e) => setErr(e.message))} />)}
    </section>
  )
}

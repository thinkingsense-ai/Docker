import { useEffect, useRef, useState } from 'react'
import { api, uploadFile, type Adapter, type Upload } from './api'

interface Props { compact?: boolean; workspaceId: string | null; onAsk: (q: string, uploadId?: string, uploadName?: string) => void; onSignedOut: () => void }

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

function DocSummary({ r }: { r: Record<string, any> }) {
  const heads: any[] = r.headings ?? [], terms: any[] = r.topTerms ?? []
  return (
    <div className="doc">
      <p>{String(r.format).toUpperCase()}: {Number(r.words).toLocaleString()} words{r.format === 'pdf' ? `, ${r.pages} pages` : ''}, {r.chunks} passages of about 800 characters</p>
      {heads.length > 0 && <><p className="muted small">Headings</p><ul className="small">{heads.map((h, i) => <li key={i} style={{ marginLeft: (h.level - 1) * 14 }}>{h.text}</li>)}</ul></>}
      {terms.length > 0 && <p className="small"><span className="muted">Most frequent words: </span>{terms.map((t) => `${t[0]} (${t[1]})`).join(', ')}</p>}
      {r.preview && <pre className="small preview">{r.preview}</pre>}
    </div>
  )
}

function ImageSummary({ r }: { r: Record<string, any> }) {
  const ex = Object.entries((r.exif ?? {}) as Record<string, string>), cols: any[] = r.colours ?? []
  const label: Record<string, string> = { cameraMake: 'Camera make', cameraModel: 'Camera model', software: 'Software', takenAt: 'Taken', modifiedAt: 'Modified' }
  return (
    <div className="img">
      {r.thumbnail && <img src={r.thumbnail} alt={`Small preview of ${r.name}`} className="thumb" />}
      <p>{r.format} · {r.width} × {r.height} ({r.megapixels} MP){r.frames > 1 ? ` · ${r.frames} frames` : ''}{r.transparent ? ' · transparent areas' : ''}</p>
      {ex.length > 0 ? <ul className="small">{ex.map(([k, v]) => <li key={k}>{label[k] ?? k}: {v}</li>)}</ul> : <p className="muted small">No camera or date metadata.</p>}
      {r.gps && <p className="warn small">Location in the file: {r.gps.lat}, {r.gps.lon}</p>}
      {cols.length > 0 && <p className="small"><span className="muted">Dominant colours: </span>{cols.map((c) => <span key={c.hex} className="swatch"><i style={{ background: c.hex }} aria-hidden="true" /> {c.hex} {Math.round(c.share * 100)}%</span>)}</p>}
    </div>
  )
}

function Card({ u, onAsk, onDelete, canShare, onShare }: { u: Upload; onAsk: (q: string, uploadId?: string, uploadName?: string) => void; onDelete?: () => void; canShare?: boolean; onShare?: (on: boolean) => void }) {
  const [asking, setAsking] = useState(false)
  const mine = u.mine !== false
  return (
    <article className="answer" aria-label={`Upload ${u.name}`}>
      <h2 className="q">{u.name} <span className={`tag kind-${u.kind}`}>{u.kind}</span>{u.nonCommercial && <span className="tag caution">non-commercial</span>}</h2>
      {u.kind === 'audio' && u.result ? <AudioSummary r={u.result} /> : u.kind === 'table' && u.result ? <TableSummary r={u.result} /> : u.kind === 'document' && u.result ? <DocSummary r={u.result} /> : u.kind === 'image' && u.result ? <ImageSummary r={u.result} /> : u.result && <pre className="small">{JSON.stringify(u.result, null, 2)}</pre>}
      {u.notes.length > 0 && <ul className="warnings">{u.notes.map((n, i) => <li key={i}>{n}</li>)}</ul>}
      {u.licence && <p className="muted small">{u.licence}</p>}
      {u.askPrompts.length > 0 && <div className="follow"><span className="muted small">Ask about this{u.askable && u.askableUntil ? ` (until ${new Date(u.askableUntil).toLocaleTimeString()})` : ''}:</span>{u.askPrompts.map((p) => <button key={p} className="chip" onClick={() => onAsk(p, u.askable ? u.id : undefined, u.name)}>{p}</button>)}</div>}
      {!mine && <p className="muted small">Shared by {u.sharedBy}{u.sharedAt ? ` at ${new Date(u.sharedAt).toLocaleTimeString()}` : ''} with everyone who can use {u.workspaceId}. Read-only. Any location in the file is hidden from you. Expires {new Date(u.expiresAt).toLocaleTimeString()}.</p>}
      {mine && <p className="muted small">{u.shared ? `Shared with everyone who can use ${u.workspaceId}.` : 'Private to you.'} The file was not kept; this record expires {new Date(u.expiresAt).toLocaleTimeString()}.{' '}
        {onDelete && <button className="link" onClick={onDelete}>Delete now</button>}</p>}
      {mine && canShare && onShare && (u.shared
        ? <p className="small"><button className="link" onClick={() => onShare(false)}>Stop sharing</button></p>
        : asking
          ? <div className="confirm small" role="group" aria-label="Confirm sharing"><p>Everyone who can use <strong>{u.workspaceId}</strong> will see this record, including its preview. Sharing does not extend how long it lasts, and a location in a picture is hidden from them.</p>
              <button onClick={() => { setAsking(false); onShare(true) }}>Share</button> <button className="link" onClick={() => setAsking(false)}>Cancel</button></div>
          : <p className="small">{u.workspaceId ? <button className="link" onClick={() => setAsking(true)}>Share with {u.workspaceId}…</button> : <span className="muted">Not made inside a pack, so it cannot be shared.</span>}</p>)}
    </article>
  )
}

export default function Uploads({ compact, workspaceId, onAsk, onSignedOut }: Props) {
  const [adapters, setAdapters] = useState<Adapter[]>([])
  const [accept, setAccept] = useState<string[]>([])
  const [ups, setUps] = useState<Upload[]>([])
  const [shared, setShared] = useState<Upload[]>([])
  const [sharing, setSharing] = useState('off')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  const [over, setOver] = useState(false)
  const input = useRef<HTMLInputElement>(null)

  useEffect(() => {
    api.adapters().then((a) => { setAdapters(a.adapters); setAccept(a.accept); setSharing(a.sharing ?? 'off') }).catch(() => {})
    api.uploads().then((u) => { setUps(u.uploads); setShared(u.shared ?? []) }).catch(() => {})
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

  const Wrap = ({ children }: { children: React.ReactNode }) => compact
    ? <details className="bring"><summary>Bring a file{ups.length ? ` (${ups.length} so far)` : ''}</summary>{children}</details>
    : <>{children}</>
  return (
    <section aria-label="Bring a file">
      {!compact && <h2>Bring a file</h2>}
      <Wrap>
      <div className={'drop' + (over ? ' over' : '')} onDragOver={(e) => { e.preventDefault(); setOver(true) }} onDragLeave={() => setOver(false)}
           onDrop={(e) => { e.preventDefault(); setOver(false); take(e.dataTransfer.files[0]) }}>
        <p>{busy ? 'Reading the file…' : <>Drop a file here or <button className="link" onClick={() => input.current?.click()}>choose one</button>. Accepted: {accept.join(' ')}</>}</p>
        <input ref={input} type="file" accept={accept.join(',')} hidden onChange={(e) => take(e.target.files?.[0])} aria-label="Choose a file to upload" />
        {adapters.filter((a) => a.enabled && a.nonCommercial).map((a) => <p key={a.id} className="warn">{a.title}: {a.licence}</p>)}
      </div>
      {err && <p role="alert" className="error">{err}</p>}
      {ups.map((u) => <Card key={u.id} u={u} onAsk={onAsk} canShare={sharing === 'workspace'} onShare={(on) => api.shareUpload(u.id, on).then((r) => setUps((x) => x.map((y) => (y.id === r.id ? r : y)))).catch((e) => setErr(e.message))} onDelete={() => api.deleteUpload(u.id).then(() => setUps((x) => x.filter((y) => y.id !== u.id))).catch((e) => setErr(e.message))} />)}
      {sharing === 'workspace' && <p className="small"><button className="link" onClick={() => api.uploads().then((u) => setShared(u.shared ?? [])).catch((e) => setErr(e.message))}>Check for uploads shared with you</button></p>}
      {shared.length > 0 && <><h2>Shared with you</h2>{shared.map((u) => <Card key={u.id} u={u} onAsk={onAsk} />)}</>}
      </Wrap>
    </section>
  )
}

import { useCallback, useEffect, useRef, useState } from 'react'
import { api, ask, ApiError, type Answer as A, type ConversationSummary, type Pack, type Starter, type Status } from './api'
import Login from './Login'
import PackCards from './PackCards'
import Answer from './Answer'
import Uploads from './Uploads'
import StarterTiles from './StarterTiles'
import { AnswerDetails, ProgressView } from './DetailsPane'
import type { ProgressEvent as PEvent } from './progress'
import { Queue } from './Workflows'
import type { Definition } from './workflow'

const LS = 'agency.pack'

function lsGet(): string | null { try { return localStorage.getItem(LS) } catch { return null } }
function lsSet(v: string | null) { try { v ? localStorage.setItem(LS, v) : localStorage.removeItem(LS) } catch { /* private window */ } }

interface Turn { question: string; answer: A }

export default function App() {
  const [user, setUser] = useState<string | null | undefined>(undefined)       // undefined = checking
  const [status, setStatus] = useState<Status | null>(null)
  const [packs, setPacks] = useState<Pack[]>([])
  const [packNote, setPackNote] = useState<string | null>(null)
  const [pack, setPack] = useState<string | null>(null)
  const [changed, setChanged] = useState('')
  const [showDomains, setShowDomains] = useState(false)          // the full domain cards: on request, not taking the first screen
  const [starters, setStarters] = useState<Starter[]>([])
  const [convs, setConvs] = useState<ConversationSummary[]>([])
  const [convId, setConvId] = useState<string | null>(null)
  const [file, setFile] = useState<{ id: string; name: string } | null>(null)    // a table being asked about: questions carry it until the person lets go or starts over
  const [turns, setTurns] = useState<Turn[]>([])
  const [q, setQ] = useState('')
  const [steps, setSteps] = useState<PEvent[]>([])
  const [startedAt, setStartedAt] = useState(0)
  const [paneOpen, setPaneOpen] = useState<boolean>(() => { try { const v = localStorage.getItem('agency.pane'); return v === null ? window.innerWidth >= 1100 : v === '1' } catch { return false } })
  const [detailIdx, setDetailIdx] = useState<number | null>(null)
  const togglePane = () => setPaneOpen((o) => { try { localStorage.setItem('agency.pane', o ? '0' : '1') } catch { /* private window */ } return !o })
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  const [grants, setGrants] = useState<{ canStart: boolean; canApprove: boolean }>({ canStart: false, canApprove: false })
  const [defs, setDefs] = useState<Definition[]>([])
  const [view, setView] = useState<'ask' | 'approvals'>('ask')
  const [waiting, setWaiting] = useState<number | null>(null)
  const abort = useRef<AbortController | null>(null)
  const bottom = useRef<HTMLDivElement>(null)

  const signedOut = useCallback(() => { setUser(null); setTurns([]); setConvId(null); setFile(null) }, [])
  const guard = useCallback((e: unknown) => { if (e instanceof ApiError && e.status === 401) signedOut(); else setErr((e as Error).message) }, [signedOut])

  useEffect(() => { api.whoami().then((w) => setUser(w.username ?? w.layerUser ?? 'signed in')).catch(() => setUser(null)) }, [])

  // workflows: only when the Server has them on (status) and this user holds a workflow grant (whoami); the Server enforces both again on every call
  const refreshWaiting = useCallback(() => { api.workflowQueue().then((q) => setWaiting(q.count)).catch(() => setWaiting(null)) }, [])
  useEffect(() => {
    if (!user || !status?.workflows?.available) { setGrants({ canStart: false, canApprove: false }); setDefs([]); return }
    api.whoami().then((w) => {
      const g = { canStart: w.canStartWorkflows === true, canApprove: w.canApprove === true }; setGrants(g)
      if (g.canStart || g.canApprove) api.workflowDefinitions().then((d) => setDefs(d.definitions)).catch(() => setDefs([]))
      if (g.canApprove) refreshWaiting()
    }).catch(() => {})
  }, [user, status, refreshWaiting])

  // after sign-in: status, packs, the remembered pack (URL, then the layer's preference, then localStorage)
  useEffect(() => {
    if (!user) return
    api.status().then(setStatus).catch(() => {})
    Promise.all([api.packs(), api.preferences().catch(() => ({} as { pack?: string }))]).then(([p, pref]) => {
      setPacks(p.packs); setPackNote(p.note)
      const want = new URLSearchParams(location.search).get('pack') ?? pref.pack ?? lsGet()
      const ok = p.packs.find((x) => x.id === want)
      setPack(ok ? ok.id : null)
    }).catch(guard)
    api.conversations().then((c) => setConvs(c.conversations ?? [])).catch(() => {})
  }, [user, guard])

  useEffect(() => {
    if (!user) return
    let current = true                                  // a slower answer for an earlier choice must not replace the starters of the one now selected
    api.starters(pack).then((s) => { if (current) setStarters(s.items ?? (s.questions ?? []).map((question) => ({ question, origin: 'suggested' as const }))) }).catch(() => { if (current) setStarters([]) })
    return () => { current = false }
  }, [user, pack])
  useEffect(() => { bottom.current?.scrollIntoView({ behavior: 'smooth', block: 'end' }) }, [turns, steps])

  function choose(id: string | null) {
    if (id === pack) return
    setPack(id); setConvId(null); setFile(null); setTurns([]); setDetailIdx(null); setErr('')
    const p = packs.find((x) => x.id === id)
    setChanged(`Asking in ${p ? p.title : 'All data'}. Starter questions updated and a new conversation started.`)
    lsSet(id); api.setPreference(id).catch(() => {})
    const url = new URL(location.href); id ? url.searchParams.set('pack', id) : url.searchParams.delete('pack'); history.replaceState(null, '', url)
  }

  async function send(text: string, uploadId?: string, uploadName?: string) {
    const question = text.trim(); if (!question || busy) return
    setBusy(true); setErr(''); setSteps([]); setStartedAt(Date.now()); setQ(''); const ac = new AbortController(); abort.current = ac
    try {
      const a = await ask(question, pack, convId, (e) => setSteps((s) => [...s, { ...e, t: Date.now() }]), ac.signal, uploadId ?? file?.id)
      setTurns((t) => { setDetailIdx(t.length); return [...t, { question, answer: a }] }); if (a.conversationId) setConvId(a.conversationId)
      if (uploadId) setFile({ id: uploadId, name: uploadName ?? 'your file' })
      api.conversations().then((c) => setConvs(c.conversations ?? [])).catch(() => {})
    } catch (e) {
      if ((e as Error).name === 'AbortError') setErr('Cancelled.'); else { if ((e as { code?: string }).code === 'upload_expired') setFile(null); guard(e) }
    } finally { setBusy(false); setSteps([]); abort.current = null }
  }

  async function open(id: string) {
    setErr('')
    try {
      const c = await api.conversation(id)
      if (!c.success) return setErr(c.error ?? 'That conversation could not be opened.')
      setConvId(id); setDetailIdx(null); setChanged('Opened a past conversation. Its answers show the saved text and rows; evidence is only kept for answers asked now.')
      setTurns((c.turns ?? []).map((t) => ({ question: t.question, answer: { answer: t.answer, columns: t.columns, rows: t.rows, sql: t.sql ?? null, conversationId: id, evidence: null } })))
    } catch (e) { guard(e) }
  }

  if (user === undefined) return <main className="center muted">Loading…</main>
  if (user === null) return <Login onDone={() => api.whoami().then((w) => setUser(w.username ?? w.layerUser ?? 'signed in')).catch(() => setUser(null))} />

  const wf = status?.workflows
  return (
    <div className={'shell' + (paneOpen ? ' with-pane' : '')}>
      <header>
        <h1>Agency</h1>
        <div className="who">
          <span title="Server reachability">{status ? (status.server.reachable ? 'Server reachable' : 'Server not reachable') : '…'}</span>
          {status?.edition && <span title="The edition the Server reports for this session">{status.edition === 'commercial' ? 'Commercial edition' : 'Free edition'}</span>}
          {wf && <span title={wf.note}>{wf.available ? 'Workflows available' : 'Workflows off'}</span>}
          <button className="link" aria-expanded={paneOpen} aria-controls="pane" onClick={togglePane}>{paneOpen ? 'Hide details' : 'Show details'}</button>
          {status?.adminUrl && <a className="link quiet" href={status.adminUrl} target="_blank" rel="noopener noreferrer" title="Opens the admin console, which has its own sign-in">Manage<span className="sr-only"> (opens the admin console in a new tab)</span></a>}
          <span>{user}</span>
          <button className="link" onClick={() => api.logout().finally(signedOut)}>Sign out</button>
        </div>
      </header>
      <nav aria-label="Conversations">
        <button className="primary" onClick={() => { setConvId(null); setFile(null); setTurns([]); setDetailIdx(null); setChanged('New conversation.') }}>New conversation</button>
        <h2>Recent</h2>
        {convs.length === 0 && <p className="muted small">No conversations yet.</p>}
        <ul>{convs.map((c) => <li key={c.id}><button className={'link' + (c.id === convId ? ' on' : '')} onClick={() => open(c.id)}>{c.title || 'Untitled'}</button></li>)}</ul>
        <p className="muted small">The Server lists conversations per user, not per domain.</p>
        {grants.canApprove && (
          <>
            <h2>Approvals</h2>
            <button className={'link' + (view === 'approvals' ? ' on' : '')} onClick={() => setView(view === 'approvals' ? 'ask' : 'approvals')}>
              {view === 'approvals' ? 'Back to questions' : `Waiting for me${waiting ? ` (${waiting})` : ''}`}</button>
          </>
        )}
      </nav>
      <main>
        {view === 'approvals' && <Queue me={user} onSignedOut={signedOut} onCount={setWaiting} />}
        {view === 'ask' && <>
        {packNote && <p className="muted small">{packNote}</p>}
        <PackCards packs={packs} selected={pack} onSelect={choose} compact={!showDomains || turns.length > 0 || busy} />
        <p className="muted small domain-line" role="status" aria-live="polite">
          {packs.find((p) => p.id === pack)?.summary ?? (pack ? '' : 'Every source this Server can reach. Choose a domain for better answers.')}
          {turns.length === 0 && !busy && packs.length > 0 && <> <button className="link" aria-expanded={showDomains} onClick={() => setShowDomains(!showDomains)}>{showDomains ? 'Hide domain details' : 'Compare domains'}</button></>}
          <span className="sr">{changed}</span>
        </p>
        {turns.length === 0 && !busy && <StarterTiles key={pack ?? 'all'} items={starters} label={pack ? `Approved questions: ${packs.find((p) => p.id === pack)?.title ?? pack}` : 'Approved questions'} onPick={send} />}
        <Uploads workspaceId={pack} onAsk={(q, id, n) => send(q, id, n)} onSignedOut={signedOut} />
        {turns.map((t, i) => <Answer key={i} a={t.answer} question={t.question} onFollow={send} onDetails={() => { setDetailIdx(i); if (!paneOpen) togglePane() }} active={paneOpen && detailIdx === i} wf={defs.length ? { defs, canStart: grants.canStart, me: user, onSignedOut: signedOut, onChange: refreshWaiting } : undefined} />)}
        {busy && !paneOpen && (
          <div className="progress" role="status" aria-live="polite">
            <span>Working on it…</span> <button onClick={() => abort.current?.abort()}>Cancel</button> <button className="link" onClick={togglePane}>Show progress</button>
          </div>
        )}
        {err && <p role="alert" className="error">{err}</p>}
        <div ref={bottom} />
        {file && <p className="small filechip" role="status">Asking about <strong>{file.name}</strong> (a table you uploaded; only you see it). <button className="link" onClick={() => setFile(null)}>Stop using it</button></p>}
        <form className="askbar" onSubmit={(e) => { e.preventDefault(); send(q) }}>
          <label className="sr" htmlFor="q">Ask a question</label>
          <input id="q" value={q} onChange={(e) => setQ(e.target.value)} placeholder={pack ? `Ask about ${packs.find((p) => p.id === pack)?.title ?? pack}` : 'Ask about any of your data'} maxLength={4000} disabled={busy} />
          <button className="primary" disabled={busy || !q.trim()}>Ask</button>
        </form>
        </>}
      </main>
      {paneOpen && (
        <aside id="pane" className="pane" aria-label="Details">
          <button className="link close-pane" onClick={togglePane}>Close</button>
          {busy
            ? <ProgressView events={steps} startedAt={startedAt} onCancel={() => abort.current?.abort()} />
            : <AnswerDetails a={detailIdx !== null ? turns[detailIdx]?.answer ?? null : null} question={detailIdx !== null ? turns[detailIdx]?.question ?? '' : ''} historic={detailIdx !== null && turns[detailIdx]?.answer.evidence === null} />}
        </aside>)}
    </div>
  )
}



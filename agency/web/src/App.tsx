import { useCallback, useEffect, useRef, useState } from 'react'
import { api, ask, ApiError, type Answer as A, type ConversationSummary, type Pack, type ProgressEvent, type Starter, type Status } from './api'
import Login from './Login'
import PackCards from './PackCards'
import Answer from './Answer'
import Uploads from './Uploads'
import { Queue } from './Workflows'
import type { Definition } from './workflow'

const STEP_LABEL: Record<string, string> = {
  understanding: 'Understanding the question', planned: 'Planning which sources to use', sql: 'Writing the query', check: 'Checking the query',
  ontology: 'Applying business definitions', results: 'Running the query', done: 'Done',
}
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
  const [starters, setStarters] = useState<Starter[]>([])
  const [convs, setConvs] = useState<ConversationSummary[]>([])
  const [convId, setConvId] = useState<string | null>(null)
  const [turns, setTurns] = useState<Turn[]>([])
  const [q, setQ] = useState('')
  const [steps, setSteps] = useState<ProgressEvent[]>([])
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  const [grants, setGrants] = useState<{ canStart: boolean; canApprove: boolean }>({ canStart: false, canApprove: false })
  const [defs, setDefs] = useState<Definition[]>([])
  const [view, setView] = useState<'ask' | 'approvals'>('ask')
  const [waiting, setWaiting] = useState<number | null>(null)
  const abort = useRef<AbortController | null>(null)
  const bottom = useRef<HTMLDivElement>(null)

  const signedOut = useCallback(() => { setUser(null); setTurns([]); setConvId(null) }, [])
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

  useEffect(() => { if (user) api.starters(pack).then((s) => setStarters(s.items ?? (s.questions ?? []).map((question) => ({ question, origin: 'suggested' as const })))).catch(() => setStarters([])) }, [user, pack])
  useEffect(() => { bottom.current?.scrollIntoView({ behavior: 'smooth', block: 'end' }) }, [turns, steps])

  function choose(id: string | null) {
    if (id === pack) return
    setPack(id); setConvId(null); setTurns([]); setErr('')
    const p = packs.find((x) => x.id === id)
    setChanged(`Asking in ${p ? p.title : 'All data'}. Starter questions updated and a new conversation started.`)
    lsSet(id); api.setPreference(id).catch(() => {})
    const url = new URL(location.href); id ? url.searchParams.set('pack', id) : url.searchParams.delete('pack'); history.replaceState(null, '', url)
  }

  async function send(text: string) {
    const question = text.trim(); if (!question || busy) return
    setBusy(true); setErr(''); setSteps([]); setQ(''); const ac = new AbortController(); abort.current = ac
    try {
      const a = await ask(question, pack, convId, (e) => setSteps((s) => [...s, e]), ac.signal)
      setTurns((t) => [...t, { question, answer: a }]); if (a.conversationId) setConvId(a.conversationId)
      api.conversations().then((c) => setConvs(c.conversations ?? [])).catch(() => {})
    } catch (e) {
      if ((e as Error).name === 'AbortError') setErr('Cancelled.'); else guard(e)
    } finally { setBusy(false); setSteps([]); abort.current = null }
  }

  async function open(id: string) {
    setErr('')
    try {
      const c = await api.conversation(id)
      if (!c.success) return setErr(c.error ?? 'That conversation could not be opened.')
      setConvId(id); setChanged('Opened a past conversation. Its answers show the saved text and rows; evidence is only kept for answers asked now.')
      setTurns((c.turns ?? []).map((t) => ({ question: t.question, answer: { answer: t.answer, columns: t.columns, rows: t.rows, sql: t.sql ?? null, conversationId: id, evidence: null } })))
    } catch (e) { guard(e) }
  }

  if (user === undefined) return <main className="center muted">Loading…</main>
  if (user === null) return <Login onDone={() => api.whoami().then((w) => setUser(w.username ?? w.layerUser ?? 'signed in')).catch(() => setUser(null))} />

  const wf = status?.workflows
  return (
    <div className="shell">
      <header>
        <h1>Agency</h1>
        <div className="who">
          <span title="Server reachability">{status ? (status.server.reachable ? 'Server reachable' : 'Server not reachable') : '…'}</span>
          {wf && <span title={wf.note}>{wf.available ? 'Workflows available' : 'Workflows: commercial edition'}</span>}
          <span>{user}</span>
          <button className="link" onClick={() => api.logout().finally(signedOut)}>Sign out</button>
        </div>
      </header>
      <nav aria-label="Conversations">
        <button className="primary" onClick={() => { setConvId(null); setTurns([]); setChanged('New conversation.') }}>New conversation</button>
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
        <PackCards packs={packs} selected={pack} onSelect={choose} compact={turns.length > 0 || busy} />
        <p className="muted small" role="status" aria-live="polite">{changed}</p>
        {turns.length === 0 && !busy && (
          <section aria-label="Starter questions">
            <h2>Try a question</h2>
            {starters.length === 0 ? <p className="muted">No starter questions for this choice.</p> :
              <ul className="starters">{starters.slice(0, 12).map((s) => (
                <li key={s.question}><button className="chip" onClick={() => send(s.question)}>{s.question}<span className={'tag ' + s.origin}>{s.origin}</span></button></li>))}</ul>}
          </section>
        )}
        <Uploads workspaceId={pack} onAsk={send} onSignedOut={signedOut} />
        {turns.map((t, i) => <Answer key={i} a={t.answer} question={t.question} onFollow={send} wf={defs.length ? { defs, canStart: grants.canStart, me: user, onSignedOut: signedOut, onChange: refreshWaiting } : undefined} />)}
        {busy && (
          <div className="progress" role="status" aria-live="polite">
            <ol>{steps.map((s, i) => <li key={i}>{STEP_LABEL[s.step] ?? s.step}</li>)}{steps.length === 0 && <li>Sending the question…</li>}</ol>
            <button onClick={() => abort.current?.abort()}>Cancel</button>
          </div>
        )}
        {err && <p role="alert" className="error">{err}</p>}
        <div ref={bottom} />
        <form className="askbar" onSubmit={(e) => { e.preventDefault(); send(q) }}>
          <label className="sr" htmlFor="q">Ask a question</label>
          <input id="q" value={q} onChange={(e) => setQ(e.target.value)} placeholder={pack ? `Ask about ${packs.find((p) => p.id === pack)?.title ?? pack}` : 'Ask about any of your data'} maxLength={4000} disabled={busy} />
          <button className="primary" disabled={busy || !q.trim()}>Ask</button>
        </form>
        </>}
      </main>
    </div>
  )
}



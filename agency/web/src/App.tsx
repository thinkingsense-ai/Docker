import { useCallback, useEffect, useRef, useState } from 'react'
import { api, ask, ApiError, type Answer as A, type ConversationSummary, type Pack, type Starter, type Status } from './api'
import Login from './Login'
import Answer from './Answer'
import Uploads from './Uploads'
import StarterTiles from './StarterTiles'
import Brief from './Brief'
import { BRIEF_PACK } from './rcaBrief'
import Sources from './Sources'
import Watch from './Watch'
import Exposure, { type ExposureAnswers } from './Exposure'
import Priorities from './Priorities'
import Clocks, { type ClockAnswers } from './Clocks'
import Audit from './Audit'
import { rate as rateExposure } from './exposureModel'
import type { Table } from './rcaBrief'
import Tour from './Tour'
import Flow from './Flow'
import { navFor, roleLabel, startWorkspace, viewFor, workspaceChoices, type View } from './shell'
import { AnswerDetails, ProgressView } from './DetailsPane'
import type { ProgressEvent as PEvent } from './progress'
import { Queue } from './Workflows'
import type { Definition } from './workflow'

const LS = 'agency.pack'

function lsGet(): string | null { try { return localStorage.getItem(LS) } catch { return null } }
function lsSet(v: string | null) { try { v ? localStorage.setItem(LS, v) : localStorage.removeItem(LS) } catch { /* private window */ } }

/** Seconds since the question was sent, so a long wait is visible without opening the details pane. */
function Elapsed({ since }: { since: number }) {
  const [now, setNow] = useState(Date.now())
  useEffect(() => { const t = setInterval(() => setNow(Date.now()), 1000); return () => clearInterval(t) }, [])
  const s = Math.max(0, Math.round((now - since) / 1000))
  return <span className="muted">{s >= 5 ? (s >= 60 ? `${Math.floor(s / 60)} min ${s % 60} s` : `${s} s`) : ''}</span>
}

interface Turn { question: string; answer: A }

export default function App() {
  const [user, setUser] = useState<string | null | undefined>(undefined)       // undefined = checking
  const [status, setStatus] = useState<Status | null>(null)
  const [packs, setPacks] = useState<Pack[]>([])
  const [packNote, setPackNote] = useState<string | null>(null)
  const [pack, setPack] = useState<string | null>(null)
  const [changed, setChanged] = useState('')
  const [watch, setWatch] = useState<Table | null>(null)      // the Watch list, kept so switching sections does not ask again
  const [sources, setSources] = useState<Table | null>(null)    // the feed list and its health, kept for Watch's health line and the Sources screen
  const [clocks, setClocks] = useState<ClockAnswers | null>(null)   // the incidents and notification rules, kept so switching sections does not ask again
  const [priorities, setPriorities] = useState<Table | null>(null)   // the Priorities answer, kept so switching sections does not ask again
  const [exposure, setExposure] = useState<ExposureAnswers | null>(null)   // the five exposure answers, kept so switching sections does not ask again
  const [navOpen, setNavOpen] = useState(false)                  // the left navigation as a drawer on a phone
  const [starters, setStarters] = useState<Starter[]>([])
  const [convs, setConvs] = useState<ConversationSummary[]>([])
  const [convId, setConvId] = useState<string | null>(null)
  const [file, setFile] = useState<{ id: string; name: string } | null>(null)    // a table being asked about: questions carry it until the person lets go or starts over
  const [turns, setTurns] = useState<Turn[]>([])
  const [early, setEarly] = useState<{ columns: string[]; rows: (string | null)[][] } | null>(null)   // the rows, shown as soon as the Server sends them: the written answer follows (the Server calls a model for the prose after the rows are ready, Server#143)
  const [q, setQ] = useState('')
  const [steps, setSteps] = useState<PEvent[]>([])
  const [startedAt, setStartedAt] = useState(0)
  const [paneOpen, setPaneOpen] = useState<boolean>(() => { try { const v = localStorage.getItem('agency.pane'); return window.innerWidth >= 1100 && v === '1' } catch { return false } })
  const [detailIdx, setDetailIdx] = useState<number | null>(null)
  const togglePane = () => setPaneOpen((o) => { try { localStorage.setItem('agency.pane', o ? '0' : '1') } catch { /* private window */ } return !o })
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  const [asking, setAsking] = useState('')                   // the question being answered, shown while it works
  const [retry, setRetry] = useState<string | null>(null)     // the question that did not get an answer, offered again
  const [notice, setNotice] = useState('')                    // why the sign-in page is showing, when the person did not ask for it
  const [grants, setGrants] = useState<{ canStart: boolean; canApprove: boolean }>({ canStart: false, canApprove: false })
  const [defs, setDefs] = useState<Definition[]>([])
  const [view, setView] = useState<View>('watch')
  const [waiting, setWaiting] = useState<number | null>(null)
  const [tourOpen, setTourOpen] = useState(false)
  const [tourMin, setTourMin] = useState(false)
  const [tourFocus, setTourFocus] = useState<string[]>([])
  const [wide, setWide] = useState(() => window.innerWidth >= 1100)
  useEffect(() => { const f = () => setWide(window.innerWidth >= 1100); window.addEventListener('resize', f); return () => window.removeEventListener('resize', f) }, [])
  const userNow = useRef<string | null | undefined>(undefined)       // the tour's play loop outlives the render it started in, so it asks for who is signed in NOW, not who was when it began
  userNow.current = user
  const switching = useRef(false)                         // the guided tour is changing who is signed in: a refusal from the person it replaced is not a lost session
  const abort = useRef<AbortController | null>(null)
  const bottom = useRef<HTMLDivElement>(null)

  const leave = useCallback(() => { setUser(null); setTurns([]); setConvId(null); setFile(null); setView('watch'); setWatch(null); setSources(null); setExposure(null); setPriorities(null); setClocks(null); setNavOpen(false); setWaiting(null); setDetailIdx(null) }, [])
  const signedOut = useCallback(() => { leave(); setQ(''); setRetry(null); setNotice('') }, [leave])
  // the Server dropped the session (it restarted, or it expired): back to sign-in, saying so, with the unsent question kept in the box
  const expired = useCallback((kept?: boolean) => { if (switching.current) return; leave(); setNotice('Your session ended (the Server may have restarted). Sign in again.' + (kept === true ? ' The question you were asking is kept.' : '')) }, [leave])
  const guard = useCallback((e: unknown) => { if (e instanceof ApiError && e.status === 401) { if (!switching.current) expired() } else setErr((e as Error).message) }, [expired])

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
      setPack(startWorkspace(p.packs, want))
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
    setChanged(`Workspace: ${p ? p.title : 'All data'}. Starter questions updated and a new conversation started.`)
    lsSet(id); api.setPreference(id).catch(() => {})
    const url = new URL(location.href); id ? url.searchParams.set('pack', id) : url.searchParams.delete('pack'); history.replaceState(null, '', url)
  }

  async function send(text: string, uploadId?: string, uploadName?: string) {
    const question = text.trim(); if (!question || busy) return
    setBusy(true); setAsking(question); setErr(''); setRetry(null); setSteps([]); setEarly(null); setStartedAt(Date.now()); setQ(''); const ac = new AbortController(); abort.current = ac
    try {
      const a = await ask(question, pack, convId, (e) => { setSteps((s) => [...s, { ...e, t: Date.now() }]); if (e.step === 'results' && Array.isArray(e.columns) && Array.isArray(e.rows)) setEarly({ columns: e.columns, rows: e.rows }) }, ac.signal, uploadId ?? file?.id)
      setTurns((t) => { setDetailIdx(t.length); return [...t, { question, answer: a }] }); if (a.conversationId) setConvId(a.conversationId)
      if (uploadId) setFile({ id: uploadId, name: uploadName ?? 'your file' })
      api.conversations().then((c) => setConvs(c.conversations ?? [])).catch(() => {})
      api.status().then(setStatus).catch(() => {})
    } catch (e) {
      const expiredSession = e instanceof ApiError && e.status === 401
      setQ(question)                                  // nothing was answered: the question goes back in the box instead of being lost
      if ((e as Error).name === 'AbortError') setErr('Cancelled. Your question is back in the box.')
      else {
        if ((e as { code?: string }).code === 'upload_expired') setFile(null)
        if ((e as { code?: string }).code === 'server_unreachable') setStatus((st) => (st ? { ...st, server: { ...st.server, reachable: false } } : st))
        if (expiredSession) expired(true); else { setRetry(question); guard(e) }
      }
    } finally { setBusy(false); setAsking(''); setSteps([]); setEarly(null); abort.current = null }
  }

  async function open(id: string) {
    setErr('')
    try {
      const c = await api.conversation(id)
      if (!c.success) return setErr(c.error ?? 'That conversation could not be opened.')
      setView('ask'); setNavOpen(false); setConvId(id); setDetailIdx(null); setChanged('Opened a past conversation. Its answers show the saved text and rows; evidence is only kept for answers asked now.')
      setTurns((c.turns ?? []).map((t) => ({ question: t.question, answer: { answer: t.answer, columns: t.columns, rows: t.rows, sql: t.sql ?? null, conversationId: id, evidence: null } })))
    } catch (e) { guard(e) }
  }

  if (user === undefined) return <main className="center muted">Loading…</main>
  if (user === null) return <Login notice={notice} onDone={() => { setNotice(''); api.whoami().then((w) => setUser(w.username ?? w.layerUser ?? 'signed in')).catch(() => setUser(null)) }} />

  const wf = status?.workflows
  // the guided tour (local demo sandbox): the layer signs in as the named demo person; everything this person saw is dropped, as on any sign-out, but the screen stays
  async function switchTo(name: string) {
    if (name === userNow.current) return
    switching.current = true
    try {
      await api.tourSignin(name)
      setTurns([]); setConvId(null); setFile(null); setWatch(null); setSources(null); setExposure(null); setPriorities(null); setClocks(null); setWaiting(null); setDetailIdx(null); setStatus(null); setDefs([]); setGrants({ canStart: false, canApprove: false })
      userNow.current = name; setUser(name)
    } finally { setTimeout(() => { switching.current = false }, 1500) }
  }
  const navGrants = { ...grants, audit: status?.audit?.allowed === true }
  const shown = viewFor(view, navGrants)
  const go = (v: View) => { setView(v); setNavOpen(false); setErr('') }
  return (
    <div className={'shell' + (paneOpen ? ' with-pane' : '') + (tourOpen && wide && !tourMin ? ' with-tour' : '')}>
      <header>
        <button className="link menu" aria-expanded={navOpen} aria-controls="sidenav" onClick={() => setNavOpen((o) => !o)}>Menu</button>
        <h1 className="brand">Agency <span className="by">by</span> <img src="/thinkingsense-wordmark.png" alt="Thinking Sense" width="117" height="26" /></h1>
        <div className="who">
          <span title="Server reachability">{status ? (status.server.reachable ? 'Server reachable' : 'Server not reachable') : '…'}</span>
          {status?.edition && <span title="The edition the Server reports for this session">{status.edition === 'commercial' ? 'Commercial edition' : 'Free edition'}</span>}
          {wf && <span title={wf.note}>{wf.available ? 'Workflows available' : 'Workflows off'}</span>}
          {status?.tour?.enabled && <button className="primary" onClick={() => setTourOpen(true)} title="A click-through of the whole demo">Quickstart tour</button>}
          <button className="link" aria-expanded={paneOpen} aria-controls="pane" onClick={togglePane}>{paneOpen ? 'Hide details' : 'Show details'}</button>
          {status?.adminUrl && <a className="link quiet" href={status.adminUrl} target="_blank" rel="noopener noreferrer" title="Opens the admin console, which has its own sign-in">Manage<span className="sr-only"> (opens the admin console in a new tab)</span></a>}
          <label className="ws"><span className="sr">Workspace</span>
            <select value={pack ?? ''} onChange={(e) => choose(e.target.value || null)} title="Workspace. More arrive later.">
              {pack === null && <option value="">No Workspace</option>}
              {workspaceChoices(packs).map((p) => <option key={p.id} value={p.id}>{p.title}</option>)}
            </select></label>
          <span>{user}</span>
          <span className="muted small" title={roleLabel(grants).note}>{roleLabel(grants).text}</span>
          <button className="link" onClick={() => api.logout().finally(signedOut)}>Sign out</button>
        </div>
      </header>
      <nav id="sidenav" aria-label="Sections" className={navOpen ? 'open' : ''}>
        <ul className="sections">
          {navFor(navGrants).map((n) => {
            const on = viewFor(view, navGrants) === n.id
            return <li key={n.id}><button className={'navitem' + (on ? ' on' : '')} aria-current={on ? 'page' : undefined} title={n.hint} onClick={() => go(n.id)}>
              {n.label}{n.id === 'approvals' && waiting ? <span className="count" aria-label={`${waiting} waiting`}>{waiting}</span> : null}</button></li>
          })}
        </ul>
        {shown === 'ask' && <>
          <button className="primary" onClick={() => { setConvId(null); setFile(null); setTurns([]); setDetailIdx(null); setChanged('New conversation.') }}>New conversation</button>
          <h2>Recent</h2>
          {convs.length === 0 && <p className="muted small">No conversations yet.</p>}
          <ul>{convs.map((c) => <li key={c.id}><button className={'link' + (c.id === convId ? ' on' : '')} title={c.title || 'Untitled'} onClick={() => open(c.id)}><span className="t">{c.title || 'Untitled'}</span>{c.updatedAtMillis ? <span className="when">{new Date(c.updatedAtMillis).toLocaleString([], { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })}</span> : null}</button></li>)}</ul>
          <p className="muted small">The Server lists conversations per user, not per Workspace.</p>
        </>}
      </nav>
      <main>
        {shown === 'briefs' && (pack === BRIEF_PACK
          ? <Brief onSignedOut={() => expired()} me={user ?? ''} canStart={grants.canStart} defs={defs} />
          : <p className="empty">Problem records are in the IT risk Workspace. Choose it from the Workspace menu at the top right.</p>)}
        {shown === 'approvals' && <Queue me={user} onSignedOut={() => expired()} onCount={setWaiting} />}
        {shown === 'watch' && <Watch table={watch} sources={sources} onLoaded={setWatch} onSources={setSources} onBrief={() => go('briefs')} onAsk={(q) => { go('ask'); setConvId(null); setTurns([]); void send(q) }} onSignedOut={() => expired()} />}
        {shown === 'audit' && <Audit onSignedOut={() => expired()} />}
        {shown === 'clocks' && (pack === BRIEF_PACK
          ? <Clocks me={user ?? ''} canStart={grants.canStart} defs={defs} answers={clocks} onAnswers={setClocks} onSignedOut={() => expired()} />
          : <p className="empty">Notifications is in the IT risk Workspace. Choose it from the Workspace menu at the top right.</p>)}
        {shown === 'priorities' && (pack === BRIEF_PACK
          ? <Priorities me={user ?? ''} canStart={grants.canStart} defs={defs} answer={priorities} exposureLevel={exposure ? rateExposure(exposure).level : null} onAnswer={setPriorities} onSignedOut={() => expired()} />
          : <p className="empty">Priorities is in the IT risk Workspace. Choose it from the Workspace menu at the top right.</p>)}
        {shown === 'exposure' && (pack === BRIEF_PACK
          ? <Exposure answers={exposure} onAnswers={setExposure} onSignedOut={() => expired()} />
          : <p className="empty">Exposure is in the IT risk Workspace. Choose it from the Workspace menu at the top right.</p>)}
        {shown === 'flow' && <Flow focus={tourFocus} />}
        {shown === 'sources' && <Sources table={sources} onLoaded={setSources} onSignedOut={() => expired()} />}
        {shown === 'ask' && <>
        {packNote && <p className="muted small">{packNote}</p>}
        <p className="muted small domain-line" role="status" aria-live="polite">
          {packs.find((p) => p.id === pack)?.summary ?? 'Every source this Server can reach. Choose a Workspace for better answers.'}
          <span className="sr">{changed}</span>
        </p>
        {turns.length === 0 && !busy && <StarterTiles key={pack ?? 'all'} items={starters} label={pack ? `Approved questions: ${packs.find((p) => p.id === pack)?.title ?? pack}` : 'Approved questions'} onPick={send} />}
        <Uploads compact={turns.length > 0} workspaceId={pack} onAsk={(q, id, n) => send(q, id, n)} onSignedOut={() => expired()} />
        {turns.map((t, i) => <Answer key={i} a={t.answer} question={t.question} onFollow={send} onDetails={() => { setDetailIdx(i); if (!paneOpen) togglePane() }} active={paneOpen && detailIdx === i} wf={defs.length ? { defs, canStart: grants.canStart, me: user, onSignedOut: () => expired(), onChange: refreshWaiting } : undefined} />)}
        {busy && asking && (
          <article className="answer pending" aria-label="Question being answered"><h2 className="q">{asking}</h2>
            {early && early.rows.length > 0 && (
              <>
                <p className="muted small" role="status">The rows are ready; the written answer is still being prepared.</p>
                <div className="tablewrap"><table><thead><tr>{early.columns.map((c) => <th key={c}>{c}</th>)}</tr></thead>
                  <tbody>{early.rows.slice(0, 20).map((r, i) => <tr key={i}>{r.map((v, j) => <td key={j}>{v ?? ''}</td>)}</tr>)}</tbody></table></div>
                {early.rows.length > 20 && <p className="muted small">First 20 of {early.rows.length} rows.</p>}
              </>)}
          </article>)}
        {busy && !paneOpen && (
          <div className="progress" role="status" aria-live="polite">
            <span>Working on it… <Elapsed since={startedAt} /></span> <button onClick={() => abort.current?.abort()}>Cancel</button> <button className="link" onClick={togglePane}>Show progress</button>
          </div>
        )}
        {err && <p role="alert" className="error">{err}{retry && !busy && <> <button className="link" onClick={() => send(retry)}>Try again</button></>}</p>}
        <div ref={bottom} />
        {file && <p className="small filechip" role="status">Asking about <strong>{file.name}</strong> (a table you uploaded; only you see it). <button className="link" onClick={() => setFile(null)}>Stop using it</button></p>}
        <form className="askbar" onSubmit={(e) => { e.preventDefault(); send(q) }}>
          <label className="sr" htmlFor="q">Ask a question</label>
          <input id="q" value={q} onChange={(e) => setQ(e.target.value)} placeholder={pack ? `Ask about ${packs.find((p) => p.id === pack)?.title ?? pack}` : 'Ask about any of your data'} maxLength={4000} disabled={busy} />
          <button className="primary" disabled={busy || !q.trim()}>Ask</button>
        </form>
        </>}
      </main>
      {tourOpen && user && <Tour user={user} go={go} switchTo={switchTo} docked={wide} min={tourMin} onMin={setTourMin} onFocus={setTourFocus} onClose={() => { setTourOpen(false); setTourMin(false); setTourFocus([]) }} />}
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



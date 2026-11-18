import { useState } from 'react'
import { api, ApiError, type Answer as A } from './api'

const CATEGORIES: [string, string][] = [['WRONG_VALUE', 'A number is wrong'], ['WRONG_DEFINITION', 'It means something else'], ['MISSING_SOURCE', 'Data is missing'], ['OTHER', 'Something else']]
type Panel = null | 'down' | 'help'

/** What the Server already has for the people who improve answers: a vote (a thumbs-down opens a review case for the analyst), a plain request to an admin, and "save as a reusable question" (an admin approves it before anyone is served it). */
export default function Feedback({ a, question, onSignedOut }: { a: A; question: string; onSignedOut?: () => void }) {
  const [vote, setVote] = useState<'UP' | 'DOWN' | null>(null)
  const [panel, setPanel] = useState<Panel>(null)
  const [category, setCategory] = useState('')
  const [note, setNote] = useState('')
  const [help, setHelp] = useState('')
  const [msg, setMsg] = useState('')
  const [busy, setBusy] = useState(false)
  const [saved, setSaved] = useState(false)
  const canVote = !!a.queryId
  const canSave = !!a.sql && !!a.queryId && a.evidence?.origin !== 'question_bank'

  async function run(f: () => Promise<string>) {
    setBusy(true); setMsg('')
    try { setMsg(await f()) }
    catch (e) { if (e instanceof ApiError && e.status === 401) onSignedOut?.(); else setMsg((e as Error).message) }
    finally { setBusy(false) }
  }
  const send = (v: 'UP' | 'DOWN') => run(async () => {
    await api.feedback({ queryId: a.queryId!, vote: v, question, answer: a.answer.slice(0, 8000), ...(v === 'DOWN' ? { category: category || undefined, note: note.trim() || undefined } : {}) })
    setVote(v); setPanel(null)
    return v === 'UP' ? 'Thanks. This helps the analyst see what works.' : 'Thanks. An analyst will look at this answer.'
  })

  return (
    <div className="fb small">
      <div className="fbrow">
        {canVote && <>
          <button className="link" aria-pressed={vote === 'UP'} disabled={busy} onClick={() => send('UP')}>Helpful</button>
          <button className="link" aria-pressed={vote === 'DOWN'} aria-expanded={panel === 'down'} disabled={busy} onClick={() => setPanel(panel === 'down' ? null : 'down')}>Not right</button>
        </>}
        {canSave && <button className="link" disabled={busy || saved} onClick={() => run(async () => { const r = await api.saveReusable(question, a.sql!); setSaved(true); return r.alreadySaved ? 'This question was already saved. An admin reviews it before anyone is served it.' : 'Saved for review. An admin approves it before anyone is served it.' })}>{saved ? 'Saved for review' : 'Save as a reusable question'}</button>}
        <button className="link" aria-expanded={panel === 'help'} onClick={() => setPanel(panel === 'help' ? null : 'help')}>Ask an admin for help</button>
      </div>
      {panel === 'down' && (
        <div className="fbpanel" role="group" aria-label="What was wrong">
          <div className="follow">{CATEGORIES.map(([id, label]) => <button key={id} className="chip" aria-pressed={category === id} onClick={() => setCategory(category === id ? '' : id)}>{label}</button>)}</div>
          <label>What should it have said? (optional)<textarea value={note} maxLength={2000} rows={2} onChange={(e) => setNote(e.target.value)} /></label>
          <button disabled={busy} onClick={() => send('DOWN')}>Send</button> <button className="link" onClick={() => setPanel(null)}>Cancel</button>
        </div>)}
      {panel === 'help' && (
        <div className="fbpanel" role="group" aria-label="Ask an admin for help">
          <label>What do you need? The admin sees who you are and this message.<textarea value={help} maxLength={2000} rows={3} onChange={(e) => setHelp(e.target.value)} placeholder="For example: I need last quarter's data, which this answer does not have." /></label>
          <button disabled={busy || !help.trim()} onClick={() => run(async () => { await api.askAdmin(`${help.trim()}\n\n(About the question: ${question})`.slice(0, 2000)); setHelp(''); setPanel(null); return 'Sent. An admin will see it under Help requests.' })}>Send to an admin</button> <button className="link" onClick={() => setPanel(null)}>Cancel</button>
        </div>)}
      {msg && <p role="status" className="muted">{msg}</p>}
    </div>
  )
}

import { useState } from 'react'
import { api } from './api'

export default function Login({ onDone }: { onDone: () => void }) {
  const [u, setU] = useState(''); const [p, setP] = useState(''); const [err, setErr] = useState(''); const [busy, setBusy] = useState(false)
  async function submit(e: React.FormEvent) {
    e.preventDefault(); setBusy(true); setErr('')
    try { await api.login(u, p); onDone() } catch (x) { setErr((x as Error).message) } finally { setBusy(false) }
  }
  return (
    <main className="login">
      <form onSubmit={submit} aria-labelledby="login-h">
        <h1 id="login-h">Agency</h1>
        <p className="muted">Sign in with your OmniGate account. Agency keeps no passwords.</p>
        <label>Username<input value={u} onChange={(e) => setU(e.target.value)} autoComplete="username" autoFocus required /></label>
        <label>Password<input type="password" value={p} onChange={(e) => setP(e.target.value)} autoComplete="current-password" required /></label>
        {err && <p role="alert" className="error">{err}</p>}
        <button className="primary" disabled={busy}>{busy ? 'Signing in…' : 'Sign in'}</button>
      </form>
    </main>
  )
}

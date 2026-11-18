import { useEffect, useState } from 'react'
import { api } from './api'

export default function Login({ onDone }: { onDone: () => void }) {
  const [u, setU] = useState(''); const [p, setP] = useState(''); const [err, setErr] = useState(''); const [busy, setBusy] = useState(false)
  const [sso, setSso] = useState<{ enabled: boolean; label?: string }>({ enabled: false })
  const why = new URLSearchParams(window.location.search).get('sso')
  const note = why === 'unknown' ? 'Your identity provider signed you in, but there is no OmniGate account for you. Ask an administrator.' : why ? 'Single sign-on did not complete. Try again.' : ''
  useEffect(() => { api.ssoConfig().then(setSso).catch(() => {}) }, [])
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
        {(err || note) && <p role="alert" className="error">{err || note}</p>}
        <button className="primary" disabled={busy}>{busy ? 'Signing in…' : 'Sign in'}</button>
        {sso.enabled && <p className="sso"><a className="button" href="/sso/login">Continue with {sso.label}</a></p>}
      </form>
    </main>
  )
}

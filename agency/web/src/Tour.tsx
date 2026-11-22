import { useEffect, useRef, useState } from 'react'
import { api, ApiError } from './api'
import type { View } from './shell'
import { PERSONAS, STEPS, stepLabel, type StepState, type TourStep } from './tourScript'

const sleep = (ms: number) => new Promise<void>((r) => setTimeout(r, ms))

/** Waits for an element that matches `sel`; when `enabled`, also for it not to be disabled. Resolves null on timeout or when the tour is stopped. */
async function waitFor(sel: string, ms: number, stop: () => boolean, enabled: boolean, refresh?: string): Promise<Element | null> {
  const end = Date.now() + ms; let last = Date.now()
  while (Date.now() < end && !stop()) {
    const el = document.querySelector(sel)
    if (el && (!enabled || !(el as HTMLButtonElement).disabled)) return el
    if (refresh && Date.now() - last > 5000) { last = Date.now(); (document.querySelector(refresh) as HTMLElement | null)?.click() }
    await sleep(250)
  }
  return null
}

/**
 * The guided click-through (tourScript.ts). Local demo sandbox only: the layer offers it when AGENCY_DEMO_TOUR=on. It signs in as the demo person for each step and presses the same buttons a person would,
 * so what the audience sees is the real product on the real Server. It adds no data path of its own.
 */
export default function Tour({ user, go, switchTo, docked, min, onMin, onClose }: { user: string; go: (v: View) => void; switchTo: (persona: string) => Promise<void>; docked: boolean; min: boolean; onMin: (m: boolean) => void; onClose: () => void }) {
  const [idx, setIdx] = useState(-1)                                   // -1 = the start page
  const [states, setStates] = useState<StepState[]>(() => STEPS.map(() => 'todo'))
  const [note, setNote] = useState('')
  const [busy, setBusy] = useState(false)
  const [auto, setAuto] = useState(false)
  const [paused, setPaused] = useState<{ i: number } | null>(null)      // play-all stops here after a failed step until the person chooses
  const [skipped, setSkipped] = useState(0)
  const choice = useRef<((c: 'retry' | 'skip' | 'stop') => void) | null>(null)
  const [pre, setPre] = useState<{ ok: boolean; text: string; fatal?: boolean }[] | null>(null)
  const stopped = useRef(false)
  const userRef = useRef(user); userRef.current = user
  useEffect(() => () => { stopped.current = true }, [])

  useEffect(() => {
    Promise.all([api.status().catch(() => null), api.tourInfo().catch(() => null), api.workflowRun('rca-1').then((r) => r.run ?? null).catch((e) => (e instanceof ApiError && (e.status === 404 || e.code === 'unknown_run') ? null : undefined))]).then(([st, info, run]) => {
      const need = ['alice', 'bob', 'carol', 'curator']
      setPre([
        { ok: !!st?.server.reachable, fatal: true, text: st?.server.reachable ? 'The Server is reachable.' : 'The Server is not reachable. Start the sandbox (agency/local/up.sh).' },
        { ok: !!st?.workflows?.available, fatal: true, text: st?.workflows?.available ? 'Workflows are available (commercial edition, engine on).' : 'Workflows are off, so most steps cannot run. Start the sandbox with the workflow gateway.' },
        { ok: !!info && need.every((n) => info.personas.includes(n)), fatal: true, text: info && need.every((n) => info.personas.includes(n)) ? 'The four demo people can be signed in.' : 'The demo people are not all set up (AGENCY_DEMO_PERSONAS needs curator, alice, bob and carol).' },
        { ok: run === null, text: run === null ? 'The first run id is free.' : 'A run from an earlier rehearsal exists (rca-1). Reset first with agency/local/reset-demo.sh, or steps that send a run will be skipped.' },
      ])
    })
  }, [])
  const setState = (i: number, s: StepState) => setStates((x) => x.map((v, j) => (j === i ? s : v)))

  async function perform(i: number): Promise<StepState> {
    const step: TourStep = STEPS[i]
    setIdx(i); setBusy(true); setNote(''); setState(i, 'doing')
    try {
      if (userRef.current !== step.persona) setNote(`Signing in as ${step.persona}…`)
      await switchTo(step.persona)                         // the app compares with who is signed in now and does nothing when it is already this person
      go(step.view); await sleep(500)
      for (const a of step.actions) {
        if (stopped.current) { setState(i, 'todo'); return 'todo' }
        if (!a.click) {                                     // a screen that loads by itself: wait for it, so the audience sees the content
          if (a.until) { setNote(`${a.label}…`); if (!(await waitFor(a.until, a.waitMs ?? 60000, () => stopped.current, false))) { setNote(stopped.current ? 'Stopped.' : `"${a.label}" did not load in time.`); setState(i, stopped.current ? 'todo' : 'failed'); return stopped.current ? 'todo' : 'failed' } }
          continue
        }
        if (a.skipIf && document.querySelector(a.skipIf)) continue
        setNote(`${a.label}…`)
        const el = await waitFor(a.click, a.findMs ?? 45000, () => stopped.current, true, a.refresh)
        if (!el) { if (stopped.current) { setState(i, 'todo'); return 'todo' } setNote(`Nothing to press for "${a.label}": it was probably already done in this sandbox.`); setState(i, 'skipped'); return 'skipped' }
        el.scrollIntoView({ block: 'center', behavior: 'smooth' }); el.setAttribute('data-tour-hl', '1'); await sleep(900)
        ;(el as HTMLElement).click(); await sleep(400); el.removeAttribute('data-tour-hl')
        if (a.until) {
          setNote(`${a.label}: waiting for the result…`)
          const got = await waitFor(a.until, a.waitMs ?? 60000, () => stopped.current, false)
          if (!got) { setNote(stopped.current ? 'Stopped.' : `"${a.label}" did not finish in time. The screen may still be working; press Next when it has.`); setState(i, stopped.current ? 'todo' : 'failed'); return stopped.current ? 'todo' : 'failed' }
          got.scrollIntoView({ block: 'center', behavior: 'smooth' })
        }
        if (a.settleMs) await sleep(a.settleMs)
      }
      setNote(''); setState(i, 'done'); return 'done'
    } catch (e) { setNote((e as Error).message || 'That step failed.'); setState(i, 'failed'); return 'failed' }
    finally { setBusy(false) }
  }

  async function play(from: number) {
    stopped.current = false; setAuto(true); setSkipped(0)
    for (let i = from; i < STEPS.length && !stopped.current; i++) {
      let r = await perform(i)
      while (r === 'failed' && !stopped.current) {         // a failed step stops the play: later steps would run on a broken state
        setPaused({ i }); const c = await new Promise<'retry' | 'skip' | 'stop'>((res) => { choice.current = res }); setPaused(null)
        if (c === 'stop') { stopped.current = true; setNote('Stopped after a failed step.'); break }
        if (c === 'skip') { setSkipped((n) => n + 1); break }
        r = await perform(i)
      }
      if (r === 'skipped') setSkipped((n) => n + 1)
      if (!stopped.current && i < STEPS.length - 1) await sleep(STEPS[i].actions.some((a) => a.click) ? 4500 : 12000)
    }
    setAuto(false)
  }
  const stop = () => { stopped.current = true; setAuto(false); setBusy(false); setNote('Stopped.'); choice.current?.('stop'); setPaused(null) }
  const manual = async (i: number) => { stopped.current = false; await perform(i) }
  const step = idx >= 0 ? STEPS[idx] : null
  const finished = idx === STEPS.length - 1 && states[idx] !== 'todo' && states[idx] !== 'doing'

  if (min) return <aside className="tour mini" aria-label="Guided tour"><button className="primary" onClick={() => onMin(false)}>Tour{step ? `: ${stepLabel(idx)}` : ''}</button></aside>
  return (
    <aside className={'tour' + (docked ? ' docked' : '')} aria-label="Guided tour">
      <div className="tour-top"><strong>Guided tour</strong><span><button className="link" onClick={() => onMin(true)}>Minimise</button> <button className="link" onClick={() => { stop(); onClose() }}>Close</button></span></div>
      {!step && <>
        <p>A click-through of the whole demo: the tour signs in as each demo person, opens the screen and presses the real buttons. The answers come from the real Server, so a step can take up to a minute when the model is busy.</p>
        <p className="small muted">Seven acts: watch, problem record, exposure, priorities, register, notifications, audit. Each run can only be started once per sandbox; reset it between rehearsals.</p>
        {pre ? <ul className="plain small" aria-label="Checks before the tour">{pre.map((c) => <li key={c.text} className={c.ok ? '' : 'error'}><span aria-hidden>{c.ok ? '✓' : '!'}</span> {c.text}</li>)}</ul> : <p className="muted small">Checking the sandbox…</p>}
        <div className="actions"><button className="primary" disabled={busy || !pre || pre.some((c) => c.fatal && !c.ok)} onClick={() => play(0)}>Play the whole demo</button> <button disabled={busy || !pre || pre.some((c) => c.fatal && !c.ok)} onClick={() => manual(0)}>Step by step</button></div>
      </>}
      {step && <>
        <p className="small muted">{step.act} · {stepLabel(idx)}</p>
        <h3>{step.title}</h3>
        <p className="small">Signed in as <strong>{user}</strong>{user !== step.persona ? <> (this step: <strong>{step.persona}</strong>)</> : null}. <span className="muted">{PERSONAS[step.persona]}</span></p>
        <p><strong>Say:</strong> {step.say}</p>
        <p className="muted"><strong>Look at:</strong> {step.look}</p>
        {note && <p role="status" aria-live="polite" className={'small' + (states[idx] === 'failed' ? ' error' : '')}>{note}</p>}
        <p className="small"><span className={'tstate ' + states[idx]}>{{ todo: 'Not run', doing: 'Running…', done: 'Done', skipped: 'Skipped', failed: 'Needs a look' }[states[idx]]}</span></p>
        <div className="actions">
          <button disabled={busy || idx === 0} onClick={() => { stopped.current = false; void manual(idx - 1) }}>Back</button>
          <button className="primary" disabled={busy} onClick={() => manual(idx)}>{states[idx] === 'todo' ? 'Run this step' : 'Run it again'}</button>
          <button disabled={busy || idx >= STEPS.length - 1} onClick={() => manual(idx + 1)}>Next</button>
          {!auto && <button disabled={busy || finished} onClick={() => play(Math.min(STEPS.length - 1, states[idx] === 'done' || states[idx] === 'skipped' ? idx + 1 : idx))}>Play from here</button>}
          {(auto || busy) && <button onClick={stop}>Stop</button>}
        </div>
        {paused && <div role="alert" className="error small"><p><strong>Play paused: this step needs a look.</strong> Later steps depend on it.</p>
          <div className="actions"><button className="primary" onClick={() => choice.current?.('retry')}>Retry this step</button> <button onClick={() => choice.current?.('skip')}>Skip it and go on</button> <button onClick={() => choice.current?.('stop')}>Stop</button></div></div>}
        <details><summary className="small">All steps</summary>
          <ol className="small tsteps">{STEPS.map((s, i) => <li key={s.id} className={i === idx ? 'now' : ''}><button className="link" disabled={busy} onClick={() => manual(i)}>{s.title}</button> <span className={'tstate ' + states[i]}>{states[i] === 'todo' ? '' : states[i]}</span></li>)}</ol>
        </details>
        {finished && <p className="small"><strong>That is the whole demo.</strong>{skipped > 0 ? ` ${skipped} step${skipped === 1 ? ' was' : 's were'} skipped.` : ''} Reset the sandbox before a rehearsal: agency/local/reset-demo.sh.</p>}
      </>}
    </aside>
  )
}

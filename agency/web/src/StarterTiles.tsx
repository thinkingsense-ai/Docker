import { useState } from 'react'
import type { Starter } from './api'

export const TOP = 5

/** The questions to show first: approved before suggested (the Server's own order inside each group), at most `limit` unless the person asks for all. */
export function pickStarters(items: Starter[], showAll: boolean, limit = TOP): { shown: Starter[]; total: number; approved: number } {
  const ordered = [...items.filter((s) => s.origin === 'approved'), ...items.filter((s) => s.origin !== 'approved')]
  return { shown: showAll ? ordered : ordered.slice(0, limit), total: ordered.length, approved: items.filter((s) => s.origin === 'approved').length }
}

interface Props { items: Starter[]; label: string; onPick: (q: string) => void }

/** Approved questions as tiles: the first five, with the rest one click away. */
export default function StarterTiles({ items, label, onPick }: Props) {
  const [all, setAll] = useState(false)
  const { shown, total, approved } = pickStarters(items, all)
  return (
    <section aria-label="Approved questions" className="tiles-section">
      <div className="tiles-head">
        <h2>{label}</h2>
        {total > TOP && <button className="link" aria-expanded={all} onClick={() => setAll(!all)}>{all ? `Show the first ${TOP}` : `Show all ${total}`}</button>}
      </div>
      {total === 0
        ? <p className="muted">No approved questions for this choice yet. Ask your own below.</p>
        : <ul className="tiles">{shown.map((s) => (
            <li key={s.question}>
              <button className="tile" onClick={() => onPick(s.question)}>
                <span className="tile-q">{s.question}</span>
                <span className={'tag ' + s.origin}>{s.origin === 'approved' ? 'approved' : 'suggested'}</span>
              </button>
            </li>))}</ul>}
      {total > 0 && !all && total > TOP && <p className="muted small">{approved} approved questions in all; the first {TOP} are shown.</p>}
    </section>
  )
}

import { useMemo, useState } from 'react'
import Chart from './Chart'
import { describePlan, planChart, statTiles, type Kind } from './chartModel'
import { Table } from './Answer'
import { formatCell } from './format'
import type { Definition } from './workflow'

type Start = { column: number; def: Definition }
interface Props { question?: string; columns: string[]; rows: (string | null)[][]; starts?: Start[]; onStart?: (def: Definition, key: string) => void }
const KIND: Record<Kind, string> = { bar: 'Bars', line: 'Line', donut: 'Donut' }

/** A result as a chart when its shape supports one, always with the table one click away (and first, when rows carry actions such as starting a workflow). */
export default function ResultView({ question, columns, rows, starts = [], onStart }: Props) {
  const [kind, setKind] = useState<Kind | undefined>()
  const [measures, setMeasures] = useState<string[] | undefined>()
  const plan = useMemo(() => planChart(columns, rows, { kind, measures, question }), [columns, rows, kind, measures, question])
  const stats = useMemo(() => statTiles(columns, rows), [columns, rows])
  const [view, setView] = useState<'chart' | 'table' | null>(null)
  const current = view ?? (plan && starts.length === 0 ? 'chart' : 'table')
  if (stats && view !== 'table') return (
    <div>
      <div className="stats">{stats.map((s) => <div key={s.label} className="stat"><div className="stat-v">{formatCell(s.value)}</div><div className="stat-l">{s.label.replace(/_/g, ' ')}</div></div>)}</div>
      <p className="small"><button className="link" onClick={() => setView('table')}>Show as a table</button></p>
    </div>
  )
  if (!plan) return <Table columns={columns} rows={rows} starts={starts} onStart={onStart} />
  return (
    <div className="rv">
      <div className="rv-bar">
        <div className="seg" role="group" aria-label="Show the result as">
          <button aria-pressed={current === 'chart'} onClick={() => setView('chart')}>Chart</button>
          <button aria-pressed={current === 'table'} onClick={() => setView('table')}>Table</button>
        </div>
        {current === 'chart' && plan.options.length > 1 && (
          <div className="seg" role="group" aria-label="Chart type">{plan.options.map((o) => <button key={o} aria-pressed={plan.kind === o} onClick={() => setKind(o)}>{KIND[o]}</button>)}</div>)}
        {current === 'chart' && plan.candidates.length > 1 && plan.kind !== 'donut' && (
          <div className="seg" role="group" aria-label="Measures to plot">
            {plan.candidates.map((c) => <button key={c} aria-pressed={plan.measures.some((m) => m.name === c)} onClick={() => {
              const now = plan.measures.map((m) => m.name); const next = now.includes(c) ? now.filter((x) => x !== c) : [...now, c]; setMeasures(next.length ? next : now)
            }}>{c.replace(/_/g, ' ')}</button>)}
          </div>)}
      </div>
      {current === 'chart'
        ? <><Chart plan={plan} /><p className="muted small">{plan.note ? plan.note + ' ' : ''}{describePlan(plan, columns)}</p></>
        : <Table columns={columns} rows={rows} starts={starts} onStart={onStart} />}
    </div>
  )
}

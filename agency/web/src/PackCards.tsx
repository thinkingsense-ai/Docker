import type { Pack } from './api'
import { badges } from './format'

interface Props { packs: Pack[]; selected: string | null; onSelect: (id: string | null) => void; compact?: boolean }

export default function PackCards({ packs, selected, onSelect, compact }: Props) {
  return (
    <section aria-label="Choose a domain">
      <div className={'cards' + (compact ? ' compact' : '')} role="radiogroup" aria-label="Domain">
        <button role="radio" aria-checked={selected === null} className={'card' + (selected === null ? ' on' : '')} onClick={() => onSelect(null)}>
          <strong>All data</strong>
          <span className="muted">Every source this Server can reach.</span>
          <span className="warn">Accuracy across all packs was not measured; choose a domain when you can.</span>
        </button>
        {packs.map((p) => {
          const off = p.loaded === false
          return (
            <button key={p.id} role="radio" aria-checked={selected === p.id} aria-disabled={off} disabled={off}
                    className={'card' + (selected === p.id ? ' on' : '') + (off ? ' off' : '')} onClick={() => onSelect(p.id)}>
              <strong>{p.title}</strong>
              <span>{p.summary}</span>
              <span className="muted">
                {p.questions.approved} approved questions · {p.sources.length} source{p.sources.length === 1 ? '' : 's'}{p.tables ? ` · ${p.tables} tables` : ''}
              </span>
              <span className="tags">{badges(p).map((b) => <span key={b} className={'tag' + (b.startsWith('non-commercial') ? ' caution' : '')}>{b}</span>)}</span>
              <span className={'state ' + (p.loaded === true ? 'ok' : p.loaded === false ? 'bad' : '')}>
                {p.loaded === true ? 'Loaded' : p.loaded === false ? `Not loaded: ${p.loadedReason ?? 'no data for it on this Server'}` : 'Load state unknown on this Server'}
              </span>
            </button>
          )
        })}
      </div>
    </section>
  )
}

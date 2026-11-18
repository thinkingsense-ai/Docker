import type { Pack } from './api'
import { badges } from './format'

export function loadedText(l: Pack['loaded']): string {
  if (l === 'workspace') return 'Loaded: has its own Workspace'
  if (l === 'category') return 'Approved questions loaded, no Workspace of its own'
  return 'Load state unknown on this Server'
}

interface Props { packs: Pack[]; selected: string | null; onSelect: (id: string | null) => void; compact?: boolean }

/** The domain choice. `compact` is a single row of chips; otherwise full cards with what each domain holds. */
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
          const off = false                                  // the layer has no definite "not loaded" signal today, so no card is disabled
          return (
            <button key={p.id} role="radio" aria-checked={selected === p.id} aria-disabled={off} disabled={off}
                    className={'card' + (selected === p.id ? ' on' : '') + (off ? ' off' : '')} onClick={() => onSelect(p.id)}>
              <strong>{p.title}</strong>
              <span>{p.summary}</span>
              <span className="muted">
                {p.questions.approved} approved questions · {p.sources.length} source{p.sources.length === 1 ? '' : 's'}{p.tables ? ` · ${p.tables} tables` : ''}
              </span>
              <span className="tags">{badges(p).map((b) => <span key={b} className={'tag' + (b.startsWith('non-commercial') ? ' caution' : '')}>{b}</span>)}</span>
              <span className={'state ' + (p.loaded === 'workspace' ? 'ok' : '')} title={p.loadedReason ?? undefined}>{loadedText(p.loaded)}</span>
            </button>
          )
        })}
      </div>
    </section>
  )
}

import type { View } from './shell'

// The two screens whose build step has not landed. Each says plainly what it will do and what to use meanwhile; none shows invented data.
const COPY: Partial<Record<View, { title: string; will: string; step: string; meanwhile: string }>> = {
  exposure: {
    title: 'Exposure',
    will: 'Five questions over a simulated estate (databases, Slack, SharePoint, object store) that show how a similar incident would reach our own systems, with one rating from Low to Critical and the rule behind it.',
    step: 'Build steps 3 and 4 (estate data, then the rating).',
    meanwhile: 'The estate is simulated: there is no real firm system to read.',
  },
  sources: {
    title: 'Sources',
    will: 'The feeds Watch reads, each with its kind (reporting, official or context), when it last answered and how many items it gave. Health only: no article text is stored.',
    step: 'Build step 6 (the feed adapter).',
    meanwhile: 'The candidate feeds and their checks are in section 5.2 of the design note.',
  },
}

export default function Screen({ view }: { view: View }) {
  const c = COPY[view]
  if (!c) return null
  return (
    <section className="screen" aria-labelledby="screen-h">
      <h2 id="screen-h">{c.title}</h2>
      <p className="notbuilt" role="status"><strong>Not built yet.</strong> {c.step}</p>
      <p>{c.will}</p>
      <p className="muted">{c.meanwhile}</p>
    </section>
  )
}

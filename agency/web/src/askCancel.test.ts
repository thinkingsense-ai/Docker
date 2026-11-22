import { afterEach, describe, expect, it, vi } from 'vitest'
import { ask } from './api'

// A fake /ask stream that sends the given frames and then stays open, like a question the Server is still working on.
function openStream(frames: object[]) {
  let ctl!: ReadableStreamDefaultController<Uint8Array>
  const enc = new TextEncoder()
  const body = new ReadableStream<Uint8Array>({ start(c) { ctl = c } })
  return { body, send: () => frames.forEach((f) => ctl.enqueue(enc.encode(`data: ${JSON.stringify(f)}\n\n`))) }
}
const calls: { url: string; init?: RequestInit }[] = []
function mockFetch(stream: ReturnType<typeof openStream>) {
  calls.length = 0
  vi.stubGlobal('fetch', vi.fn(async (url: string, init?: RequestInit) => {
    calls.push({ url, init })
    if (url === '/ask') return new Response(stream.body, { status: 200 })
    return new Response(JSON.stringify({ success: true, cancelled: true }), { status: 200 })
  }))
}
const tick = () => new Promise((r) => setTimeout(r, 20))
afterEach(() => vi.unstubAllGlobals())

describe('Cancel', () => {
  it('tells the Server to stop the question when the caller aborts, using the queryId from the first event', async () => {
    const s = openStream([{ step: 'understanding', queryId: 'q-1234-5678', conversationId: 'c1' }]); mockFetch(s)
    const ac = new AbortController(); let first = false
    void ask('Which suppliers?', 'it-risk', null, () => { first = true }, ac.signal).catch(() => {})
    s.send(); await tick(); expect(first).toBe(true)
    ac.abort(); await tick()
    const cancel = calls.find((c) => c.url === '/cancel')
    expect(cancel).toBeDefined(); expect(cancel!.init?.method).toBe('POST'); expect(JSON.parse(String(cancel!.init?.body))).toEqual({ queryId: 'q-1234-5678' })
    expect((cancel!.init?.headers as Record<string, string>)['X-Requested-With']).toBe('agency')
  })
  it('cancels once even if abort() is called twice', async () => {
    const s = openStream([{ step: 'understanding', queryId: 'q-aaaa-bbbb' }]); mockFetch(s); const ac = new AbortController()
    void ask('x', null, null, () => {}, ac.signal).catch(() => {}); s.send(); await tick(); ac.abort(); ac.abort(); await tick()
    expect(calls.filter((c) => c.url === '/cancel').length).toBe(1)
  })
  it('does not call cancel when nothing was aborted, or when no event (so no id) had arrived yet', async () => {
    const s = openStream([]); mockFetch(s); const ac = new AbortController()
    void ask('x', null, null, () => {}, ac.signal).catch(() => {}); await tick(); ac.abort(); await tick()
    expect(calls.some((c) => c.url === '/cancel')).toBe(false)           // honest limit: an abort before the first event has no query id to cancel
    const s2 = openStream([{ step: 'understanding', queryId: 'q-cccc-dddd' }]); mockFetch(s2)
    void ask('y', null, null, () => {}, new AbortController().signal).catch(() => {}); s2.send(); await tick()
    expect(calls.some((c) => c.url === '/cancel')).toBe(false)
  })
})

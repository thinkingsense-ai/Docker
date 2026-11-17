// Calls to the thinking layer (same origin). The layer holds the Server's session; the browser only has the layer's cookie.
export interface Source { id: string; schemas: string[] }
export interface Pack {
  id: string; title: string; summary: string; sources: Source[]; tables: number | null
  questions: { approved: number; crossSource: number }; modalities: string[]; needsEmbeddingModel: boolean
  capabilities: string[]; editions: string[]; licence: { data?: string; nonCommercial?: boolean }
  loaded: 'workspace' | 'category' | null; loadedReason?: string | null   // the layer's wording: a Workspace exists, only approved questions exist, or unknown
}
export interface Evidence {
  workspace: string; pack: string | null; scopeEnforcedBy: 'server-backends' | 'agency-hint' | 'none'
  sources: { id: string }[]; intendedSources: Source[] | null; origin: string | null; sql: string | null; model: string | null
  checks: { id: string; status: string }[]; answeredWithoutDataSources: boolean; elapsedMs: number; warnings: string[]
}
export interface Starter { question: string; origin: 'approved' | 'suggested' }
export interface ConversationSummary { id: string; title: string; updatedAtMillis: number }
export interface Turn { question: string; answer: string; sql?: string; columns: string[]; rows: (string | null)[][] }
export interface Answer {
  answer: string; columns: string[]; rows: (string | null)[][]; sql: string | null; conversationId: string | null
  suggestedQuestions?: string[]; truncated?: boolean; evidence: Evidence | null
}
export interface Status {
  layer: { version: string }; server: { reachable: boolean; llmConfigured?: boolean }
  workflows?: { available: boolean; note: string }; decisions: { readable: boolean }; scopeHint: boolean
}

export interface Adapter { id: string; title: string; kind?: string; enabled: boolean; reason?: string; nonCommercial?: boolean; licence?: string; notes?: string; maxBytes?: number; accepts: { extensions: string[]; mime: string[] } }
export interface Upload {
  id: string; name: string; kind: string; adapter: string; workspaceId: string | null; nonCommercial: boolean; licence: string | null
  notes: string[]; askPrompts: string[]; result: Record<string, any> | null; expiresAt: number
}

export class ApiError extends Error {
  constructor(public status: number, public code: string, message: string) { super(message) }
}

async function call<T>(method: string, path: string, body?: unknown): Promise<T> {
  const res = await fetch(path, {
    method, credentials: 'same-origin',
    headers: { 'Content-Type': 'application/json', 'X-Requested-With': 'agency' },   // the layer refuses a cookie-carrying POST without it
    body: body === undefined ? undefined : JSON.stringify(body),
  })
  let data: any = {}
  try { data = await res.json() } catch { /* non-JSON error body */ }
  if (!res.ok) throw new ApiError(res.status, data?.error?.code ?? 'error', data?.error?.message ?? `Request failed (HTTP ${res.status}).`)
  return data as T
}

export const api = {
  login: (username: string, password: string) => call<{ username: string }>('POST', '/login', { username, password }),
  logout: () => call<unknown>('POST', '/logout', {}),
  whoami: () => call<Record<string, any>>('GET', '/whoami'),
  packs: () => call<{ packs: Pack[]; note: string | null }>('GET', '/packs'),
  status: () => call<Status>('GET', '/status'),
  starters: (pack: string | null) => call<{ items?: Starter[]; questions?: string[] }>('GET', '/starters' + (pack ? '?pack=' + encodeURIComponent(pack) : '')),
  conversations: () => call<{ conversations: ConversationSummary[] }>('GET', '/conversations'),
  conversation: (id: string) => call<{ success: boolean; title?: string; turns?: Turn[]; error?: string }>('GET', '/conversations/get?id=' + encodeURIComponent(id)),
  preferences: () => call<{ pack?: string }>('GET', '/preferences'),
  adapters: () => call<{ adapters: Adapter[]; accept: string[] }>('GET', '/adapters'),
  uploads: () => call<{ uploads: Upload[] }>('GET', '/uploads'),
  deleteUpload: (id: string) => call<unknown>('DELETE', '/uploads/' + encodeURIComponent(id)),
  setPreference: (pack: string | null) => call<{ pack?: string }>('POST', '/preferences', { pack }),
}

export interface ProgressEvent { step: string; [k: string]: any }

/** Streams POST /ask. onEvent gets each Server event as the layer relays it; resolves with the final answer, rejects on error or abort. */
export async function ask(question: string, workspaceId: string | null, conversationId: string | null,
                          onEvent: (e: ProgressEvent) => void, signal: AbortSignal): Promise<Answer> {
  const res = await fetch('/ask', {
    method: 'POST', credentials: 'same-origin', signal,
    headers: { 'Content-Type': 'application/json', Accept: 'text/event-stream', 'X-Requested-With': 'agency' },
    body: JSON.stringify({ question, workspaceId, conversationId }),
  })
  if (!res.ok || !res.body) {
    let data: any = {}
    try { data = await res.json() } catch { /* ignore */ }
    throw new ApiError(res.status, data?.error?.code ?? 'error', data?.error?.message ?? `Request failed (HTTP ${res.status}).`)
  }
  const reader = res.body.getReader(); const dec = new TextDecoder(); let buf = ''
  let evidence: Evidence | null = null; let final: ProgressEvent | null = null
  const handle = (frame: string) => {
    for (const line of frame.split('\n')) {
      if (!line.startsWith('data: ')) continue
      let e: ProgressEvent
      try { e = JSON.parse(line.slice(6)) } catch { continue }
      if (e.step === 'evidence') { evidence = e.evidence; continue }
      onEvent(e)
      if (['done', 'error', 'stopped', 'approval_needed'].includes(e.step)) final = e
    }
  }
  for (;;) {
    const { value, done } = await reader.read()
    if (value) buf += dec.decode(value, { stream: true })
    let i: number
    while ((i = buf.indexOf('\n\n')) >= 0) { handle(buf.slice(0, i)); buf = buf.slice(i + 2) }
    if (done) break
  }
  if (buf) handle(buf)
  const f = final as ProgressEvent | null
  if (!f) throw new ApiError(502, 'no_answer', 'The Server ended the stream without an answer.')
  if (f.step === 'error') throw new ApiError(200, 'server_error', String(f.error ?? f.message ?? 'The Server could not answer.'))
  if (f.step !== 'done') throw new ApiError(200, f.step, f.step === 'approval_needed' ? 'This question needs an approval before it can run.' : 'The question was stopped.')
  return { answer: f.answer ?? '', columns: f.columns ?? [], rows: f.rows ?? [], sql: f.sql ?? null, conversationId: f.conversationId ?? null,
           suggestedQuestions: f.suggestedQuestions, truncated: f.truncated, evidence }
}

export async function uploadFile(file: File, workspaceId: string | null): Promise<Upload> {
  const q = 'name=' + encodeURIComponent(file.name) + (workspaceId ? '&workspaceId=' + encodeURIComponent(workspaceId) : '')
  const res = await fetch('/uploads?' + q, { method: 'POST', credentials: 'same-origin', headers: { 'Content-Type': file.type || 'application/octet-stream', 'X-Requested-With': 'agency' }, body: file })
  let data: any = {}
  try { data = await res.json() } catch { /* non-JSON */ }
  if (!res.ok) throw new ApiError(res.status, data?.error?.code ?? 'error', data?.error?.message ?? `Upload failed (HTTP ${res.status}).`)
  return data as Upload
}

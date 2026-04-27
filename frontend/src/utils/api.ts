export const API = {
  HEALTH: '/api/health',
  CHAT: '/api/chat',
  CHAT_SESSIONS: '/api/chat/sessions',
  CHAT_SESSION: (id: string) => `/api/chat/sessions/${id}`,
  CHAT_SESSION_MESSAGES: (id: string) => `/api/chat/sessions/${id}/messages`,
  DOCUMENTS: '/api/documents',
  DOCUMENTS_UPLOAD: '/api/documents/upload',
  DOCUMENT: (id: string) => `/api/documents/${id}`,
  SETTINGS_MODELS: '/api/settings/models',
  SETTINGS_MODEL: '/api/settings/model',
  SETTINGS_PROVIDER: '/api/settings/provider',
} as const

export async function apiFetch<T = unknown>(
  path: string,
  options?: RequestInit,
): Promise<T> {
  const resp = await fetch(path, options)
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({}))
    throw new Error((err as any).detail || `HTTP ${resp.status}`)
  }
  return resp.json() as Promise<T>
}

export function apiPost<T = unknown>(path: string, body: unknown): Promise<T> {
  return apiFetch<T>(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
}

export function apiPatch<T = unknown>(path: string, body: unknown): Promise<T> {
  return apiFetch<T>(path, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
}

export function apiDelete<T = unknown>(path: string): Promise<T> {
  return apiFetch<T>(path, { method: 'DELETE' })
}

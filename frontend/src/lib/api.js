import { getUserId } from './userId'

// Dev:  vazio -> usa o proxy do Vite ('/api' -> http://127.0.0.1:8000)
// Prod: definido em frontend/.env.production (VITE_API_BASE_URL)
export const API_BASE = (import.meta.env.VITE_API_BASE_URL ?? '').replace(/\/$/, '')

/** Monta a URL absoluta da API. Use também para <video src>, fetch direto, etc. */
export const apiUrl = (path) => `${API_BASE}${path}`

/** Rota escopada ao usuário atual: userPath('/projects/current') -> /api/users/<id>/projects/current */
export const userPath = (path) => `/api/users/${getUserId()}${path}`

/** Erro de API com status HTTP e a mensagem `detail` devolvida pelo backend. */
export class ApiError extends Error {
  constructor(message, status, detail) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.detail = detail
  }
}

async function toApiError(method, path, res) {
  const txt = await res.text()
  let detail = ''
  try {
    const parsed = JSON.parse(txt)
    if (typeof parsed?.detail === 'string') detail = parsed.detail
  } catch { /* corpo não-JSON */ }
  return new ApiError(`${method} ${path} failed: ${res.status} ${txt}`, res.status, detail)
}

export async function apiGet(path) {
  const res = await fetch(apiUrl(path))
  if (!res.ok) throw await toApiError('GET', path, res)
  return res.json()
}

export async function apiPost(path, body) {
  const res = await fetch(apiUrl(path), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!res.ok) throw await toApiError('POST', path, res)
  return res.json()
}

/**
 * POST multipart/form-data com um File/Blob no campo "file".
 * Usado pelo useVideoPreprocess para enviar o vídeo ao backend Python.
 */
export async function apiPostFile(path, file, filename) {
  const form = new FormData()
  form.append('file', file, filename ?? 'video.mp4')

  const res = await fetch(apiUrl(path), { method: 'POST', body: form })
  if (!res.ok) throw await toApiError('POST', path, res)
  return res.json()
}

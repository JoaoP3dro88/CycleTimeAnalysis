// Dev:  vazio -> usa o proxy do Vite ('/api' -> http://127.0.0.1:8000)
// Prod: definido em frontend/.env.production (VITE_API_BASE_URL)
export const API_BASE = (import.meta.env.VITE_API_BASE_URL ?? '').replace(/\/$/, '')

/** Monta a URL absoluta da API. Use também para <video src>, fetch direto, etc. */
export const apiUrl = (path) => `${API_BASE}${path}`

export async function apiGet(path) {
  const res = await fetch(apiUrl(path))
  if (!res.ok) throw new Error(`GET ${path} failed: ${res.status}`)
  return res.json()
}

export async function apiPost(path, body) {
  const res = await fetch(apiUrl(path), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })

  if (!res.ok) {
    const txt = await res.text()
    throw new Error(`POST ${path} failed: ${res.status} ${txt}`)
  }

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

  if (!res.ok) {
    const txt = await res.text()
    throw new Error(`POST ${path} failed: ${res.status} ${txt}`)
  }

  return res.json()
}
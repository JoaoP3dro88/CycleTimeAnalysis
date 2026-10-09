/**
 * Identificação do usuário (workspace).
 *
 * Cada navegador recebe um ID aleatório (UUID) guardado no localStorage.
 * Todos os dados no servidor (projeto + vídeos) ficam isolados por esse ID.
 * Para continuar de outro PC/navegador, use "Usar outro ID" em Config.
 *
 * Não há senha: o ID funciona como chave de acesso (adequado a rede interna).
 */
const KEY = 'cta_user_id'

// Mesma regra do backend (backend/services/user_service.py)
const VALID = /^[A-Za-z0-9][A-Za-z0-9_-]{3,63}$/
export const isValidUserId = (id) => VALID.test(id ?? '')

function generate() {
  if (globalThis.crypto?.randomUUID) return crypto.randomUUID()
  const bytes = crypto.getRandomValues(new Uint8Array(16))
  return Array.from(bytes, (b) => b.toString(16).padStart(2, '0')).join('')
}

let memoryId = null // fallback se o localStorage estiver bloqueado

export function getUserId() {
  try {
    const saved = localStorage.getItem(KEY)
    if (saved && isValidUserId(saved)) return saved.toLowerCase()
    const fresh = generate()
    localStorage.setItem(KEY, fresh)
    return fresh
  } catch {
    return (memoryId ??= generate())
  }
}

export function setUserId(id) {
  if (!isValidUserId(id)) {
    throw new Error('ID inválido: use 4 a 64 letras, números, "-" ou "_".')
  }
  const normalized = id.toLowerCase()
  try { localStorage.setItem(KEY, normalized) } catch { memoryId = normalized }
}

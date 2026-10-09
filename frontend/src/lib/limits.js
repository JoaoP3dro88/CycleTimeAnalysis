/** Limite de duração do vídeo (segundos). Padrão: 10 min (igual ao backend). */
export const MAX_VIDEO_SECONDS = Number(import.meta.env.VITE_MAX_VIDEO_SECONDS ?? 600)

export function tooLongMessage(durationS) {
  const limitMin = MAX_VIDEO_SECONDS / 60
  const shown = durationS ? ` (o vídeo tem ${(durationS / 60).toFixed(1)} min)` : ''
  return `O vídeo excede o limite de ${limitMin} minutos${shown}.\nCorte o vídeo e tente novamente.`
}

/**
 * Lê só os metadados do arquivo e devolve a duração em segundos,
 * ou null se o navegador não conseguir ler (aí o backend valida).
 */
export function getVideoDuration(file) {
  return new Promise((resolve) => {
    const url = URL.createObjectURL(file)
    const v = document.createElement('video')
    let finished = false
    const done = (d) => {
      if (finished) return
      finished = true
      URL.revokeObjectURL(url)
      v.removeAttribute('src')
      resolve(d)
    }
    v.preload = 'metadata'
    v.onloadedmetadata = () => done(Number.isFinite(v.duration) ? v.duration : null)
    v.onerror = () => done(null)
    setTimeout(() => done(null), 10000)
    v.src = url
  })
}

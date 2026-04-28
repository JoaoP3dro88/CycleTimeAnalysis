/**
 * useVideoPreprocess.js
 *
 * Envia o vídeo para o backend Python (POST /api/preprocess) que roda
 * mp.solutions.hands em todos os frames e devolve o JSON de landmarks.
 *
 * O cache resultante tem o mesmo formato esperado pelo VideoAnalyzer:
 *   Map<frameIndex, { landmarks, handedness } | null>
 *   cache._realFps  → fps real do vídeo (reportado pelo backend)
 *
 * O "src" recebido é uma blob: URL criada pelo App quando o usuário
 * carrega o vídeo.  Convertemos de volta para Blob via fetch para
 * poder enviar como multipart ao backend.
 */
import { useEffect, useRef, useState, useCallback } from 'react'
import { apiPostFile } from './api'

/**
 * @param {{ src: string, fps: number }} opts
 * @returns {{ cacheRef, status, progress, cancel }}
 *   status: 'idle' | 'uploading' | 'processing' | 'done' | 'error' | 'cancelled'
 */
export function useVideoPreprocess({ src, fps }) {
  const cacheRef  = useRef(new Map())
  const cancelRef = useRef(false)

  const [status,   setStatus]   = useState('idle')
  const [progress, setProgress] = useState(0)

  const cancel = useCallback(() => { cancelRef.current = true }, [])

  useEffect(() => {
    if (!src) {
      cacheRef.current = new Map()
      setStatus('idle')
      setProgress(0)
      return
    }

    // Cancel any in-flight request
    cancelRef.current = true

    const t = setTimeout(async () => {
      cancelRef.current = false
      cacheRef.current  = new Map()
      setStatus('uploading')
      setProgress(0)

      try {
        // 1. Converter blob: URL → Blob real
        console.log('[preprocess] 1/4 — convertendo blob URL para Blob...')
        const blobResp = await fetch(src)
        const blob     = await blobResp.blob()
        console.log(`[preprocess] 1/4 — Blob pronto: ${(blob.size / 1024 / 1024).toFixed(1)} MB`)

        if (cancelRef.current) { setStatus('cancelled'); return }

        setStatus('processing')

        // 2. Enviar ao backend — resposta pode demorar (vídeo inteiro)
        //    Enquanto aguarda mostramos uma barra indeterminada (fake loading)
        console.log('[preprocess] 2/4 — enviando vídeo ao backend (POST /api/preprocess)...')
        const fakeTimer = startFakeProgress(setProgress)

        const t0   = performance.now()
        const data = await apiPostFile('/api/preprocess', blob, 'video.mp4')
        const secs = ((performance.now() - t0) / 1000).toFixed(1)

        clearInterval(fakeTimer)
        console.log(`[preprocess] 2/4 — resposta recebida em ${secs}s`)

        if (cancelRef.current) { setStatus('cancelled'); return }

        // 3. Popular o cache com o resultado
        //    Backend devolve:  { fps, total_frames, frames: { "0": null|{landmarks,handedness}, ... } }
        const realFps    = data.fps ?? fps
        const totalFrames = data.total_frames ?? 0
        console.log(`[preprocess] 3/4 — processando ${totalFrames} frames a ${realFps} fps...`)
        const cache   = new Map()

        for (const [key, val] of Object.entries(data.frames ?? {})) {
          const frameIndex = parseInt(key, 10)
          if (val === null) {
            cache.set(frameIndex, null)
          } else {
            // Converter arrays [[x,y,z],...] → objetos {x,y,z} que o VideoAnalyzer espera
            cache.set(frameIndex, {
              landmarks:  val.landmarks.map(hand =>
                hand.map(([x, y, z]) => ({ x, y, z }))
              ),
              handedness: val.handedness.map(([label, score]) => [{ categoryName: label, score }]),
            })
          }
        }

        cache._realFps = realFps
        cacheRef.current = cache

        const framesWithHands = [...cache.values()].filter(v => v !== null).length
        console.log(`[preprocess] 4/4 — cache pronto: ${cache.size} frames, ${framesWithHands} com mãos detectadas`)

        setProgress(1)
        setStatus('done')

      } catch (err) {
        if (cancelRef.current) { setStatus('cancelled'); return }
        console.error('[preprocess] ERRO:', err)
        // Extrair a mensagem de detalhe do backend se disponível
        const detail = err.message ?? String(err)
        console.error('[preprocess] Detalhe completo:', detail)
        setStatus('error')
      }
    }, 100)

    return () => {
      clearTimeout(t)
      cancelRef.current = true
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [src])

  return { cacheRef, status, progress, cancel }
}

// ── Fake progress enquanto o backend processa ─────────────────────────────────
// Sobe de 0 → 0.99 assintoticamente. Nunca chega a 100% — isso só acontece
// quando o backend responde (setProgress(1) + setStatus('done')).
function startFakeProgress(setProgress) {
  let elapsed = 0
  return setInterval(() => {
    elapsed += 0.5
    // Curva assintótica: 1 - e^(-elapsed/60)  →  chega a ~0.63 em 60s, ~0.86 em 120s
    const frac = Math.min(0.99, 1 - Math.exp(-elapsed / 60))
    setProgress(frac)
  }, 500)
}

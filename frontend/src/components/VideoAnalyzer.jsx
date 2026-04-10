/**
 * VideoAnalyzer.jsx
 *
 * Overlay sobre o vídeo. A cada frame entregue pelo browser via
 * requestVideoFrameCallback (rVFC), lê os landmarks do cache
 * (pré-processado por useVideoPreprocess) e os desenha no canvas.
 *
 * ALINHAMENTO CACHE ↔ PLAYBACK
 * ─────────────────────────────
 * O useVideoPreprocess gravou o frame N usando timestamp = N/fps segundos
 * (seek exato). Durante a reprodução, o rVFC entrega metadata.mediaTime,
 * que é o tempo real do vídeo. Para mapear para o índice do cache usamos:
 *
 *   frameIndex = Math.round(mediaTime * fps)
 *
 * Isso é exatamente o que o legado Python faz:
 *   current_frame_num = int(self.cap.get(cv2.CAP_PROP_POS_FRAMES))
 *   cache.get_detection(current_frame_num)
 *
 * IMPORTANTE: DrawingUtils é instanciado UMA vez (ref), não por frame.
 */
import { useEffect, useRef, useState, useCallback, forwardRef, useImperativeHandle } from 'react'
import { Pencil, Trash2 } from 'lucide-react'
import { DrawingUtils, HandLandmarker } from '@mediapipe/tasks-vision'
import RoiOverlay from './RoiOverlay'
import { RoiTracker, detectRoi } from '../lib/roiTracker'

const ROI_COLORS = ['#00ff00', '#ff00ff', '#00ffff', '#ffff00', '#ff4444', '#ff8800', '#016d1cff', '#4631ffff', '#ff4bc3ff']

// INDEX_FINGER_TIP = landmark 8, igual ao legado Python
function getProbe(landmarks) {
  const tip = landmarks[8]
  return { x: tip.x, y: tip.y }
}

function isValidHand(landmarks) {
  if (!landmarks || landmarks.length < 21) return false
  const xs = landmarks.map((l) => l.x)
  const ys = landmarks.map((l) => l.y)
  const w = Math.max(...xs) - Math.min(...xs)
  const h = Math.max(...ys) - Math.min(...ys)
  return Math.sqrt(w * w + h * h) >= 0.04
}

export default forwardRef(function VideoAnalyzer(
  { videoRef, src, fps = 30, onCreateEvent, preprocessCache, preprocessStatus, initialRois, onRoisChange, loopRange, events = [] },
  ref,
) {
  const canvasRef       = useRef(null)
  const drawUtilsRef    = useRef(null)   // DrawingUtils — instanciado uma vez
  const trackerRef      = useRef(new RoiTracker())
  const rvfcHandleRef   = useRef(null)
  const lastFrameRef    = useRef(-1)     // último frameIndex processado (evita duplicatas)
  const maxEndFrameRef  = useRef({ Left: -1, Right: -1 })
  const processedFramesRef = useRef({})

  const [rois, setRois]               = useState(() => initialRois ?? [])
  const [drawingMode, setDrawingMode] = useState(false)
  const [activeRois, setActiveRois]   = useState({ Left: null, Right: null })

  const roisRef          = useRef(rois)
  const fpsRef           = useRef(fps)
  const onCreateEventRef = useRef(onCreateEvent)
  const onRoisChangeRef  = useRef(onRoisChange)

  useEffect(() => { roisRef.current         = rois },          [rois])
  useEffect(() => { fpsRef.current          = fps },           [fps])
  useEffect(() => { onCreateEventRef.current = onCreateEvent }, [onCreateEvent])
  useEffect(() => { onRoisChangeRef.current  = onRoisChange },  [onRoisChange])

  // Quando o pai injeta ROIs novas (abrir projeto JSON)
  const initialRoisKey = JSON.stringify(initialRois)
  useEffect(() => {
    if (initialRois && initialRois.length > 0) {
      setRois(initialRois)
      trackerRef.current.reset()
      setActiveRois({ Left: null, Right: null })
    }
  }, [initialRoisKey]) // eslint-disable-line react-hooks/exhaustive-deps

  useImperativeHandle(ref, () => ({ getRois: () => roisRef.current }), [])

  // ── Inicializar DrawingUtils quando o canvas estiver pronto ──────────────
  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const ctx = canvas.getContext('2d')
    drawUtilsRef.current = new DrawingUtils(ctx)
  }, []) // uma única vez

  // ── Loop principal — requestVideoFrameCallback ────────────────────────────
  //
  // Estratégia:
  //   1. rVFC é chamado imediatamente ANTES de o frame ser composto na tela,
  //      então metadata.mediaTime é o tempo EXATO do frame que vai aparecer.
  //   2. Calculamos frameIndex = round(mediaTime * fps) — mesmo que o legado.
  //   3. Lemos cache.get(frameIndex) — O(1), zero overhead.
  //   4. Desenhamos landmarks e passamos pro RoiTracker.
  //   5. Re-registramos rVFC no FIM do tick para o PRÓXIMO frame.
  //
  useEffect(() => {
    const video = videoRef?.current
    if (!video || preprocessStatus !== 'done') return

    let stopped = false

    // Garantir que canvas e DrawingUtils estão prontos
    const canvas = canvasRef.current
    if (!canvas) return
    const ctx = canvas.getContext('2d')
    if (!drawUtilsRef.current) {
      drawUtilsRef.current = new DrawingUtils(ctx)
    }

    function tick(_now, metadata) {
      if (stopped) return

      // mediaTime é o tempo do frame que ESTÁ sendo apresentado agora
      const mediaTime  = metadata?.mediaTime ?? video.currentTime
      // Usar o fps real gravado pelo preprocess — mesmo divisor usado ao gravar
      const cache      = preprocessCache?.current ?? null
      const realFps    = (cache && cache._realFps) ? cache._realFps : fpsRef.current
      const frameIndex = Math.round(mediaTime * realFps)

      // Evitar reprocessar o mesmo frame (rVFC pode disparar duplicatas em pausa)
      if (frameIndex === lastFrameRef.current) {
        rvfcHandleRef.current = video.requestVideoFrameCallback(tick)
        return
      }
      lastFrameRef.current = frameIndex

      // ── Redimensionar canvas se necessário ──────────────────────────────
      const vw = video.videoWidth  || 640
      const vh = video.videoHeight || 480
      if (canvas.width !== vw || canvas.height !== vh) {
        canvas.width  = vw
        canvas.height = vh
        // DrawingUtils precisa ser recriado após resize do canvas
        drawUtilsRef.current = new DrawingUtils(ctx)
      }
      ctx.clearRect(0, 0, vw, vh)

      // ── Ler do cache — O(1), sem MediaPipe em tempo real ────────────────
      const cached = cache ? (cache.get(frameIndex) ?? null) : null

      // ── Desenhar landmarks ───────────────────────────────────────────────
      const handsDetected = {}
      if (cached && cached.landmarks && cached.handedness) {
        const du = drawUtilsRef.current
        for (let i = 0; i < cached.landmarks.length; i++) {
          const lm = cached.landmarks[i]
          if (!isValidHand(lm)) continue

          // Legado: 'Left' MediaPipe = mão direita real (câmera espelhada)
          const rawLabel  = cached.handedness[i]?.[0]?.categoryName ?? 'Left'
          const realLabel = rawLabel === 'Left' ? 'Right' : 'Left'
          const probe     = getProbe(lm)
          const roiIdx    = detectRoi(probe.x, probe.y, roisRef.current)
          handsDetected[realLabel] = roiIdx ?? null

          try {
            du.drawConnectors(lm, HandLandmarker.HAND_CONNECTIONS, { color: '#00FF00', lineWidth: 2 })
            du.drawLandmarks(lm,  { color: '#FF0000', lineWidth: 1, radius: 4 })
          } catch (_) { /* ignora erros de desenho em frames corrompidos */ }
        }
      }

      setActiveRois({ Left: handsDetected.Left ?? null, Right: handsDetected.Right ?? null })

      // ── RoiTracker — mesmo algoritmo de confirmação do legado ────────────
      const videoTimeMs  = mediaTime * 1000
      const currentRois  = roisRef.current
      const newEvents    = trackerRef.current.processFrame(handsDetected, currentRois, videoTimeMs, frameIndex)

      for (const ev of newEvents) {
        if (ev.type !== 'EXIT') continue
        const roi = currentRois[ev.roiIndex]
        if (!roi) continue

        const startFrame = ev.entryFrame ?? Math.max(0, frameIndex - Math.round(ev.duration * fpsRef.current))
        const endFrame   = ev.lostFrame  ?? frameIndex

        // Nova checagem: não criar evento se já existe evento sobreposto para mesma mão/ROI
        // Checagem robusta: não criar evento se TODO o intervalo já está coberto
        const handLabel = ev.hand === 'Left' ? 'Mão Esquerda' : 'Mão Direita'
        const key = handLabel + '|' + roi.name
        if (!processedFramesRef.current[key]) processedFramesRef.current[key] = new Set()
        let alreadyProcessed = true
        for (let f = startFrame; f < endFrame; ++f) {
          if (!processedFramesRef.current[key].has(f)) {
            alreadyProcessed = false
            break
          }
        }
        if (alreadyProcessed) continue
        // Marca todos os frames do novo evento como processados
        for (let f = startFrame; f < endFrame; ++f) {
          processedFramesRef.current[key].add(f)
        }

        const dur      = fpsRef.current > 0 ? (endFrame - startFrame) / fpsRef.current : ev.duration
        const category = ev.hand === 'Left' ? (roi.leftCategory ?? '') : (roi.rightCategory ?? '')

        onCreateEventRef.current?.({
          operation:   roi.name,
          start_frame: startFrame,
          end_frame:   Math.max(startFrame + 1, endFrame),
          duration:    Number(dur.toFixed(6)),
          category,
          object:      handLabel,
          resource:    roi.name,
        })
      }

      // Registrar próximo frame
      // Bloquear criação de eventos automáticos se loopRange?.active
      if (loopRange?.active) {
        rvfcHandleRef.current = video.requestVideoFrameCallback(tick)
        return
      }

      rvfcHandleRef.current = video.requestVideoFrameCallback(tick)
    }

    // ── Detectar seek: resetar tracker quando o tempo pula ──────────────────
    let lastSeekTime = -1
    function onSeeked() {
      trackerRef.current.reset()
      maxEndFrameRef.current = { Left: -1, Right: -1 }
      lastFrameRef.current   = -1
      setActiveRois({ Left: null, Right: null })
      lastSeekTime = video.currentTime
    }
    video.addEventListener('seeked', onSeeked)

    // Iniciar loop
    if (typeof video.requestVideoFrameCallback === 'function') {
      rvfcHandleRef.current = video.requestVideoFrameCallback(tick)
    } else {
      // Fallback RAF para Safari
      let rafId
      let lastRafTime = -1
      const rafTick = () => {
        if (stopped) return
        rafId = requestAnimationFrame(rafTick)
        const t = video.currentTime
        if (t === lastRafTime || video.readyState < 2) return
        lastRafTime = t
        tick(performance.now(), { mediaTime: t })
      }
      rafId = requestAnimationFrame(rafTick)
      rvfcHandleRef.current = { _isRaf: true, _rafId: rafId }
    }

    return () => {
      stopped = true
      video.removeEventListener('seeked', onSeeked)
      const h = rvfcHandleRef.current
      if (h) {
        if (h._isRaf) {
          cancelAnimationFrame(h._rafId)
        } else if (typeof video.cancelVideoFrameCallback === 'function') {
          video.cancelVideoFrameCallback(h)
        }
        rvfcHandleRef.current = null
      }
      ctx.clearRect(0, 0, canvas.width, canvas.height)
      setActiveRois({ Left: null, Right: null })
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [preprocessStatus, src, videoRef])

  // Resetar ao trocar de vídeo
  useEffect(() => {
    trackerRef.current.reset()
    maxEndFrameRef.current = { Left: -1, Right: -1 }
    lastFrameRef.current   = -1
    setActiveRois({ Left: null, Right: null })
  }, [src])

  const handleRoisChange = useCallback((nextRois) => {
    setRois(nextRois)
    trackerRef.current.reset()
    setActiveRois({ Left: null, Right: null })
    setDrawingMode(false)
    onRoisChangeRef.current?.(nextRois)
  }, [])

  // ── Render ────────────────────────────────────────────────────────────────
  return (
    <div style={{ position: 'absolute', inset: 0, pointerEvents: 'none' }}>

      <canvas
        ref={canvasRef}
        style={{
          position: 'absolute', inset: 0,
          width: '100%', height: '100%',
          objectFit: 'contain',
          pointerEvents: 'none',
        }}
      />

      <div style={{ position: 'absolute', inset: 0, pointerEvents: drawingMode ? 'auto' : 'none' }}>
        <RoiOverlay
          rois={rois}
          activeRois={activeRois}
          drawingMode={drawingMode}
          onRoisChange={handleRoisChange}
          mirror={false}
          videoRef={videoRef}
        />
      </div>

      <div
        style={{
          position: 'absolute', top: '0.5rem', left: '0.5rem',
          display: 'flex', gap: '0.4rem', alignItems: 'center', flexWrap: 'wrap',
          pointerEvents: 'auto', zIndex: 10,
        }}
      >
        <button
          onClick={() => setDrawingMode((v) => !v)}
          style={{
            padding: '0.3rem 0.6rem', borderRadius: '0.4rem',
            border: drawingMode ? '1px solid #1a4a1a' : '1px solid #444',
            background: drawingMode ? 'rgba(13,46,13,0.9)' : 'rgba(0,0,0,0.75)',
            color: '#fff', cursor: 'pointer', fontSize: '0.75rem',
            display: 'flex', alignItems: 'center', gap: '0.3rem',
          }}
        >
          <Pencil size={13} strokeWidth={2} />
          {drawingMode ? 'Desenhando…' : 'ROI'}
        </button>

        {rois.length > 0 && (
          <button
            onClick={() => {
              setRois([])
              trackerRef.current.reset()
              setActiveRois({ Left: null, Right: null })
              onRoisChangeRef.current?.([])
            }}
            style={{
              padding: '0.3rem 0.6rem', borderRadius: '0.4rem',
              border: '1px solid #4b1d1d', background: 'rgba(42,18,18,0.85)',
              color: '#fff', cursor: 'pointer', fontSize: '0.75rem',
              display: 'flex', alignItems: 'center', gap: '0.3rem',
            }}
          >
            <Trash2 size={13} strokeWidth={2} />
          </button>
        )}

        {rois.map((roi, i) => (
          <span
            key={i}
            title={`Esq: ${roi.leftCategory || '—'} | Dir: ${roi.rightCategory || '—'}`}
            style={{
              padding: '0.2rem 0.45rem', borderRadius: '0.35rem', fontSize: '0.7rem',
              border: `1px solid ${ROI_COLORS[i % ROI_COLORS.length]}`,
              color: ROI_COLORS[i % ROI_COLORS.length],
              background: 'rgba(0,0,0,0.75)', cursor: 'default', whiteSpace: 'nowrap',
            }}
          >
            {roi.name}
            {activeRois.Left  === i && ' ✋'}
            {activeRois.Right === i && ' 🤚'}
          </span>
        ))}
      </div>
    </div>
  )
})
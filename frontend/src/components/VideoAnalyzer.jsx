/**
 * VideoAnalyzer.jsx
 *
 * Pure overlay: renders as position:absolute inset:0 over the video element.
 * Contains:
 *   - A <canvas> for landmark drawing (inset:0, pointer-events:none)
 *   - RoiOverlay SVG (inset:0)
 *   - A floating toolbar pinned to top-left (pointer-events:auto)
 *
 * Props:
 *   videoRef        React ref — the SAME <video> element used by VideoPlayer
 *   src             string    — current video src
 *   fps             number    — project FPS (used for frame counting)
 *   onCreateEvent   fn(event) — called on every ROI EXIT
 *   preprocessCache React ref (Map<frameN, {landmarks,handedness}|null>)
 *                   — when provided, landmark detection reads from cache
 *                     instead of running the neural network in real-time.
 *                     Falls back to live detection if the frame is not cached.
 *
 * Imperative handle (ref forwarded from App via forwardRef):
 *   { landmarkerRef }  — gives the parent access to the loaded HandLandmarker
 *                        instance so useVideoPreprocess can reuse it.
 */
import { useEffect, useRef, useState, useCallback, forwardRef, useImperativeHandle } from 'react'
import { Loader, Activity, Play, Pencil, Trash2, Zap, Radio, AlertTriangle } from 'lucide-react'
import { HandLandmarker, FilesetResolver, DrawingUtils } from '@mediapipe/tasks-vision'
import RoiOverlay from './RoiOverlay'
import { RoiTracker, detectRoi } from '../lib/roiTracker'

const ROI_COLORS = ['#00ff00', '#ff00ff', '#00ffff', '#ffff00', '#ff4444', '#ff8800', '#016d1cff', '#4631ffff', '#ff4bc3ff']

// ── Geometric filter (same as CameraView) ───────────────────────────────────
function isValidHand(landmarks) {
  if (!landmarks || landmarks.length < 21) return false
  const xs = landmarks.map((l) => l.x)
  const ys = landmarks.map((l) => l.y)
  const w = Math.max(...xs) - Math.min(...xs)
  const h = Math.max(...ys) - Math.min(...ys)
  return Math.sqrt(w * w + h * h) >= 0.04
}

// Probe: centroid of index finger chain (5=MCP, 6=PIP, 7=DIP, 8=tip)
function getProbe(landmarks) {
  const chain = [landmarks[5], landmarks[6], landmarks[7], landmarks[8]]
  return {
    x: chain.reduce((s, l) => s + l.x, 0) / chain.length,
    y: chain.reduce((s, l) => s + l.y, 0) / chain.length,
  }
}

export default forwardRef(function VideoAnalyzer(
  { videoRef, src, fps = 30, onCreateEvent, preprocessCache, initialRois, onRoisChange },
  ref,
) {
  const canvasRef = useRef(null)
  const landmarkerRef = useRef(null)
  const rafRef = useRef(null)
  const trackerRef = useRef(new RoiTracker())
  const loadingRef = useRef(false)
  // Highest end_frame already emitted per hand — prevents duplicate events
  // when the user seeks backward and reprocesses an already-seen range.
  const maxEndFrameRef = useRef({ Left: -1, Right: -1 })

  const [modelReady, setModelReady] = useState(false)
  const [modelError, setModelError] = useState(null)
  const [active, setActive] = useState(false)
  const [rois, setRois] = useState(() => initialRois ?? [])
  const [drawingMode, setDrawingMode] = useState(false)
  const [activeRois, setActiveRois] = useState({ Left: null, Right: null })
  // Derived from videoRef directly — no prop needed
  const [videoReady, setVideoReady] = useState(false)
  // 'cache' | 'live' | null — source of the last landmark detection
  const [detectionSource, setDetectionSource] = useState(null)
  // Accumulated hit counters (updated via ref to avoid per-frame re-renders;
  // flushed to state every ~30 frames so the badge stays current).
  const detectStatsRef = useRef({ cache: 0, live: 0, flushAt: 30 })
  const [detectStats, setDetectStats] = useState({ cache: 0, live: 0 })

  const roisRef = useRef(rois)
  useEffect(() => { roisRef.current = rois }, [rois])

  // When the parent passes a new initialRois array (e.g. after JSON import),
  // seed the internal state. Using a stable JSON key avoids infinite loops.
  const initialRoisKey = JSON.stringify(initialRois)
  useEffect(() => {
    if (initialRois && initialRois.length > 0) {
      setRois(initialRois)
      trackerRef.current.reset()
      setActiveRois({ Left: null, Right: null })
    }
  }, [initialRoisKey]) // eslint-disable-line react-hooks/exhaustive-deps

  const fpsRef = useRef(fps)
  useEffect(() => { fpsRef.current = fps }, [fps])

  const onCreateEventRef = useRef(onCreateEvent)
  useEffect(() => { onCreateEventRef.current = onCreateEvent }, [onCreateEvent])

  const activeRef = useRef(active)
  useEffect(() => { activeRef.current = active }, [active])

  // Keep a stable ref to the cache prop so the tick loop always reads the
  // latest Map without triggering re-renders or stale closures.
  // Because preprocessCache is already a ref (stable object), we just point
  // our own ref at its .current on every render.
  const preprocessCachePropRef = useRef(null)
  preprocessCachePropRef.current = preprocessCache ?? null

  // Expose landmarkerRef + getRois so App can read ROIs for export
  useImperativeHandle(ref, () => ({ landmarkerRef, getRois: () => roisRef.current }), [])

  // ── Track video readiness directly from the element ──────────────────────
  useEffect(() => {
    const video = videoRef?.current
    if (!video) return
    const onReady = () => setVideoReady(video.readyState >= 2 && isFinite(video.duration))
    const onEmpty = () => setVideoReady(false)
    video.addEventListener('canplay', onReady)
    video.addEventListener('loadeddata', onReady)
    video.addEventListener('emptied', onEmpty)
    // Check immediately in case video is already loaded
    onReady()
    return () => {
      video.removeEventListener('canplay', onReady)
      video.removeEventListener('loadeddata', onReady)
      video.removeEventListener('emptied', onEmpty)
    }
  }, [videoRef, src])

  // ── Load model once ──────────────────────────────────────────────────────
  useEffect(() => {
    if (loadingRef.current || landmarkerRef.current) return
    loadingRef.current = true

    ;(async () => {
      try {
        const vision = await FilesetResolver.forVisionTasks('/mediapipe-wasm')
        landmarkerRef.current = await HandLandmarker.createFromOptions(vision, {
          baseOptions: {
            modelAssetPath:
              'https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/latest/hand_landmarker.task',
            delegate: 'GPU',
          },
          runningMode: 'VIDEO',
          numHands: 2,
          minHandDetectionConfidence: 0.6,
          minHandPresenceConfidence: 0.5,
          minTrackingConfidence: 0.4,
        })
        setModelReady(true)
      } catch (e) {
        setModelError(`Erro ao carregar modelo: ${e.message ?? e}`)
      } finally {
        loadingRef.current = false
      }
    })()

    return () => {
      stopLoop()
      landmarkerRef.current?.close?.()
      landmarkerRef.current = null
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // ── Detection loop ───────────────────────────────────────────────────────
  function startLoop() {
    const video = videoRef?.current
    const canvas = canvasRef.current
    if (!video || !canvas || !landmarkerRef.current) return

    const ctx = canvas.getContext('2d')
    const drawingUtils = new DrawingUtils(ctx)
    let lastVideoTime = -1
    // Wall-clock time of last processFrame call (for paused grace-period ticking)
    let lastWallMs = performance.now()

    function tick() {
      rafRef.current = requestAnimationFrame(tick)

      if (!activeRef.current) return
      if (video.readyState < 2) return

      // ── Match canvas resolution to the VIDEO's intrinsic size.
      const vw = video.videoWidth || 640
      const vh = video.videoHeight || 480
      if (canvas.width !== vw || canvas.height !== vh) {
        canvas.width = vw
        canvas.height = vh
      }

      const nowWall = performance.now()
      const videoTime = video.currentTime

      // ── Detect seek / loop (time jumped backward) → reset tracker ────────
      if (videoTime < lastVideoTime - 0.05) {
        trackerRef.current.reset()
        setActiveRois({ Left: null, Right: null })
        lastVideoTime = videoTime
        lastWallMs = nowWall
        return
      }

      // ── Decide whether to run detection this tick ─────────────────────────
      // Always run when the video has advanced to a new frame (playing).
      // Also run every ~100 ms wall-clock even when paused, so that
      // the grace period can expire if the hand leaves while paused.
      const frameAdvanced = videoTime !== lastVideoTime
      const pausedTimeout = !frameAdvanced && (nowWall - lastWallMs) >= 100

      if (!frameAdvanced && !pausedTimeout) return

      const prevWallMs = lastWallMs
      lastVideoTime = videoTime
      lastWallMs = nowWall

      const videoTimeMs = videoTime * 1000  // ms in video time

      // ── Landmark detection — cache-first, then live ───────────────────────
      // If the video was pre-processed, read from the cache (O(1), no GPU).
      // Fall back to live MediaPipe when the frame is not cached yet.
      const cache = preprocessCachePropRef.current?.current ?? null
      const currentFrame = Math.round(videoTime * fpsRef.current)
      let results
      let fromCache = false

      if (cache && cache.has(currentFrame)) {
        // Use pre-computed result (may be null = no hands on this frame)
        const cached = cache.get(currentFrame)
        results = cached ?? { landmarks: [], handedness: [] }
        fromCache = true
      } else {
        // Live detection (no cache or frame not yet processed)
        // detectForVideo requires a strictly-increasing timestamp — performance.now()
        // is always monotonic, regardless of whether the video is paused.
        results = landmarkerRef.current.detectForVideo(video, performance.now())
      }

      // ── Update detection-source stats (throttled to avoid re-render storm) ─
      const stats = detectStatsRef.current
      if (fromCache) { stats.cache++ } else { stats.live++ }
      stats.flushAt--
      if (stats.flushAt <= 0) {
        setDetectionSource(fromCache ? 'cache' : 'live')
        setDetectStats({ cache: stats.cache, live: stats.live })
        stats.flushAt = 30
      }

      ctx.clearRect(0, 0, canvas.width, canvas.height)

      const validLandmarks = (results.landmarks ?? []).filter(isValidHand)
      const validHandedness = (results.handedness ?? []).filter(
        (_, i) => isValidHand(results.landmarks?.[i])
      )

      for (const landmarks of validLandmarks) {
        drawingUtils.drawConnectors(landmarks, HandLandmarker.HAND_CONNECTIONS, {
          color: '#00FF00', lineWidth: 2,
        })
        drawingUtils.drawLandmarks(landmarks, { color: '#FF0000', lineWidth: 1, radius: 4 })
      }

      const handsDetected = {}
      const currentRois = roisRef.current

      for (let i = 0; i < validLandmarks.length; i++) {
        const rawLabel = validHandedness[i]?.[0]?.categoryName ?? 'Left'
        const userLabel = rawLabel  // video is not mirrored
        const probe = getProbe(validLandmarks[i])
        const roiIdx = detectRoi(probe.x, probe.y, currentRois)
        handsDetected[userLabel] = roiIdx

        // Draw probe dot at normalized coordinates × intrinsic size
        ctx.beginPath()
        ctx.arc(probe.x * canvas.width, probe.y * canvas.height, 8, 0, Math.PI * 2)
        ctx.fillStyle = '#00ffff'
        ctx.fill()
        ctx.strokeStyle = '#000'
        ctx.lineWidth = 2
        ctx.stroke()
      }

      setActiveRois({ Left: handsDetected.Left ?? null, Right: handsDetected.Right ?? null })

      const currentFps = fpsRef.current
      // Pass video-time ms so duration is in video seconds (correct at any speed).
      // When paused (pausedTimeout), advance the tracker clock by the wall-clock
      // elapsed since last call so grace timers can still expire.
      const timeForTracker = frameAdvanced
        ? videoTimeMs
        : videoTimeMs + (nowWall - prevWallMs)
      const newEvents = trackerRef.current.processFrame(handsDetected, currentRois, timeForTracker)
      for (const ev of newEvents) {
        if (ev.type === 'EXIT') {
          const roi = currentRois[ev.roiIndex]
          if (!roi) continue

          const endFrame = Math.round(video.currentTime * currentFps)
          const startFrame = Math.max(0, endFrame - Math.round(ev.duration * currentFps))

          // Skip if this hand already emitted an event that ends at or after
          // this start_frame — means we've rewound and would create a duplicate.
          if (startFrame <= maxEndFrameRef.current[ev.hand]) continue

          const category = ev.hand === 'Left'
            ? (roi.leftCategory ?? '')
            : (roi.rightCategory ?? '')

          maxEndFrameRef.current[ev.hand] = endFrame

          onCreateEventRef.current?.({
            operation: roi.name,
            start_frame: startFrame,
            end_frame: Math.max(startFrame + 1, endFrame),
            duration: Number(ev.duration.toFixed(6)),
            category,
            object: ev.hand === 'Left' ? 'Mão Esquerda' : 'Mão Direita',
            resource: roi.name,
          })
        }
      }
    }

    rafRef.current = requestAnimationFrame(tick)
  }

  function stopLoop() {
    if (rafRef.current) {
      cancelAnimationFrame(rafRef.current)
      rafRef.current = null
    }
    // Clear canvas
    const canvas = canvasRef.current
    if (canvas) {
      const ctx = canvas.getContext('2d')
      ctx?.clearRect(0, 0, canvas.width, canvas.height)
    }
    setActiveRois({ Left: null, Right: null })
  }

  // Start/stop loop when active toggles
  useEffect(() => {
    if (active && modelReady && videoReady) {
      startLoop()
    } else {
      stopLoop()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [active, modelReady, videoReady])

  // Stop tracking if video src changes
  useEffect(() => {
    setActive(false)
    trackerRef.current.reset()
    maxEndFrameRef.current = { Left: -1, Right: -1 }
    // Reset detection stats for the new video
    detectStatsRef.current = { cache: 0, live: 0, flushAt: 30 }
    setDetectStats({ cache: 0, live: 0 })
    setDetectionSource(null)
  }, [src])

  const onRoisChangeRef = useRef(onRoisChange)
  useEffect(() => { onRoisChangeRef.current = onRoisChange }, [onRoisChange])

  const handleRoisChange = useCallback((nextRois) => {
    setRois(nextRois)
    trackerRef.current.reset()
    setActiveRois({ Left: null, Right: null })
    setDrawingMode(false)
    onRoisChangeRef.current?.(nextRois)
  }, [])

  const toggleActive = () => {
    if (!active) {
      trackerRef.current.reset()
    }
    setActive((v) => !v)
  }

  // ── Render — pure overlay, zero layout footprint ────────────────────────
  // The component is wrapped in position:absolute inset:0 by App.jsx.
  // We fill that container completely and never add block-level height.
  return (
    // Full overlay — passes pointer events through except the toolbar and drawing mode
    <div style={{ position: 'absolute', inset: 0, pointerEvents: 'none' }}>

      {/* Landmark canvas.
          - Internal resolution matches the video's intrinsic size (set in tick()).
          - CSS object-fit:contain makes the browser scale/letterbox it exactly
            the same way the <video> element does, so landmarks line up perfectly. */}
      <canvas
        ref={canvasRef}
        style={{
          position: 'absolute',
          inset: 0,
          width: '100%',
          height: '100%',
          objectFit: 'contain',
          pointerEvents: 'none',
        }}
      />

      {/* ROI SVG overlay — pointer events only when drawing */}
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

      {/* Floating toolbar — top-left corner, always interactive */}
      <div
        style={{
          position: 'absolute',
          top: '0.5rem',
          left: '0.5rem',
          display: 'flex',
          gap: '0.4rem',
          alignItems: 'center',
          flexWrap: 'wrap',
          pointerEvents: 'auto',
          zIndex: 10,
        }}
      >
        {/* Model status */}
        {!modelReady && !modelError && (
          <span style={{
            fontSize: '0.72rem', color: '#ccc',
            background: 'rgba(0,0,0,0.7)', padding: '0.2rem 0.4rem', borderRadius: '0.4rem',
          }}>
            <Loader size={12} strokeWidth={2} style={{ animation: 'spin 1s linear infinite' }} /> Carregando modelo…
          </span>
        )}
        {modelError && (
          <span style={{
            fontSize: '0.72rem', color: '#ffb4b4',
            background: 'rgba(0,0,0,0.7)', padding: '0.2rem 0.4rem', borderRadius: '0.4rem',
          }}>
            <AlertTriangle size={12} strokeWidth={2} /> {modelError}
          </span>
        )}

        {/* Track toggle */}
        <button
          onClick={toggleActive}
          disabled={!modelReady || !videoReady}
          style={{
            padding: '0.3rem 0.6rem',
            borderRadius: '0.4rem',
            border: active ? '1px solid #1a4a1a' : '1px solid #444',
            background: active ? 'rgba(13,46,13,0.9)' : 'rgba(0,0,0,0.75)',
            color: '#fff',
            cursor: (!modelReady || !videoReady) ? 'not-allowed' : 'pointer',
            fontSize: '0.75rem',
            opacity: (!modelReady || !videoReady) ? 0.5 : 1,
          }}
        >
          {active ? <><Activity size={13} strokeWidth={2} /> Rastreando</> : <><Play size={13} strokeWidth={2} /> Rastrear</>}
        </button>

        {/* Detection source badge — shows whether the current frame came from
            the pre-processed cache or from live MediaPipe inference */}
        {active && detectionSource && (() => {
          const total = detectStats.cache + detectStats.live
          const cachePct = total > 0 ? Math.round((detectStats.cache / total) * 100) : 0
          const isFullCache = detectionSource === 'cache'
          return (
            <span
              title={
                `Cache: ${detectStats.cache} frames\n` +
                `Ao vivo: ${detectStats.live} frames\n` +
                `Total processado: ${total}`
              }
              style={{
                padding: '0.2rem 0.5rem',
                borderRadius: '0.4rem',
                fontSize: '0.7rem',
                fontWeight: 600,
                background: isFullCache ? 'rgba(0,80,20,0.85)' : 'rgba(80,40,0,0.85)',
                border: `1px solid ${isFullCache ? '#2ca02c' : '#ff7f0e'}`,
                color: isFullCache ? '#6fcf6f' : '#ffb347',
                whiteSpace: 'nowrap',
                cursor: 'default',
              }}
            >
              {isFullCache ? <><Zap size={11} strokeWidth={2} /> Cache</> : <><Radio size={11} strokeWidth={2} /> Ao vivo</>}{' '}
              <span style={{ opacity: 0.8 }}>{cachePct}%</span>
            </span>
          )
        })()}

        {/* Draw ROI */}
        <button
          onClick={() => setDrawingMode((v) => !v)}
          style={{
            padding: '0.3rem 0.6rem',
            borderRadius: '0.4rem',
            border: drawingMode ? '1px solid #1a4a1a' : '1px solid #444',
            background: drawingMode ? 'rgba(13,46,13,0.9)' : 'rgba(0,0,0,0.75)',
            color: '#fff',
            cursor: 'pointer',
            fontSize: '0.75rem',
          }}
        >
          {drawingMode ? <><Pencil size={13} strokeWidth={2} /> Desenhando…</> : <><Pencil size={13} strokeWidth={2} /> ROI</>}
        </button>

        {/* Clear ROIs */}
        {rois.length > 0 && (
          <button
            onClick={() => {
              setRois([])
              trackerRef.current.reset()
              setActiveRois({ Left: null, Right: null })
            }}
            style={{
              padding: '0.3rem 0.6rem',
              borderRadius: '0.4rem',
              border: '1px solid #4b1d1d',
              background: 'rgba(42,18,18,0.85)',
              color: '#fff',
              cursor: 'pointer',
              fontSize: '0.75rem',
            }}
          >
            <Trash2 size={13} strokeWidth={2} />
          </button>
        )}

        {/* ROI name badges */}
        {rois.map((roi, i) => (
          <span
            key={i}
            title={`Esq: ${roi.leftCategory || '—'} | Dir: ${roi.rightCategory || '—'}`}
            style={{
              padding: '0.2rem 0.45rem',
              borderRadius: '0.35rem',
              fontSize: '0.7rem',
              border: `1px solid ${ROI_COLORS[i % ROI_COLORS.length]}`,
              color: ROI_COLORS[i % ROI_COLORS.length],
              background: 'rgba(0,0,0,0.75)',
              cursor: 'default',
              whiteSpace: 'nowrap',
            }}
          >
            {roi.name}
            <span style={{ opacity: 0.65, marginLeft: '0.25rem' }}>
              E:{roi.leftCategory || '—'} D:{roi.rightCategory || '—'}
            </span>
          </span>
        ))}
      </div>
    </div>
  )
})

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
 *   videoRef       React ref — the SAME <video> element used by VideoPlayer
 *   src            string    — current video src
 *   fps            number    — project FPS (used for frame counting)
 *   isReady        bool      — true once video metadata is loaded
 *   onCreateEvent  fn(event) — called on every ROI EXIT
 */
import { useEffect, useRef, useState, useCallback } from 'react'
import { HandLandmarker, FilesetResolver, DrawingUtils } from '@mediapipe/tasks-vision'
import RoiOverlay from './RoiOverlay'
import { RoiTracker, detectRoi } from '../lib/roiTracker'

const ROI_COLORS = ['#00ff00', '#ff00ff', '#00ffff', '#ffff00', '#ff4444', '#ff8800']

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

export default function VideoAnalyzer({ videoRef, src, fps = 30, onCreateEvent }) {
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
  const [rois, setRois] = useState([])
  const [drawingMode, setDrawingMode] = useState(false)
  const [activeRois, setActiveRois] = useState({ Left: null, Right: null })
  // Derived from videoRef directly — no prop needed
  const [videoReady, setVideoReady] = useState(false)

  const roisRef = useRef(rois)
  useEffect(() => { roisRef.current = rois }, [rois])

  const fpsRef = useRef(fps)
  useEffect(() => { fpsRef.current = fps }, [fps])

  const onCreateEventRef = useRef(onCreateEvent)
  useEffect(() => { onCreateEventRef.current = onCreateEvent }, [onCreateEvent])

  const activeRef = useRef(active)
  useEffect(() => { activeRef.current = active }, [active])

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

      // detectForVideo requires a strictly-increasing timestamp — performance.now()
      // is always monotonic, regardless of whether the video is paused.
      const results = landmarkerRef.current.detectForVideo(video, performance.now())
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
  }, [src])

  const handleRoisChange = useCallback((nextRois) => {
    setRois(nextRois)
    trackerRef.current.reset()
    setActiveRois({ Left: null, Right: null })
    setDrawingMode(false)
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
            ⏳ Carregando modelo…
          </span>
        )}
        {modelError && (
          <span style={{
            fontSize: '0.72rem', color: '#ffb4b4',
            background: 'rgba(0,0,0,0.7)', padding: '0.2rem 0.4rem', borderRadius: '0.4rem',
          }}>
            ⚠️ {modelError}
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
          {active ? '🟢 Rastreando' : '▶ Rastrear'}
        </button>

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
          {drawingMode ? '✏️ Desenhando…' : '✏️ ROI'}
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
            🗑️
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
}

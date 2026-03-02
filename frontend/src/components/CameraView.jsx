/**
 * CameraView.jsx
 *
 * Real-time hand tracking (MediaPipe Tasks-Vision, WASM) + polygonal ROI detection.
 *
 * Props:
 *   fps            number  — project FPS, used to convert durations to frame counts
 *   onCreateEvent  fn(event) — called with a fully-formed project event on every EXIT
 */
import { useEffect, useRef, useState, useCallback } from 'react'
import { HandLandmarker, FilesetResolver, DrawingUtils } from '@mediapipe/tasks-vision'
import RoiOverlay from './RoiOverlay'
import { RoiTracker, detectRoi } from '../lib/roiTracker'

const HAND_CONNECTIONS = HandLandmarker.HAND_CONNECTIONS
const ROI_COLORS = ['#00ff00', '#ff00ff', '#00ffff', '#ffff00', '#ff4444', '#ff8800']

// ── Geometric filter ─────────────────────────────────────────────────────────
// Minimal filter: only reject detections that are clearly too small to be a
// real hand (e.g. stray noise). Everything else is left to MediaPipe's own
// confidence thresholds (set high below).
function isValidHand(landmarks) {
  if (!landmarks || landmarks.length < 21) return false
  const xs = landmarks.map((l) => l.x)
  const ys = landmarks.map((l) => l.y)
  const w = Math.max(...xs) - Math.min(...xs)
  const h = Math.max(...ys) - Math.min(...ys)
  // Reject only truly tiny bounding boxes (noise / partial frames)
  return Math.sqrt(w * w + h * h) >= 0.04
}

// Probe point for ROI membership: centroid of the index finger chain
// (landmarks 5=MCP, 6=PIP, 7=DIP, 8=tip).
// Using the full chain instead of just the tip makes detection robust when
// the fingertip is occluded by a held object — the centroid stays in the
// right region even when landmark 8 is being estimated behind the object.
function getProbe(landmarks) {
  const chain = [landmarks[5], landmarks[6], landmarks[7], landmarks[8]]
  return {
    x: chain.reduce((s, l) => s + l.x, 0) / chain.length,
    y: chain.reduce((s, l) => s + l.y, 0) / chain.length,
  }
}

// Convert a tracker EXIT event + ROI config into a project event object
function buildProjectEvent(trackerEvent, roi, fps) {
  const { hand, duration } = trackerEvent
  const frames = Math.max(1, Math.round(duration * fps))
  // Use a virtual start frame anchored to wall-clock seconds since epoch
  // so events are roughly ordered chronologically in the list.
  const startFrame = Math.round((trackerEvent.timestamp - frames * (1000 / fps)) / (1000 / fps))
  const endFrame = startFrame + frames

  const category = hand === 'Left'
    ? (roi?.leftCategory ?? '')
    : (roi?.rightCategory ?? '')

  return {
    operation: roi?.name ?? 'ROI',
    start_frame: Math.max(0, startFrame),
    end_frame: Math.max(1, endFrame),
    duration: Number(duration.toFixed(6)),
    category,
    object: hand === 'Left' ? 'Mão Esquerda' : 'Mão Direita',
    resource: roi?.name ?? 'ROI',
  }
}

export default function CameraView({ fps = 30, onCreateEvent }) {
  const videoRef = useRef(null)
  const canvasRef = useRef(null)
  const landmarkerRef = useRef(null)
  const rafRef = useRef(null)
  const streamRef = useRef(null)
  const trackerRef = useRef(new RoiTracker())

  const [status, setStatus] = useState('Iniciando câmera…')
  const [error, setError] = useState(null)

  const [rois, setRois] = useState([])
  const [drawingMode, setDrawingMode] = useState(false)
  const [activeRois, setActiveRois] = useState({ Left: null, Right: null })

  // Keep rois accessible inside rAF loop without stale closure
  const roisRef = useRef(rois)
  useEffect(() => { roisRef.current = rois }, [rois])

  const fpsRef = useRef(fps)
  useEffect(() => { fpsRef.current = fps }, [fps])

  const onCreateEventRef = useRef(onCreateEvent)
  useEffect(() => { onCreateEventRef.current = onCreateEvent }, [onCreateEvent])

  // ── 1. Load HandLandmarker then open camera ──────────────────────────────
  useEffect(() => {
    let cancelled = false

    async function init() {
      try {
        setStatus('Carregando modelo MediaPipe…')
        const vision = await FilesetResolver.forVisionTasks('/mediapipe-wasm')
        const landmarker = await HandLandmarker.createFromOptions(vision, {
          baseOptions: {
            // full model — more robust to occlusion (e.g. hand holding objects)
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
        if (cancelled) return
        landmarkerRef.current = landmarker
        setStatus('Abrindo câmera…')
        await startCamera()
      } catch (e) {
        if (!cancelled) setError(`Erro ao carregar MediaPipe: ${e.message ?? e}`)
      }
    }

    init()
    return () => { cancelled = true; stopAll() }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // ── 2. Camera stream ─────────────────────────────────────────────────────
  async function startCamera() {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: { width: { ideal: 1280 }, height: { ideal: 720 }, facingMode: 'user' },
      })
      streamRef.current = stream
      const video = videoRef.current
      if (!video) return
      video.srcObject = stream
      video.onloadedmetadata = () => {
        video.play()
        setStatus('')
        startDetectionLoop()
      }
    } catch (e) {
      setError(`Câmera não disponível: ${e.message ?? e}`)
    }
  }

  // ── 3. rAF detection + ROI tracking loop ────────────────────────────────
  function startDetectionLoop() {
    const video = videoRef.current
    const canvas = canvasRef.current
    if (!video || !canvas) return

    const ctx = canvas.getContext('2d')
    const drawingUtils = new DrawingUtils(ctx)
    let lastCallTime = -1

    function detect() {
      rafRef.current = requestAnimationFrame(detect)
      if (video.readyState < 2) return

      if (canvas.width !== video.videoWidth || canvas.height !== video.videoHeight) {
        canvas.width = video.videoWidth || 640
        canvas.height = video.videoHeight || 480
      }

      // Throttle to camera frame rate: skip if less than ~15ms since last call (~60fps max)
      const now = performance.now()
      if (now - lastCallTime < 15) return
      lastCallTime = now

      const landmarker = landmarkerRef.current
      if (!landmarker) return

      const results = landmarker.detectForVideo(video, now)
      ctx.clearRect(0, 0, canvas.width, canvas.height)

      const validLandmarks = (results.landmarks ?? []).filter(isValidHand)
      const validHandedness = (results.handedness ?? []).filter(
        (_, i) => isValidHand(results.landmarks?.[i])
      )

      for (const landmarks of validLandmarks) {
        drawingUtils.drawConnectors(landmarks, HAND_CONNECTIONS, { color: '#00FF00', lineWidth: 2 })
        drawingUtils.drawLandmarks(landmarks, { color: '#FF0000', lineWidth: 1, radius: 4 })
      }

      const handsDetected = {}
      const currentRois = roisRef.current

      for (let i = 0; i < validLandmarks.length; i++) {
        // MediaPipe labels are camera-perspective; flip to match user's mirror view
        const rawLabel = validHandedness[i]?.[0]?.categoryName ?? 'Left'
        const userLabel = rawLabel === 'Left' ? 'Right' : 'Left'
        const probe = getProbe(validLandmarks[i])
        const roiIdx = detectRoi(probe.x, probe.y, currentRois)
        handsDetected[userLabel] = roiIdx

        // Draw probe dot (cyan)
        ctx.beginPath()
        ctx.arc(probe.x * canvas.width, probe.y * canvas.height, 8, 0, Math.PI * 2)
        ctx.fillStyle = '#00ffff'
        ctx.fill()
        ctx.strokeStyle = '#000'
        ctx.lineWidth = 2
        ctx.stroke()
      }

      setActiveRois({ Left: handsDetected.Left ?? null, Right: handsDetected.Right ?? null })

      // Process tracker — on EXIT build and emit a project event
      const newTrackerEvents = trackerRef.current.processFrame(handsDetected, currentRois)
      for (const ev of newTrackerEvents) {
        if (ev.type === 'EXIT') {
          const roi = currentRois[ev.roiIndex]
          const projectEvent = buildProjectEvent(ev, roi, fpsRef.current)
          onCreateEventRef.current?.(projectEvent)
        }
      }
    }

    rafRef.current = requestAnimationFrame(detect)
  }

  // ── 4. Cleanup ───────────────────────────────────────────────────────────
  function stopAll() {
    if (rafRef.current) cancelAnimationFrame(rafRef.current)
    if (streamRef.current) {
      streamRef.current.getTracks().forEach((t) => t.stop())
      streamRef.current = null
    }
    landmarkerRef.current?.close?.()
    landmarkerRef.current = null
  }

  const handleRoisChange = useCallback((nextRois) => {
    setRois(nextRois)
    trackerRef.current.reset()
    setActiveRois({ Left: null, Right: null })
    setDrawingMode(false)
  }, [])

  // ── Render ───────────────────────────────────────────────────────────────
  return (
    <div style={{ display: 'flex', flexDirection: 'column', width: '100%', height: '100%', gap: '0.5rem' }}>

      {/* Toolbar */}
      <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center', flexWrap: 'wrap', flexShrink: 0 }}>
        <button
          onClick={() => setDrawingMode((v) => !v)}
          style={{
            padding: '0.35rem 0.75rem',
            borderRadius: '0.5rem',
            border: drawingMode ? '1px solid #1a4a1a' : '1px solid #2a2a2a',
            background: drawingMode ? '#0d2e0d' : '#111',
            cursor: 'pointer',
            fontSize: '0.8rem',
          }}
        >
          {drawingMode ? '✏️ Desenhando…' : '✏️ Desenhar ROI'}
        </button>

        {rois.length > 0 && (
          <button
            onClick={() => {
              setRois([])
              trackerRef.current.reset()
              setActiveRois({ Left: null, Right: null })
            }}
            style={{
              padding: '0.35rem 0.75rem',
              borderRadius: '0.5rem',
              border: '1px solid #4b1d1d',
              background: '#2a1212',
              cursor: 'pointer',
              fontSize: '0.8rem',
            }}
          >
            🗑️ Limpar ROIs
          </button>
        )}

        {/* ROI badges with category info */}
        {rois.map((roi, i) => (
          <span
            key={i}
            title={`Esq: ${roi.leftCategory || '—'} | Dir: ${roi.rightCategory || '—'}`}
            style={{
              padding: '0.2rem 0.5rem',
              borderRadius: '0.4rem',
              fontSize: '0.75rem',
              border: `1px solid ${ROI_COLORS[i % ROI_COLORS.length]}`,
              color: ROI_COLORS[i % ROI_COLORS.length],
              background: '#111',
              cursor: 'default',
            }}
          >
            {roi.name}
            <span style={{ opacity: 0.7, marginLeft: '0.3rem', fontSize: '0.7rem' }}>
              E:{roi.leftCategory || '—'} D:{roi.rightCategory || '—'}
            </span>
          </span>
        ))}
      </div>

      {/* Camera + overlays */}
      <div
        style={{
          position: 'relative',
          flex: 1,
          minHeight: 0,
          background: '#000',
          borderRadius: '0.75rem',
          overflow: 'hidden',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
        }}
      >
        {/* Status / error */}
        {(status || error) && (
          <div
            style={{
              position: 'absolute',
              inset: 0,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              zIndex: 10,
              background: 'rgba(0,0,0,0.65)',
              color: error ? '#ffb4b4' : '#ccc',
              fontSize: '0.9rem',
              padding: '1rem',
              textAlign: 'center',
            }}
          >
            {error ?? status}
          </div>
        )}

        {/* Camera feed (CSS-mirrored) */}
        <video
          ref={videoRef}
          autoPlay
          playsInline
          muted
          style={{ width: '100%', height: '100%', objectFit: 'contain', display: 'block', transform: 'scaleX(-1)' }}
        />

        {/* Landmark canvas (CSS-mirrored to match video) */}
        <canvas
          ref={canvasRef}
          style={{
            position: 'absolute', inset: 0,
            width: '100%', height: '100%',
            objectFit: 'contain',
            transform: 'scaleX(-1)',
            pointerEvents: 'none',
          }}
        />

        {/* ROI overlay (no CSS mirror — coordinates handled mathematically) */}
        <RoiOverlay
          rois={rois}
          activeRois={activeRois}
          drawingMode={drawingMode}
          onRoisChange={handleRoisChange}
        />
      </div>
    </div>
  )
}

/**
 * useVideoPreprocess.js
 *
 * Pre-processes every frame of a video with MediaPipe HandLandmarker and
 * stores the results in a Map so VideoAnalyzer can play them back instantly,
 * without running the neural network in real-time during playback.
 *
 * Architecture
 * ────────────
 *  • Creates its OWN HandLandmarker instance (does NOT share with VideoAnalyzer).
 *    This avoids all timestamp-collision and mode-switching problems.
 *  • A hidden <video> is created in memory; we seek frame-by-frame and call
 *    detectForVideo() using a fake strictly-increasing timestamp per frame.
 *  • Results are stored in:
 *      cacheRef.current  →  Map<frameNumber, { landmarks, handedness } | null>
 *    where null means "no hands detected on this frame".
 *  • Progress (0–1) is reported reactively.
 *  • Processing is cancelled automatically when src changes or component unmounts.
 */
import { useEffect, useRef, useState, useCallback } from 'react'
import { HandLandmarker, FilesetResolver } from '@mediapipe/tasks-vision'

// Same model URL used by VideoAnalyzer
const MODEL_URL =
  'https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/latest/hand_landmarker.task'

/**
 * @param {object} opts
 * @param {string}  opts.src            — blob URL of the video to process
 * @param {string}   opts.src         — blob URL of the video to process
 * @param {number}   opts.fps         — frames per second
 * @param {function} [opts.onProgress] — (fraction: 0–1) => void
 * @param {function} [opts.onDone]     — () => void
 * @returns {{ cacheRef, status, progress, cancel }}
 */
export function useVideoPreprocess({ src, fps, onProgress, onDone }) {
  const cacheRef  = useRef(new Map())
  const cancelRef = useRef(false)

  const [status,   setStatus]   = useState('idle')   // idle|processing|done|error|cancelled
  const [progress, setProgress] = useState(0)

  const cancel = useCallback(() => { cancelRef.current = true }, [])

  useEffect(() => {
    if (!src) {
      cacheRef.current = new Map()
      setStatus('idle')
      setProgress(0)
      return
    }

    // Signal any in-flight run to stop
    cancelRef.current = true

    // Brief delay so the previous async run can detect the cancellation flag
    const t = setTimeout(() => {
      cancelRef.current = false
      cacheRef.current  = new Map()
      setStatus('processing')
      setProgress(0)

      runPreprocess({
        src,
        fps,
        cacheRef,
        cancelRef,
        onProgress: (frac) => {
          setProgress(frac)
          onProgress?.(frac)
        },
        onDone: () => {
          setStatus('done')
          setProgress(1)
          onDone?.()
        },
        onError: (err) => {
          console.error('[VideoPreprocess] error:', err)
          setStatus('error')
        },
        onCancelled: () => {
          setStatus('cancelled')
        },
      })
    }, 100)

    return () => {
      clearTimeout(t)
      cancelRef.current = true
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [src])

  return { cacheRef, status, progress, cancel }
}

// ─── Core async processing function ──────────────────────────────────────────
async function runPreprocess({
  src, fps, cacheRef, cancelRef,
  onProgress, onDone, onError, onCancelled,
}) {
  let landmarker = null

  try {
    // ── 1. Load a DEDICATED HandLandmarker instance in VIDEO mode ─────────
    // We never share this instance with VideoAnalyzer — that avoids all
    // timestamp-collision problems between the preprocess series and the
    // live playback series.
    const vision = await FilesetResolver.forVisionTasks('/mediapipe-wasm')
    if (cancelRef.current) { onCancelled(); return }

    landmarker = await HandLandmarker.createFromOptions(vision, {
      baseOptions: { modelAssetPath: MODEL_URL, delegate: 'GPU' },
      runningMode: 'VIDEO',
      numHands: 2,
      minHandDetectionConfidence: 0.5,
      minHandPresenceConfidence: 0.5,
      minTrackingConfidence: 0.4,
    })
    if (cancelRef.current) { landmarker.close(); onCancelled(); return }

    // ── 2. Load the video into a detached element ─────────────────────────
    const video = document.createElement('video')
    video.src         = src
    video.muted       = true
    video.preload     = 'auto'
    video.crossOrigin = 'anonymous'

    await new Promise((resolve, reject) => {
      video.onloadedmetadata = resolve
      video.onerror = () => reject(new Error('Falha ao carregar metadados do vídeo'))
    })
    if (cancelRef.current) { landmarker.close(); onCancelled(); return }

    const totalFrames  = Math.ceil(video.duration * fps)
    const frameIntervalMs = 1000 / fps

    // ── 3. Canvas for frame extraction ────────────────────────────────────
    const W = video.videoWidth  || 640
    const H = video.videoHeight || 480
    const canvas = document.createElement('canvas')
    canvas.width  = W
    canvas.height = H
    const ctx = canvas.getContext('2d')

    // ── 4. Seek-and-detect loop ───────────────────────────────────────────
    // detectForVideo requires a STRICTLY INCREASING timestamp (ms).
    // We use frame * frameIntervalMs — each call is one frame apart,
    // which satisfies MediaPipe's constraint.
    for (let frame = 0; frame < totalFrames; frame++) {
      if (cancelRef.current) {
        landmarker.close()
        onCancelled()
        return
      }

      await seekTo(video, frame / fps)
      ctx.drawImage(video, 0, 0, W, H)

      let result
      try {
        result = landmarker.detectForVideo(canvas, frame * frameIntervalMs)
      } catch (e) {
        console.warn(`[VideoPreprocess] frame ${frame} skipped:`, e.message)
        result = { landmarks: [], handedness: [] }
      }

      const { landmarks = [], handedness = [] } = result
      cacheRef.current.set(
        frame,
        landmarks.length > 0 ? { landmarks, handedness } : null,
      )

      // Report progress and yield to the browser every 10 frames
      if (frame % 10 === 0 || frame === totalFrames - 1) {
        onProgress((frame + 1) / totalFrames)
        await yieldToUI()
      }
    }

    landmarker.close()
    onDone()

  } catch (err) {
    landmarker?.close()
    onError(err)
  }
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

function seekTo(video, time) {
  return new Promise((resolve) => {
    if (Math.abs(video.currentTime - time) < 0.001) { resolve(); return }
    const done = () => { video.removeEventListener('seeked', done); resolve() }
    video.addEventListener('seeked', done)
    video.currentTime = time
  })
}

function yieldToUI() {
  return new Promise((r) => setTimeout(r, 0))
}

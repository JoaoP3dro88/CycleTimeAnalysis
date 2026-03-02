import { forwardRef, useEffect, useImperativeHandle, useMemo, useRef, useState } from 'react'
import { formatTime } from '../lib/time'
import { apiGet } from '../lib/api'
import '../styles/controls.css'

export function VideoCanvas({ videoRef, src, maxHeight = '60vh' }) {
  return (
    <div style={{ marginTop: 0, height: '100%' }}>
      <video
        ref={videoRef}
        src={src || undefined}
        style={{ width: '100%', height: '100%', maxHeight, background: '#000', borderRadius: '0.65rem' }}
        controls
      />
    </div>
  )
}

/**
 * Web video player with start/end marking similar to the legacy PyQt workflow.
 *
 * Notes:
 * - In browser we work in seconds. We map to frames using fps.
 * - We rely on requestVideoFrameCallback when available for smoother frame sampling.
 */
const VideoPlayer = forwardRef(function VideoPlayer(
  {
    fps = 30,
    onMarkStart,
    onMarkEnd,
    loopRange,
    onLoopRangeChange,
    layout = 'stacked', // 'stacked' | 'controls' | 'split'
    renderVideo,
    externalSrc,
  },
  ref
) {
  const videoRef = useRef(null)
  const rVfcId = useRef(null)

  const [fileUrl, setFileUrl] = useState('')
  const [fileName, setFileName] = useState('')
  const [library, setLibrary] = useState([])
  const [selectedLibraryUrl, setSelectedLibraryUrl] = useState('')
  const [isReady, setIsReady] = useState(false)
  const [isPlaying, setIsPlaying] = useState(false)
  const [durationS, setDurationS] = useState(0)
  const [currentS, setCurrentS] = useState(0)
  const [uiFrame, setUiFrame] = useState(0)
  const [speed, setSpeed] = useState(1)

  const currentFrame = useMemo(() => uiFrame, [uiFrame])
  const totalFrames = useMemo(() => Math.floor(durationS * fps), [durationS, fps])

  async function refreshLibrary() {
    try {
      const vids = await apiGet('/api/projects/videos')
      setLibrary(Array.isArray(vids) ? vids : [])
    } catch {
      // ignore; backend may be down while frontend still loads
    }
  }

  useEffect(() => {
    refreshLibrary()
  }, [])

  const effectiveSrc = externalSrc || fileUrl

  // If src is cleared, immediately consider the player not ready.
  useEffect(() => {
    if (!effectiveSrc) {
      setIsReady(false)
      setIsPlaying(false)
      setDurationS(0)
      setCurrentS(0)
      setUiFrame(0)
    }
  }, [effectiveSrc])

  useEffect(() => {
    const video = videoRef.current
    if (!video) return

    function onLoadedMetadata() {
      setIsReady(true)
      setDurationS(video.duration || 0)
      setCurrentS(video.currentTime || 0)
      setUiFrame(Math.round((video.currentTime || 0) * fps))
    }

    // Some browsers/cases (especially when src is set from outside) can fire
    // loadeddata/canplay more reliably than loadedmetadata.
    function onCanPlayLike() {
      if (!isFinite(video.duration)) return
      setIsReady(true)
      setDurationS(video.duration || 0)
      setCurrentS(video.currentTime || 0)
      setUiFrame(Math.round((video.currentTime || 0) * fps))
    }

    function onTimeUpdate() {
      setCurrentS(video.currentTime || 0)
      setUiFrame(Math.round((video.currentTime || 0) * fps))
    }

    function onPlay() {
      setIsPlaying(true)
    }

    function onPause() {
      setIsPlaying(false)
    }

    video.addEventListener('loadedmetadata', onLoadedMetadata)
  video.addEventListener('loadeddata', onCanPlayLike)
  video.addEventListener('canplay', onCanPlayLike)
    video.addEventListener('timeupdate', onTimeUpdate)
    video.addEventListener('play', onPlay)
    video.addEventListener('pause', onPause)

    // requestVideoFrameCallback gives us frame-accurate-ish updates.
    if (typeof video.requestVideoFrameCallback === 'function') {
      const tick = () => {
        setCurrentS(video.currentTime || 0)
        setUiFrame(Math.round((video.currentTime || 0) * fps))
        rVfcId.current = video.requestVideoFrameCallback(tick)
      }
      rVfcId.current = video.requestVideoFrameCallback(tick)
    }

    return () => {
      video.removeEventListener('loadedmetadata', onLoadedMetadata)
      video.removeEventListener('loadeddata', onCanPlayLike)
      video.removeEventListener('canplay', onCanPlayLike)
      video.removeEventListener('timeupdate', onTimeUpdate)
      video.removeEventListener('play', onPlay)
      video.removeEventListener('pause', onPause)
      if (rVfcId.current && typeof video.cancelVideoFrameCallback === 'function') {
        video.cancelVideoFrameCallback(rVfcId.current)
      }
    }
  }, [effectiveSrc])

  // If the src changes from the outside, make sure the <video> element is updated.
  useEffect(() => {
    const v = videoRef.current
    if (!v) return
    if (!effectiveSrc) return
    if (v.src !== effectiveSrc) {
      setIsReady(false)
      v.src = effectiveSrc
      // Ensure metadata load starts; loadedmetadata will flip isReady to true.
      v.load?.()

      // If the browser already has enough data immediately, don't keep controls disabled.
      // readyState: 0=HAVE_NOTHING, 1=HAVE_METADATA, 2=HAVE_CURRENT_DATA...
      if (v.readyState >= 1) {
        setIsReady(true)
      }
    }
  }, [effectiveSrc])

  // Loop behavior (front-only state): if loopRange is active, jump back when reaching end.
  useEffect(() => {
    const video = videoRef.current
    if (!video) return
    if (!loopRange?.active) return

    const handle = window.setInterval(() => {
      const endS = loopRange.endFrame / fps
      const startS = loopRange.startFrame / fps
      if (video.currentTime >= endS) {
        video.currentTime = startS
      }
    }, 50)

    return () => window.clearInterval(handle)
  }, [loopRange, fps])

  function onPickFile(e) {
    const file = e.target.files?.[0]
    if (!file) return

    const url = URL.createObjectURL(file)
    setFileUrl(url)
    setFileName(file.name)
    setSelectedLibraryUrl('')
    setIsReady(false)
    setDurationS(0)
    setCurrentS(0)

    // reset loop when loading a new file
    onLoopRangeChange?.({ active: false, startFrame: 0, endFrame: 0 })
  }

  async function uploadCurrentFile() {
    // Re-ask for a file (blob URL can't be re-uploaded reliably), so we use the input flow.
    // This button is mainly to clarify the intended workflow: upload video to backend for persistence.
    // We'll open the file picker again.
    const picker = document.createElement('input')
    picker.type = 'file'
    picker.accept = 'video/*'
    picker.onchange = async () => {
      const file = picker.files?.[0]
      if (!file) return
      const form = new FormData()
      form.append('file', file)
      const res = await fetch('http://127.0.0.1:8000/api/projects/videos/upload', {
        method: 'POST',
        body: form,
      })
      if (!res.ok) {
        const txt = await res.text()
        throw new Error(`Upload failed: ${res.status} ${txt}`)
      }
      const saved = await res.json()
      if (saved?.url) {
        setFileUrl(`http://127.0.0.1:8000${saved.url}`)
        setFileName(saved.name ?? file.name)
        setSelectedLibraryUrl(`http://127.0.0.1:8000${saved.url}`)
        await refreshLibrary()
      }
    }
    picker.click()
  }

  function setPlaybackRate(next) {
    const video = videoRef.current
    setSpeed(next)
    if (video) video.playbackRate = next
  }

  function stepFrames(delta) {
    const video = videoRef.current
    if (!video || !isReady) return

    // Use the element time as the source of truth (React state can lag).
    // We also "snap" after the seek, because some codecs land between frames.
    video.pause()

    const cur = Number.isFinite(video.currentTime) ? video.currentTime : 0
    const curFrame = Math.round(cur * fps)
    const nextFrame = Math.max(0, Math.min(totalFrames - 1, curFrame + delta))
    const targetS = nextFrame / fps

    const snap = () => {
      // Snap to the nearest frame after the seek settles.
      const f = Math.round((video.currentTime || 0) * fps)
      video.currentTime = Math.max(0, Math.min(totalFrames - 1, f)) / fps
      // Force UI refresh (some browsers don't fire timeupdate on programmatic seeks while paused)
      setCurrentS(video.currentTime || 0)
      setUiFrame(nextFrame)
    }

    const onSeeked = () => {
      video.removeEventListener('seeked', onSeeked)
      snap()
    }

    video.addEventListener('seeked', onSeeked)
    video.currentTime = targetS

    // Fallback: if 'seeked' is flaky, still snap on next frame/tick.
    if (typeof video.requestVideoFrameCallback === 'function') {
      video.requestVideoFrameCallback(() => snap())
    } else {
      window.setTimeout(snap, 0)
    }
  }

  function seekToFrame(frame) {
    const video = videoRef.current
    if (!video || !isReady) return
    const safe = Math.max(0, Math.min(totalFrames - 1, frame))
    video.currentTime = safe / fps
    setUiFrame(safe)
  }

  function play() {
    const video = videoRef.current
    if (!video || !isReady) return
    void video.play()
  }

  function pause() {
    const video = videoRef.current
    if (!video || !isReady) return
    video.pause()
  }

  useImperativeHandle(
    ref,
    () => ({
      seekToFrame,
      play,
      pause,
      getCurrentFrame: () => currentFrame,
      getIsReady: () => isReady,
    }),
    [currentFrame, isReady, fps, totalFrames]
  )

  const controls = (
    <div>
      <div className="ctaRow" style={{ justifyContent: 'space-between' }}>
        <div style={{ display: 'flex', gap: 10, alignItems: 'center', flexWrap: 'wrap' }}>
          <span className="badge">
            FPS: <b>{fps}</b>
          </span>
          <span className="badge">
            Frame: <b>{currentFrame}</b> / {totalFrames}
          </span>
          <span className="badge">
            {formatTime(currentS)} / {formatTime(durationS)}
          </span>
          {fileName ? (
            <span className="badge" title={fileName}>
              Vídeo: <b>{fileName.length > 24 ? `${fileName.slice(0, 24)}…` : fileName}</b>
            </span>
          ) : null}
        </div>

        <div style={{ display: 'flex', gap: 10, alignItems: 'center', flexWrap: 'wrap' }}>
          <button className="btn" onClick={() => stepFrames(-1)} disabled={!isReady}>
            -1F
          </button>
          <button className="btn" onClick={() => stepFrames(1)} disabled={!isReady}>
            +1F
          </button>

          <select
            className="select"
            value={speed}
            onChange={(e) => setPlaybackRate(Number(e.target.value))}
            disabled={!isReady}
          >
            {[0.25, 0.5, 1, 2, 4].map((s) => (
              <option key={s} value={s}>
                {s}x
              </option>
            ))}
          </select>

          <button
            className="btn btnPrimary"
            onClick={() => {
              const video = videoRef.current
              if (!video || !isReady) return
              if (video.paused) video.play()
              else video.pause()
            }}
            disabled={!isReady}
          >
            {isPlaying ? 'Pause' : 'Play'}
          </button>

          <button
            className="btn"
            onClick={() => onMarkStart?.(currentFrame)}
            disabled={!isReady}
          >
            Marcar início
          </button>
          <button
            className="btn"
            onClick={() => onMarkEnd?.(currentFrame)}
            disabled={!isReady}
          >
            Marcar fim
          </button>
        </div>
      </div>
    </div>
  )

  const videoCanvas = typeof renderVideo === 'function' ? (
    renderVideo({ videoRef, src: effectiveSrc, isReady })
  ) : (
    <div style={{ marginTop: '0.75rem' }}>
      <VideoCanvas videoRef={videoRef} src={effectiveSrc} />
    </div>
  )

  const bottomRow = (
    <div>
      <div className="ctaRow" style={{ marginTop: '0.65rem' }}>
        <div style={{ display: 'flex', gap: 10, alignItems: 'center', flexWrap: 'wrap' }}>
          <span className="badge">Biblioteca:</span>
          <select
            className="select"
            value={selectedLibraryUrl}
            onChange={(e) => {
              const url = e.target.value
              setSelectedLibraryUrl(url)
              if (url) {
                setFileUrl(url)
                setFileName(url.split('/').slice(-1)[0])
              }
            }}
          >
            <option value="">— selecionar —</option>
            {library.map((v) => (
              <option key={v.url} value={`http://127.0.0.1:8000${v.url}`}>
                {v.name}
              </option>
            ))}
          </select>
          <button className="btn" onClick={refreshLibrary}>
            Atualizar lista
          </button>
        </div>
      </div>

      <div className="ctaRow" style={{ marginTop: '0.65rem' }}>
        <div style={{ display: 'flex', gap: 10, alignItems: 'center', flexWrap: 'wrap' }}>
          <label className="badge">
            Ir para frame:&nbsp;
            <input
              className="input"
              type="number"
              min={0}
              max={Math.max(0, totalFrames - 1)}
              defaultValue={0}
              onKeyDown={(e) => {
                if (e.key !== 'Enter') return
                const v = Number(e.currentTarget.value)
                if (Number.isFinite(v)) seekToFrame(v)
              }}
              style={{ width: '8rem' }}
              disabled={!isReady}
              title="Digite um frame e pressione Enter"
            />
          </label>

          <label className="badge" style={{ display: 'inline-flex', gap: 8, alignItems: 'center' }}>
            <input
              type="checkbox"
              checked={!!loopRange?.active}
              onChange={(e) => {
                const checked = e.currentTarget.checked
                if (checked) {
                  // If there's no configured range yet, create a small default range.
                  const hasRange =
                    Number.isFinite(loopRange?.startFrame) &&
                    Number.isFinite(loopRange?.endFrame) &&
                    loopRange.endFrame > loopRange.startFrame

                  if (hasRange) {
                    onLoopRangeChange?.({ ...loopRange, active: true })
                  } else {
                    const start = Math.max(0, currentFrame)
                    const end = Math.min(totalFrames - 1, currentFrame + Math.floor(fps))
                    onLoopRangeChange?.({ active: true, startFrame: start, endFrame: Math.max(end, start + 1) })
                  }
                } else {
                  onLoopRangeChange?.({ ...(loopRange ?? { startFrame: 0, endFrame: 0 }), active: false })
                }
              }}
              disabled={!isReady}
            />
            Loop
          </label>

          <button
            className="btn"
            onClick={() => {
              // Set / refresh loop window around current frame (does not implicitly toggle off).
              const start = Math.max(0, currentFrame)
              const end = Math.min(totalFrames - 1, currentFrame + Math.floor(fps))
              onLoopRangeChange?.({ active: true, startFrame: start, endFrame: Math.max(end, start + 1) })
              seekToFrame(start)
            }}
            disabled={!isReady}
            title="Define o loop em torno do frame atual"
          >
            Definir loop
          </button>

          {loopRange?.active ? (
            <span className="badge" style={{ display: 'inline-flex', gap: 6, alignItems: 'center' }}>
              Loop: <b>{loopRange.startFrame}</b> → <b>{loopRange.endFrame}</b>
            </span>
          ) : null}
        </div>
      </div>
    </div>
  )

  if (layout === 'controls') {
    return (
      <div className="card">
        {controls}
        {bottomRow}
      </div>
    )
  }

  if (layout === 'split') {
    return (
      <div>
        {controls}
        {bottomRow}
      </div>
    )
  }

  return (
    <div className="card">
      {controls}
      {videoCanvas}
      {bottomRow}
    </div>
  )
})

export default VideoPlayer

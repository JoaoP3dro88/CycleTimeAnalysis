import './App.css'

import { useEffect, useMemo, useRef, useState, useCallback } from 'react'
import {
  Timer, FolderOpen, Download, Camera, Save, FilePlus,
  Settings, BarChart2, X,
  CheckCircle, AlertTriangle,
} from 'lucide-react'
import EventEditor from './components/EventEditor'
import VideoPlayer, { VideoCanvas } from './components/VideoPlayer'
import CameraView from './components/CameraView'
import VideoAnalyzer from './components/VideoAnalyzer'
import Dashboard from './components/Dashboard'
import { apiGet, apiPost } from './lib/api'
import { useVideoPreprocess } from './lib/useVideoPreprocess'

// ─── Reusable header button style ────────────────────────────────────────────
const hBtn = (active = false, danger = false) => ({
  padding: '0.45rem 0.7rem',
  borderRadius: '0.5rem',
  border: danger ? '1px solid #4b1d1d'
        : active  ? '1px solid #2a4a1a'
        :           '1px solid #2a2a2a',
  background: danger ? '#2a1212'
            : active  ? '#172910'
            :           '#111',
  color: '#e0e0e0',
  cursor: 'pointer',
  fontSize: '0.82rem',
  fontWeight: active ? 600 : 400,
  whiteSpace: 'nowrap',
  transition: 'border-color 0.15s, background 0.15s',
})

function App() {
  const playerRef    = useRef(null)
  const videoRef     = useRef(null)   // single <video> DOM element shared by all
  const filePickerRef = useRef(null)
  const analyzerRef  = useRef(null)

  // ── Heartbeat: mantém o servidor vivo e encerra ao fechar ─────────────────
  useEffect(() => {
    const ping = () => fetch('/api/heartbeat', { method: 'POST' }).catch(() => {})
    ping()
    const interval = setInterval(ping, 5000)
    const onUnload = () => navigator.sendBeacon('/api/shutdown')
    window.addEventListener('beforeunload', onUnload)
    return () => {
      clearInterval(interval)
      window.removeEventListener('beforeunload', onUnload)
    }
  }, [])

  const [project,    setProject]    = useState(null)
  const [analytics,  setAnalytics]  = useState(null)
  const [error,      setError]      = useState('')
  const [busy,       setBusy]       = useState(false)
  const [unsaved,    setUnsaved]    = useState(false)
  const [projectFileName, setProjectFileName] = useState(null)
  const [pendingStartFrame, setPendingStartFrame] = useState(null)
  const [loopIndex,  setLoopIndex]  = useState(-1)
  const [loopRange,  setLoopRange]  = useState({ active: false, startFrame: 0, endFrame: 0 })
  const [cameraMode, setCameraMode] = useState(false)
  const [videoSrc,   setVideoSrc]   = useState('')
  const [activeTab,  setActiveTab]  = useState('editor') // 'editor' | 'dashboard'
  const [showSettings, setShowSettings] = useState(false)
  const [importedRois, setImportedRois] = useState(null) // ROIs restored from a JSON import
  const [trackingMode, setTrackingMode] = useState('manual') // 'manual' | 'tracking'

  // Editable project meta (FPS + takt time)
  const [metaFps,    setMetaFps]    = useState(30)
  const [metaTakt,   setMetaTakt]   = useState(10)

  // Toast for preprocess completion (auto-hide after 5 s)
  const [preprocessToast, setPreprocessToast] = useState(null) // null | 'done' | 'error'
  const toastTimerRef = useRef(null)

  const fps = useMemo(
    () => project?.meta?.fps ?? metaFps,
    [project, metaFps],
  )

  // Keep local meta fields in sync when a project loads
  useEffect(() => {
    if (project?.meta) {
      setMetaFps(project.meta.fps ?? 30)
      setMetaTakt(project.meta.takt_time ?? 10)
    }
  }, [project])

  // ── Pre-processing ────────────────────────────────────────────────────────
  const {
    cacheRef: preprocessCacheRef,
    status:   preprocessStatus,
    progress: preprocessProgress,
  } = useVideoPreprocess({ src: trackingMode === 'tracking' ? videoSrc : '', fps })

  // Show a toast when preprocess finishes or fails, then auto-dismiss
  useEffect(() => {
    if (preprocessStatus === 'done' || preprocessStatus === 'error') {
      setPreprocessToast(preprocessStatus)
      clearTimeout(toastTimerRef.current)
      toastTimerRef.current = setTimeout(() => setPreprocessToast(null), 5000)
    }
    if (preprocessStatus === 'processing') setPreprocessToast(null)
  }, [preprocessStatus])

  async function refreshAnalytics(p) {
    try {
      await apiPost('/api/projects/import', p)
      const a = await apiGet('/api/analytics/current')
      setAnalytics(a)
    } catch { /* non-fatal */ }
  }

  function updateProject(nextProject) {
    setProject(nextProject)
    setUnsaved(true)
    refreshAnalytics(nextProject)
  }

  // Kept for legacy call-sites inside event handlers
  async function saveProject(nextProject) {
    updateProject(nextProject)
    return nextProject
  }

  // App starts empty — no auto-load
  useEffect(() => {}, [])

  function onNewProject() {
    if (unsaved && !window.confirm('Há alterações não salvas. Criar novo projeto vai descartá-las. Continuar?')) return
    setProject(null)
    setAnalytics(null)
    setVideoSrc('')
    setLoopRange({ active: false, startFrame: 0, endFrame: 0 })
    setPendingStartFrame(null)
    setLoopIndex(-1)
    setImportedRois(null)
    setMetaFps(30)
    setMetaTakt(10)
    setUnsaved(false)
    setProjectFileName(null)
    setError('')
  }

  async function onOpenProject(ev) {
    const file = ev.target.files?.[0]
    if (!file) return
    if (unsaved && !window.confirm('Há alterações não salvas. Abrir outro projeto vai descartá-las. Continuar?')) {
      ev.target.value = ''; return
    }
    setBusy(true)
    setError('')
    try {
      const parsed = JSON.parse(await file.text())

      setVideoSrc('')
      setLoopRange({ active: false, startFrame: 0, endFrame: 0 })
      setPendingStartFrame(null)
      setLoopIndex(-1)

      setProject(parsed)
      setProjectFileName(file.name)
      setUnsaved(false)
      setMetaFps(parsed.meta?.fps ?? 30)
      setMetaTakt(parsed.meta?.takt_time ?? 10)
      setImportedRois(Array.isArray(parsed.rois) && parsed.rois.length > 0 ? parsed.rois : null)

      await refreshAnalytics(parsed)

      // Tenta recarregar o vídeo automaticamente
      const videoPath     = parsed.meta?.video_path
      const videoFilename = parsed.meta?.video_filename
      if (videoPath || videoFilename) {
        let loaded = false
        if (videoPath) {
          try {
            const testUrl = `/api/projects/video-by-path?path=${encodeURIComponent(videoPath)}`
            if ((await fetch(testUrl, { method: 'HEAD' })).ok) {
              setVideoSrc(testUrl)
              loaded = true
            }
          } catch { /* fall through */ }
        }
        if (!loaded && videoFilename) {
          try {
            const match = (await apiGet('/api/projects/videos')).find(v => v.name === videoFilename)
            if (match) {
              setVideoSrc(match.url)
              loaded = true
            }
          } catch { /* fall through */ }
        }
        if (!loaded) {
          setError(`Vídeo "${videoFilename ?? videoPath}" não encontrado.\nCarregue o vídeo manualmente.`)
        }
      }
    } catch (e) {
      setError(e.message ?? String(e))
    } finally {
      setBusy(false)
      ev.target.value = ''
    }
  }

  async function onSaveProject() {
    setBusy(true)
    setError('')
    try {
      const currentRois = analyzerRef.current?.getRois?.() ?? []
      const base = project ?? { meta: { fps: metaFps, total_frames: 0, takt_time: metaTakt }, events: [] }
      const toSave = { ...base, rois: currentRois }
      const blob = new Blob([JSON.stringify(toSave, null, 2)], { type: 'application/json' })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = projectFileName ?? 'projeto.cta.json'
      a.click()
      URL.revokeObjectURL(url)
      setProject(toSave)
      setUnsaved(false)
    } catch (e) {
      setError(e.message ?? String(e))
    } finally {
      setBusy(false)
    }
  }

  // Upload video to backend (for future re-opens), but keep the blob: URL
  // active for this session — do NOT switch videoSrc to the backend URL.
  function persistVideoMeta(blobUrl, file, detectedFps, totalFrames) {
    const formData = new FormData()
    formData.append('file', file)
    fetch('/api/projects/videos/upload', { method: 'POST', body: formData })
      .then((r) => r.ok ? r.json() : null)
      .then((result) => {
        setProject((prev) => {
          const base = prev ?? { meta: { fps: detectedFps, total_frames: totalFrames, takt_time: metaTakt }, events: [], rois: [] }
          const nextProject = {
            ...base,
            meta: {
              ...base.meta,
              fps: detectedFps,
              total_frames: totalFrames,
              takt_time: base.meta?.takt_time ?? metaTakt,
              ...(result ? { video_filename: result.name, video_path: result.absolute_path } : {}),
            },
          }
          refreshAnalytics(nextProject)
          return nextProject
        })
        setUnsaved(true)
        // blob: URL stays in videoSrc — no setVideoSrc() call here
      })
      .catch(() => {
        setProject((prev) => {
          const base = prev ?? { meta: { fps: detectedFps, total_frames: totalFrames, takt_time: metaTakt }, events: [], rois: [] }
          const nextProject = { ...base, meta: { ...base.meta, fps: detectedFps, total_frames: totalFrames } }
          refreshAnalytics(nextProject)
          return nextProject
        })
        setUnsaved(true)
      })
  }

  // Persist FPS / takt time edits immediately
  const applyMeta = useCallback((patch) => {
    const newFps  = patch.fps  ?? metaFps
    const newTakt = patch.takt ?? metaTakt
    if (patch.fps  !== undefined) setMetaFps(newFps)
    if (patch.takt !== undefined) setMetaTakt(newTakt)
    const base = project ?? { meta: { fps: newFps, total_frames: 0, takt_time: newTakt }, events: [] }
    const next = { ...base, meta: { ...base.meta, fps: newFps, takt_time: newTakt } }
    updateProject(next)
  }, [project, metaFps, metaTakt]) // eslint-disable-line react-hooks/exhaustive-deps

  // ── shared input style (used in settings panel) ──────────────────────────
  const inputStyle = {
    padding: '0.25rem 0.4rem',
    borderRadius: '0.35rem',
    border: '1px solid #2a2a2a',
    background: '#111',
    color: '#e0e0e0',
    fontSize: '0.82rem',
  }

  return (
    <div style={{ width: '100%', height: '100vh', boxSizing: 'border-box', display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>

      {/* ── Header ──────────────────────────────────────────────────────────── */}
      <header style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '0.5rem', flexWrap: 'wrap', padding: '0.5rem 0.75rem', borderBottom: '1px solid #1a1a1a' }}>

        {/* Left: brand + status */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem' }}>
          <h1 style={{ margin: 0, fontSize: '1.05rem', lineHeight: 1.2, fontWeight: 700, display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
            <Timer size={16} strokeWidth={2} />Cycle Time Analysis
          </h1>
          {busy && <span style={{ fontSize: '0.72rem', color: '#666' }}>Processando…</span>}
          {!busy && unsaved && <span style={{ fontSize: '0.72rem', color: '#c8a02a' }}>● Não salvo</span>}
          {!busy && !unsaved && projectFileName && <span style={{ fontSize: '0.72rem', color: '#666' }}>{projectFileName}</span>}
        </div>

        {/* Center: file / input actions */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
          <button style={{ ...hBtn(), display: "flex", alignItems: "center", gap: "0.35rem" }} onClick={onNewProject}>
            <FilePlus size={14} strokeWidth={2} /> Novo
          </button>
          <label style={{ ...hBtn(), display: "flex", alignItems: "center", gap: "0.35rem" }}>
            <FolderOpen size={14} strokeWidth={2} /> Abrir projeto
            <input type="file" accept="application/json,.cta.json" onChange={onOpenProject} style={{ display: 'none' }} />
          </label>
          <button style={{ ...hBtn(), display: "flex", alignItems: "center", gap: "0.35rem" }} onClick={onSaveProject} disabled={busy}>
            <Save size={14} strokeWidth={2} /> {unsaved ? 'Salvar *' : 'Salvar'}
          </button>
          <button
            style={{ ...hBtn(trackingMode === 'tracking'), display: "flex", alignItems: "center", gap: "0.35rem" }}
            onClick={() => setTrackingMode(m => m === 'manual' ? 'tracking' : 'manual')}
            title={trackingMode === 'tracking' ? 'Modo: Rastreamento (clique para manual)' : 'Modo: Manual (clique para rastreamento)'}
          >
            {trackingMode === 'tracking' ? '🤖 Rastreamento' : '✏️ Manual'}
          </button>
          <label style={{ ...hBtn(), display: "flex", alignItems: "center", gap: "0.35rem" }}>
            <FolderOpen size={14} strokeWidth={2} /> Carregar vídeo
            <input
              ref={filePickerRef}
              type="file"
              accept="video/*"
              onChange={(e) => {
                const file = e.target.files?.[0]
                if (!file) return
                const url = URL.createObjectURL(file)
                setVideoSrc(url)
                setLoopRange({ active: false, startFrame: 0, endFrame: 0 })
                setPendingStartFrame(null)
                setLoopIndex(-1)
                setError('')
                e.target.value = ''

                const probeVideo = document.createElement('video')
                probeVideo.src = url
                probeVideo.muted = true
                probeVideo.preload = 'auto'

                probeVideo.addEventListener('loadedmetadata', () => {
                  const duration = probeVideo.duration || 0

                  if (typeof probeVideo.requestVideoFrameCallback === 'function') {
                    let frameCount = 0
                    let startTime = null
                    const sampleDuration = Math.min(2, duration)

                    const tick = (_now, meta) => {
                      if (startTime === null) startTime = meta.mediaTime
                      frameCount++
                      const elapsed = meta.mediaTime - startTime
                      if (elapsed < sampleDuration && meta.mediaTime < duration - 0.1) {
                        probeVideo.requestVideoFrameCallback(tick)
                      } else {
                        // Manter precisão total — não arredondar para inteiro.
                        // Math.round(29.97) = 30 causaria erro acumulado nos timestamps.
                        const detectedFps = elapsed > 0 ? frameCount / elapsed : metaFps
                        const safeDetectedFps = detectedFps >= 1 && detectedFps <= 240 ? detectedFps : metaFps
                        const totalFrames = Math.round(duration * safeDetectedFps)
                        setMetaFps(safeDetectedFps)
                        persistVideoMeta(url, file, safeDetectedFps, totalFrames)
                        probeVideo.pause()
                      }
                    }
                    probeVideo.requestVideoFrameCallback(tick)
                    probeVideo.play().catch(() => {})
                  } else {
                    const totalFrames = Math.round(duration * metaFps)
                    persistVideoMeta(url, file, metaFps, totalFrames)
                  }
                }, { once: true })
              }}
              style={{ display: 'none' }}
            />
          </label>
          <button style={{ ...hBtn(cameraMode), display: "flex", alignItems: "center", gap: "0.35rem" }} onClick={() => setCameraMode((v) => !v)}>
            <Camera size={14} strokeWidth={2} /> {cameraMode ? 'Fechar câmera' : 'Câmera'}
          </button>
        </div>

        {/* Right: project actions */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
          <button style={{ ...hBtn(showSettings), display: "flex", alignItems: "center", gap: "0.35rem" }} onClick={() => setShowSettings((v) => !v)}>
            <Settings size={14} strokeWidth={2} /> Config
          </button>
          <button style={{ ...hBtn(activeTab === 'dashboard'), display: "flex", alignItems: "center", gap: "0.35rem" }} onClick={() => setActiveTab((t) => (t === 'dashboard' ? 'editor' : 'dashboard'))}>
            <BarChart2 size={14} strokeWidth={2} /> Dashboard
          </button>
        </div>
      </header>

      {/* ── Settings panel (collapsible) ─────────────────────────────────── */}
      {showSettings && (
        <div style={{ padding: '0.45rem 0.75rem', background: '#0d0d0d', borderBottom: '1px solid #1a1a1a', display: 'flex', gap: '1.5rem', flexWrap: 'wrap', alignItems: 'center' }}>
          <label style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', fontSize: '0.82rem', color: '#aaa' }}>
            FPS:
            <input
              type="number" min="1" max="120"
              value={metaFps}
              onChange={(e) => setMetaFps(Number(e.target.value))}
              onBlur={(e) => applyMeta({ fps: Number(e.target.value) })}
              style={{ width: '4rem', ...inputStyle }}
            />
          </label>
          <label style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', fontSize: '0.82rem', color: '#aaa' }}>
            Takt time (s):
            <input
              type="number" min="0" step="0.1"
              value={metaTakt}
              onChange={(e) => setMetaTakt(Number(e.target.value))}
              onBlur={(e) => applyMeta({ takt: Number(e.target.value) })}
              style={{ width: '5rem', ...inputStyle }}
            />
          </label>
          <button style={{ ...hBtn(), fontSize: '0.75rem' }} onClick={() => setShowSettings(false)}><X size={13} strokeWidth={2} /> Fechar</button>
        </div>
      )}

      {/* ── Error banner ─────────────────────────────────────────────────── */}
      {error && (
        <div style={{ margin: '0.4rem 0.75rem', padding: '0.5rem 0.65rem', borderRadius: '0.5rem', border: '1px solid #4b1d1d', background: '#2a1212', color: '#ffb4b4', fontSize: '0.82rem', whiteSpace: 'pre-wrap' }}>
          {error}
        </div>
      )}

      {/* ── Pre-process progress (persistent while running) ──────────────── */}
      {videoSrc && trackingMode === 'tracking' && (preprocessStatus === 'uploading' || preprocessStatus === 'processing') && (
        <div style={{ margin: '0 0.75rem 0.2rem', display: 'flex', flexDirection: 'column', gap: '0.15rem' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.72rem', color: '#888' }}>
            <span style={{ display: "flex", alignItems: "center", gap: "0.35rem" }}>
              {preprocessStatus === 'uploading' ? '📤 Enviando vídeo ao backend…' : '⏳ Processando com MediaPipe (Python)…'}
            </span>
            <span>{Math.round(preprocessProgress * 100)}%</span>
          </div>
          <div style={{ height: '3px', borderRadius: '2px', background: '#222', overflow: 'hidden' }}>
            <div style={{ height: '100%', width: `${Math.round(preprocessProgress * 100)}%`, background: 'linear-gradient(90deg,#1a6b2a,#2ca02c)', transition: 'width 0.2s ease', borderRadius: '2px' }} />
          </div>
        </div>
      )}

      {/* ── Toast notifications (auto-dismiss) ───────────────────────────── */}
      {preprocessToast === 'done' && (
        <div style={{ margin: '0 0.75rem 0.2rem', padding: '0.3rem 0.6rem', borderRadius: '0.4rem', background: 'rgba(44,160,44,0.12)', border: '1px solid rgba(44,160,44,0.35)', color: '#6fcf6f', fontSize: '0.72rem', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <span style={{ display: "flex", alignItems: "center", gap: "0.4rem" }}><CheckCircle size={13} strokeWidth={2} /> Pré-processamento concluído — detecção via cache activa</span>
          <button onClick={() => setPreprocessToast(null)} style={{ background: 'none', border: 'none', color: '#6fcf6f', cursor: 'pointer', lineHeight: 1, padding: '0 0.2rem', display: 'flex', alignItems: 'center' }}><X size={13} strokeWidth={2} /></button>
        </div>
      )}
      {preprocessToast === 'error' && (
        <div style={{ margin: '0 0.75rem 0.2rem', padding: '0.3rem 0.6rem', borderRadius: '0.4rem', background: 'rgba(255,127,14,0.1)', border: '1px solid rgba(255,127,14,0.4)', color: '#ffb347', fontSize: '0.72rem', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <span style={{ display: "flex", alignItems: "center", gap: "0.4rem" }}><AlertTriangle size={13} strokeWidth={2} /> Pré-processamento falhou — a usar detecção em tempo real</span>
          <button onClick={() => setPreprocessToast(null)} style={{ background: 'none', border: 'none', color: '#ffb347', cursor: 'pointer', lineHeight: 1, padding: '0 0.2rem', display: 'flex', alignItems: 'center' }}><X size={13} strokeWidth={2} /></button>
        </div>
      )}

      {/* ── Main work area ───────────────────────────────────────────────── */}
      <main style={{ flex: 1, minHeight: 0, overflow: 'hidden', display: 'flex', flexDirection: 'column' }}>
        {/* ── DASHBOARD TAB ── */}
        {activeTab === 'dashboard' && (
          <div style={{ flex: 1, minHeight: 0, padding: 'var(--cta-pad)', display: 'flex', flexDirection: 'column' }}>
            <h2 style={{ margin: '0 0 0.5rem', fontSize: '1rem', display: 'flex', alignItems: 'center', gap: '0.4rem' }}><BarChart2 size={16} strokeWidth={2} /> Dashboard de Análises</h2>
            <div style={{ flex: 1, minHeight: 0 }}>
              <Dashboard
                events={project?.events ?? []}
                taktTime={project?.meta?.takt_time ?? 0}
                fps={fps}
              />
            </div>
          </div>
        )}

        {/* ── EDITOR TAB ── */}
        {activeTab === 'editor' && (
        <section
          className="cta-app-panels"
          style={{
            flex: 1,
            minHeight: 0,
            minWidth: 0,
            display: 'grid',
            gridTemplateColumns: 'minmax(0, 1.25fr) minmax(0, 0.75fr)',
            gap: 'var(--cta-gap)',
            alignItems: 'stretch',
            padding: 'var(--cta-pad)',
          }}
        >
          {/* LEFT: title + event editor. Only the table scrolls (inside EventEditor). */}
          <div style={{ minHeight: 0, display: 'flex', flexDirection: 'column' }}>
            <h2 style={{ margin: '0 0 0.5rem', fontSize: '1rem' }}>Editor de eventos</h2>
            <div style={{ minHeight: 0, flex: 1 }}>
              <EventEditor
                fps={fps}
                events={project?.events ?? []}
                pendingStartFrame={pendingStartFrame}
                loopIndex={loopIndex}
                tableMaxHeight={'100%'}
                onSeekStart={(frame) => {
                  setError('')
                  playerRef.current?.seekToFrame?.(Number(frame))
                }}
                onSeekEnd={(frame) => {
                  setError('')
                  playerRef.current?.seekToFrame?.(Number(frame))
                }}
                onLoopIndexChange={(idx) => {
                  setLoopIndex(idx)

                  if (idx < 0) {
                    setLoopRange({ active: false, startFrame: 0, endFrame: 0 })
                    return
                  }

                  const e = (project?.events ?? [])[idx]
                  if (!e) return
                  setLoopRange({ active: true, startFrame: e.start_frame, endFrame: e.end_frame })

                  playerRef.current?.seekToFrame?.(Number(e.start_frame))
                  playerRef.current?.play?.()
                }}
                onChange={(nextEvents) => {
                  const nextProject = {
                    ...(project ?? { meta: { fps, total_frames: 0, takt_time: 10 }, events: [] }),
                    meta: {
                      ...(project?.meta ?? { fps, total_frames: 0, takt_time: 10 }),
                      fps,
                    },
                    events: nextEvents,
                  }
                  updateProject(nextProject)
                }}
                onCreateFromRange={(startFrame, endFrame) => {
                  const duration = fps > 0 ? (endFrame - startFrame) / fps : 0
                  const newEvent = {
                    operation: 'Nova Operação',
                    start_frame: startFrame,
                    end_frame: endFrame,
                    duration: Number(duration.toFixed(6)),
                    category: '',
                    object: 'Objeto',
                    resource: 'Recurso',
                  }
                  const nextProject = {
                    ...(project ?? { meta: { fps, total_frames: 0, takt_time: 10 }, events: [] }),
                    meta: {
                      ...(project?.meta ?? { fps, total_frames: 0, takt_time: 10 }),
                      fps,
                    },
                    events: [...(project?.events ?? []), newEvent],
                  }
                  updateProject(nextProject)
                }}
              />
            </div>
          </div>

          {/* RIGHT: video and tools split vertically but column height matches left. */}
          <div
            style={{
              minHeight: 0,
              display: 'flex',
              flexDirection: 'column',
              justifyContent: 'flex-end',
            }}
          >
            <h2 style={{ margin: '0 0 0.5rem', fontSize: '1rem' }}>
              {cameraMode ? 'Câmera ao vivo' : 'Vídeo'}
            </h2>
            {/* Video area grows; tools keep natural height at the bottom. */}
            <div style={{ minHeight: 0, flex: 1, display: 'flex' }}>
              <div
                style={{
                  border: '1px solid #2a2a2a',
                  borderRadius: '0.75rem',
                  padding: '0.75rem',
                  background: '#0b0b0b',
                  width: '100%',
                  display: 'flex',
                  minHeight: 0,
                }}
              >
                {cameraMode ? (
                  <CameraView
                    fps={fps}
                    onCreateEvent={(newEvent) => {
                      const currentProject = project ?? {
                        meta: { fps, total_frames: 0, takt_time: 10 },
                        events: [],
                      }
                      const nextProject = {
                        ...currentProject,
                        events: [...(currentProject.events ?? []), newEvent],
                      }
                      updateProject(nextProject)
                    }}
                  />
                ) : (
                <div style={{ position: 'relative', width: '100%', minHeight: 0, display: 'flex', flexDirection: 'column' }}>
                  {/* Single <video> element — shared by VideoPlayer controls and VideoAnalyzer */}
                  <VideoCanvas
                    videoRef={videoRef}
                    src={videoSrc}
                    maxHeight={'100%'}
                  />
                  {/* Analyzer overlay sits on top of the video, absolutely positioned */}
                  {videoSrc && trackingMode === 'tracking' && (
                    <div style={{ position: 'absolute', inset: 0, pointerEvents: 'none' }}>
                      <VideoAnalyzer
                        ref={analyzerRef}
                        videoRef={videoRef}
                        src={videoSrc}
                        fps={fps}
                        preprocessCache={preprocessCacheRef}
                        preprocessStatus={preprocessStatus}
                        initialRois={importedRois}
                        onRoisChange={(nextRois) => {
                          setProject((prev) => {
                            const base = prev ?? { meta: { fps, total_frames: 0, takt_time: metaTakt }, events: [], rois: [] }
                            return { ...base, rois: nextRois }
                          })
                          setUnsaved(true)
                        }}
                        onCreateEvent={(newEvent) => {
                          const currentProject = project ?? {
                            meta: { fps, total_frames: 0, takt_time: 10 },
                            events: [],
                          }
                          const nextProject = {
                            ...currentProject,
                            events: [...(currentProject.events ?? []), newEvent],
                          }
                          updateProject(nextProject)
                        }}
                        loopRange={loopRange}
                        events={project?.events ?? []}
                      />
                    </div>
                  )}
                </div>
                )}
              </div>
            </div>

            {/* Push tools to the bottom of the right column while keeping the whole column same height as left. */}
            <div
              style={{
                marginTop: 'auto',
                minHeight: '35%',
                flex: '0 0 auto',
                display: 'flex',
                flexDirection: 'column',
                alignSelf: 'stretch',
              }}
            >
              <h2 style={{ margin: '0.75rem 0 0.5rem', fontSize: '1rem' }}>Ferramentas de vídeo</h2>
              <div style={{ minHeight: 0 }}>
                <VideoPlayer
                  ref={playerRef}
                  fps={fps}
                  externalSrc={videoSrc}
                  externalVideoRef={videoRef}
                  loopRange={loopRange}
                  onLoopRangeChange={(lr) => setLoopRange(lr)}
                  layout="controls"
                  onMarkStart={(frame) => {
                    setPendingStartFrame(frame)
                  }}
                  onMarkEnd={(frame) => {
                    if (pendingStartFrame == null) {
                      setError('Marque o início primeiro.')
                      return
                    }
                    if (frame <= pendingStartFrame) {
                      setError('O frame de fim deve ser maior que o de início.')
                      return
                    }

                    const duration = fps > 0 ? (frame - pendingStartFrame) / fps : 0
                    const newEvent = {
                      operation: 'Nova Operação',
                      start_frame: pendingStartFrame,
                      end_frame: frame,
                      duration: Number(duration.toFixed(6)),
                      category: '',
                      object: 'Objeto',
                      resource: 'Recurso',
                    }

                    setError('')
                    setPendingStartFrame(null)

                    const nextProject = {
                      ...(project ?? { meta: { fps, total_frames: 0, takt_time: 10 }, events: [] }),
                      meta: {
                        ...(project?.meta ?? { fps, total_frames: 0, takt_time: 10 }),
                        fps,
                      },
                      events: [...(project?.events ?? []), newEvent],
                    }

                    updateProject(nextProject)
                  }}
                />
              </div>
            </div>
          </div>
        </section>
        )}

        {/* Responsive (no JS): when the viewport gets narrow, stack panels. */}
        <style>{`
          @media (max-width: 70rem) {
            .cta-app-panels { grid-template-columns: 1fr !important; }
          }
        `}</style>
      </main>

      {/* ── Footer ───────────────────────────────────────────────────────── */}
      <footer style={{ padding: '0.3rem 0.75rem', color: '#555', fontSize: '0.72rem', borderTop: '1px solid #1a1a1a', display: 'flex', gap: '1.25rem', alignItems: 'center' }}>
        <span>FPS: <b style={{ color: '#888' }}>{fps}</b></span>
        <span>Takt: <b style={{ color: '#888' }}>{metaTakt}s</b></span>
        <span>Eventos: <b style={{ color: '#888' }}>{project?.events?.length ?? 0}</b></span>
        {project?.meta?.total_frames > 0 && (
          <span>Frames: <b style={{ color: '#888' }}>{project.meta.total_frames}</b></span>
        )}
        {project?.rois?.length > 0 && (
          <span>ROIs: <b style={{ color: '#888' }}>{project.rois.length}</b></span>
        )}
        {videoSrc && <span style={{ color: '#444' }}>● Vídeo carregado</span>}
      </footer>
    </div>
  )
}

export default App

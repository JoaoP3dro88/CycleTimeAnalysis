import './App.css'

import { useEffect, useMemo, useRef, useState, useCallback } from 'react'
import {
  Timer, FolderOpen, Download, Camera, Upload,
  Settings, Trash2, BarChart2, X,
  CheckCircle, AlertTriangle, Cpu,
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
  const videoStateRef = useRef({ videoRef: { current: null }, src: '' })
  const filePickerRef = useRef(null)
  const analyzerRef  = useRef(null)

  const [project,    setProject]    = useState(null)
  const [analytics,  setAnalytics]  = useState(null)
  const [error,      setError]      = useState('')
  const [busy,       setBusy]       = useState(false)
  const [initDone,   setInitDone]   = useState(false)   // first load complete
  const [pendingStartFrame, setPendingStartFrame] = useState(null)
  const [loopIndex,  setLoopIndex]  = useState(-1)
  const [loopRange,  setLoopRange]  = useState({ active: false, startFrame: 0, endFrame: 0 })
  const [cameraMode, setCameraMode] = useState(false)
  const [videoSrc,   setVideoSrc]   = useState('')
  const [activeTab,  setActiveTab]  = useState('editor') // 'editor' | 'dashboard'
  const [showSettings, setShowSettings] = useState(false)
  const [importedRois, setImportedRois] = useState(null) // ROIs restored from a JSON import

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
  } = useVideoPreprocess({ src: videoSrc, fps })

  // Show a toast when preprocess finishes or fails, then auto-dismiss
  useEffect(() => {
    if (preprocessStatus === 'done' || preprocessStatus === 'error') {
      setPreprocessToast(preprocessStatus)
      clearTimeout(toastTimerRef.current)
      toastTimerRef.current = setTimeout(() => setPreprocessToast(null), 5000)
    }
    if (preprocessStatus === 'processing') setPreprocessToast(null)
  }, [preprocessStatus])

  async function refreshAll() {
    setBusy(true)
    setError('')
    try {
      const p = await apiGet('/api/projects/current')
      setProject(p)
      const a = await apiGet('/api/analytics/current')
      setAnalytics(a)
    } catch (e) {
      setError(e.message ?? String(e))
    } finally {
      setBusy(false)
      setInitDone(true)
    }
  }

  async function saveProject(nextProject) {
    // Persist whole project (simple and reliable for now)
    const saved = await apiPost('/api/projects/import', nextProject)
    setProject(saved)
    const a = await apiGet('/api/analytics/current')
    setAnalytics(a)
  }

  useEffect(() => {
    ;(async () => {
      // Option A: always start from zero when opening the app.
      try {
        await apiPost('/api/projects/reset', {})
      } catch {
        // If the backend is old or temporarily unavailable, fall back to loading whatever exists.
      }
      refreshAll()
    })()
  }, [])

  async function onResetProject() {
    if (!window.confirm('Zerar o projecto apaga todos os eventos. Continuar?')) return
    setBusy(true)
    setError('')
    try {
      await apiPost('/api/projects/reset', {})
      await refreshAll()
      setLoopRange({ active: false, startFrame: 0, endFrame: 0 })
      setPendingStartFrame(null)
      setLoopIndex(-1)
    } catch (e) {
      setError(e.message ?? String(e))
    } finally {
      setBusy(false)
    }
  }

  async function onImportJsonFile(ev) {
    const file = ev.target.files?.[0]
    if (!file) return

    setBusy(true)
    setError('')
    try {
      const text = await file.text()
      const parsed = JSON.parse(text)
      await saveProject(parsed)

      // ── Restore ROIs ─────────────────────────────────────────────────────
      if (Array.isArray(parsed.rois) && parsed.rois.length > 0) {
        setImportedRois(parsed.rois)
      }

      // ── Try to auto-load the video ────────────────────────────────────────
      const videoPath     = parsed.meta?.video_path      // absolute path on this machine
      const videoFilename = parsed.meta?.video_filename  // basename fallback

      if (videoPath || videoFilename) {
        let loaded = false

        // 1st try: serve directly from absolute path (works when the file is
        //          still on the same machine where it was originally loaded).
        if (videoPath) {
          try {
            const testUrl = `/api/projects/video-by-path?path=${encodeURIComponent(videoPath)}`
            const res = await fetch(testUrl, { method: 'HEAD' })
            if (res.ok) {
              videoStateRef.current.src = testUrl
              setVideoSrc(testUrl)
              setLoopRange({ active: false, startFrame: 0, endFrame: 0 })
              setPendingStartFrame(null)
              setLoopIndex(-1)
              loaded = true
            }
          } catch { /* fall through */ }
        }

        // 2nd try: look in data/videos/ by filename (file was uploaded before)
        if (!loaded && videoFilename) {
          try {
            const videos = await apiGet('/api/projects/videos')
            const match = videos.find((v) => v.name === videoFilename)
            if (match) {
              videoStateRef.current.src = match.url
              setVideoSrc(match.url)
              setLoopRange({ active: false, startFrame: 0, endFrame: 0 })
              setPendingStartFrame(null)
              setLoopIndex(-1)
              loaded = true
            }
          } catch { /* fall through */ }
        }

        // Nothing worked — ask the user to locate the file manually
        if (!loaded) {
          setError(
            `Vídeo "${videoFilename ?? videoPath}" não encontrado.\n` +
            `Carregue o vídeo manualmente usando o botão "Carregar vídeo".`
          )
        }
      }
    } catch (e) {
      setError(e.message ?? String(e))
    } finally {
      setBusy(false)
      ev.target.value = ''
    }
  }

  async function onExportJson() {
    setBusy(true)
    setError('')
    try {
      // Grab current ROIs from the analyzer and persist them first
      const currentRois = analyzerRef.current?.getRois?.() ?? []
      const baseProject = project ?? { meta: { fps: metaFps, total_frames: 0, takt_time: metaTakt }, events: [] }
      const withRois = { ...baseProject, rois: currentRois }
      await saveProject(withRois)

      const p = await apiGet('/api/projects/export')
      const blob = new Blob([JSON.stringify(p, null, 2)], { type: 'application/json' })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url; a.download = 'project.json'; a.click()
      URL.revokeObjectURL(url)
    } catch (e) {
      setError(e.message ?? String(e))
    } finally {
      setBusy(false)
    }
  }

  // Persist FPS / takt time edits immediately
  const applyMeta = useCallback((patch) => {
    const newFps  = patch.fps  ?? metaFps
    const newTakt = patch.takt ?? metaTakt
    if (patch.fps  !== undefined) setMetaFps(newFps)
    if (patch.takt !== undefined) setMetaTakt(newTakt)
    const base = project ?? { meta: { fps: newFps, total_frames: 0, takt_time: newTakt }, events: [] }
    const next = { ...base, meta: { ...base.meta, fps: newFps, takt_time: newTakt } }
    setProject(next)
    saveProject(next).catch((e) => setError(e.message ?? String(e)))
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
            <Timer size={16} strokeWidth={2} /> Cycle Time Analysis
          </h1>
          {!initDone && <span style={{ fontSize: '0.72rem', color: '#666' }}>Carregando…</span>}
          {initDone && busy && <span style={{ fontSize: '0.72rem', color: '#666' }}>Salvando…</span>}
        </div>

        {/* Center: file / input actions */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
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
                videoStateRef.current.src = url
                setVideoSrc(url)
                setLoopRange({ active: false, startFrame: 0, endFrame: 0 })
                setPendingStartFrame(null)
                setLoopIndex(-1)
                setError('')
                e.target.value = ''

                // Upload video to backend so the absolute path is known and
                // future imports can serve the file directly from disk.
                const formData = new FormData()
                formData.append('file', file)
                fetch('/api/projects/videos/upload', { method: 'POST', body: formData })
                  .then((r) => r.ok ? r.json() : null)
                  .then((result) => {
                    if (!result) return
                    // Persist video_path (absolute) + video_filename into meta
                    const nextProject = {
                      ...(project ?? { meta: { fps: metaFps, total_frames: 0, takt_time: metaTakt }, events: [], rois: [] }),
                      meta: {
                        ...(project?.meta ?? {}),
                        fps: metaFps,
                        takt_time: metaTakt,
                        video_filename: result.name,
                        video_path: result.absolute_path,
                      },
                    }
                    saveProject(nextProject).catch(() => {})
                  })
                  .catch(() => {/* non-fatal — local blob still works */})
              }}
              style={{ display: 'none' }}
            />
          </label>
          <label style={{ ...hBtn(), display: "flex", alignItems: "center", gap: "0.35rem" }}>
            <Download size={14} strokeWidth={2} /> Importar JSON
            <input type="file" accept="application/json" onChange={onImportJsonFile} style={{ display: 'none' }} />
          </label>
          <button style={{ ...hBtn(cameraMode), display: "flex", alignItems: "center", gap: "0.35rem" }} onClick={() => setCameraMode((v) => !v)}>
            <Camera size={14} strokeWidth={2} /> {cameraMode ? 'Fechar câmera' : 'Câmera'}
          </button>
        </div>

        {/* Right: project actions */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
          <button style={{ ...hBtn(), display: "flex", alignItems: "center", gap: "0.35rem" }} onClick={onExportJson} disabled={busy}>
            <Upload size={14} strokeWidth={2} /> Exportar
          </button>
          <button style={{ ...hBtn(showSettings), display: "flex", alignItems: "center", gap: "0.35rem" }} onClick={() => setShowSettings((v) => !v)}>
            <Settings size={14} strokeWidth={2} /> Config
          </button>
          <button style={{ ...hBtn(false, true), display: "flex", alignItems: "center", gap: "0.35rem" }} onClick={onResetProject} disabled={busy}>
            <Trash2 size={14} strokeWidth={2} /> Resetar
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
      {videoSrc && preprocessStatus === 'processing' && (
        <div style={{ margin: '0 0.75rem 0.2rem', display: 'flex', flexDirection: 'column', gap: '0.15rem' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.72rem', color: '#888' }}>
            <span style={{ display: "flex", alignItems: "center", gap: "0.35rem" }}><Cpu size={13} strokeWidth={2} /> Pré-processando com MediaPipe…</span>
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

                  setProject(nextProject)
                  setBusy(true)
                  saveProject(nextProject)
                    .catch((e) => setError(e.message ?? String(e)))
                    .finally(() => setBusy(false))
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
                  setBusy(true)
                  saveProject(nextProject)
                    .catch((e) => setError(e.message ?? String(e)))
                    .finally(() => setBusy(false))
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
                      setBusy(true)
                      saveProject(nextProject)
                        .catch((e) => setError(e.message ?? String(e)))
                        .finally(() => setBusy(false))
                    }}
                  />
                ) : (
                <div style={{ position: 'relative', width: '100%', minHeight: 0, display: 'flex', flexDirection: 'column' }}>
                  {/* Video fills all available space */}
                  <VideoCanvas
                    videoRef={videoStateRef.current.videoRef}
                    src={videoStateRef.current.src}
                    maxHeight={'100%'}
                  />
                  {/* Analyzer overlays sit on top of the video, absolutely positioned */}
                  {videoSrc && (
                    <div style={{ position: 'absolute', inset: 0, pointerEvents: 'none' }}>
                      <VideoAnalyzer
                        ref={analyzerRef}
                        videoRef={videoStateRef.current.videoRef}
                        src={videoSrc}
                        fps={fps}
                        preprocessCache={preprocessCacheRef}
                        initialRois={importedRois}
                        onCreateEvent={(newEvent) => {
                          const currentProject = project ?? {
                            meta: { fps, total_frames: 0, takt_time: 10 },
                            events: [],
                          }
                          const nextProject = {
                            ...currentProject,
                            events: [...(currentProject.events ?? []), newEvent],
                          }
                          setBusy(true)
                          saveProject(nextProject)
                            .catch((e) => setError(e.message ?? String(e)))
                            .finally(() => setBusy(false))
                        }}
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
                  externalSrc={videoStateRef.current.src}
                  loopRange={loopRange}
                  onLoopRangeChange={(lr) => setLoopRange(lr)}
                  layout="controls"
                  renderVideo={({ videoRef, src, isReady: vReady }) => {
                    // Critical: keep the VideoPlayer's internal <video> ref pointing to
                    // the same DOM element used by the canvas. Otherwise isReady never
                    // becomes true and all controls stay disabled.
                    videoStateRef.current.videoRef = videoRef
                    const nextSrc = videoStateRef.current.src || src
                    videoStateRef.current.src = nextSrc
                    // Sync ready state for VideoAnalyzer (no-op: VideoAnalyzer self-detects readiness)
                    if (videoRef?.current && videoRef.current.src !== nextSrc) {
                      videoRef.current.src = nextSrc
                      // Critical on some browsers: setting .src directly doesn't always
                      // trigger a metadata load unless we call load().
                      try {
                        videoRef.current.pause?.()
                        videoRef.current.currentTime = 0
                        videoRef.current.load?.()
                      } catch {
                        // ignore
                      }
                    }
                    return null
                  }}
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

                    setBusy(true)
                    saveProject(nextProject)
                      .catch((e) => setError(e.message ?? String(e)))
                      .finally(() => setBusy(false))
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
        {videoSrc && <span style={{ color: '#444' }}>● Vídeo carregado</span>}
      </footer>
    </div>
  )
}

export default App

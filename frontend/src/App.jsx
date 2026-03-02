import './App.css'

import { useEffect, useMemo, useRef, useState } from 'react'
import EventEditor from './components/EventEditor'
import VideoPlayer, { VideoCanvas } from './components/VideoPlayer'
import CameraView from './components/CameraView'
import VideoAnalyzer from './components/VideoAnalyzer'
import Dashboard from './components/Dashboard'
import { apiGet, apiPost } from './lib/api'

function App() {
  const playerRef = useRef(null)
  const videoStateRef = useRef({ videoRef: { current: null }, src: '' })
  const filePickerRef = useRef(null)
  const [project, setProject] = useState(null)
  const [analytics, setAnalytics] = useState(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [pendingStartFrame, setPendingStartFrame] = useState(null)
  const [loopIndex, setLoopIndex] = useState(-1)
  const [loopRange, setLoopRange] = useState({ active: false, startFrame: 0, endFrame: 0 })
  const [cameraMode, setCameraMode] = useState(false)
  const [videoSrc, setVideoSrc] = useState('')
  const [activeTab, setActiveTab] = useState('editor')  // 'editor' | 'dashboard'

  const fps = useMemo(() => project?.meta?.fps ?? 30, [project])

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
    setBusy(true)
    setError('')
    try {
      await apiPost('/api/projects/reset', {})
      await refreshAll()
      // Reset local player/editor transient state
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
      const p = await apiGet('/api/projects/export')
      const blob = new Blob([JSON.stringify(p, null, 2)], {
        type: 'application/json',
      })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = 'project.json'
      a.click()
      URL.revokeObjectURL(url)
    } catch (e) {
      setError(e.message ?? String(e))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div
      style={{
        width: '100%',
        height: '100vh',
        boxSizing: 'border-box',
        display: 'flex',
        flexDirection: 'column',
        overflow: 'hidden',
      }}
    >
      <header
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          gap: '0.75rem',
          flexWrap: 'wrap',
          padding: '0.75rem',
        }}
      >
        <div>
          <h1 style={{ margin: 0, fontSize: '1.25rem', lineHeight: 1.2 }}>Cycle Time Analysis</h1>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
          <label
            style={{
              padding: '0.6rem 0.75rem',
              borderRadius: '0.65rem',
              border: '1px solid #2a2a2a',
              background: '#111',
              cursor: 'pointer',
            }}
          >
            Importar JSON
            <input
              type="file"
              accept="application/json"
              onChange={onImportJsonFile}
              style={{ display: 'none' }}
            />
          </label>

          {/* Quick access like legacy: load video sits in the top bar */}
          <button
            onClick={() => filePickerRef.current?.click()}
            style={{
              padding: '0.6rem 0.75rem',
              borderRadius: '0.65rem',
              border: '1px solid #2a2a2a',
              background: '#111',
              cursor: 'pointer',
            }}
          >
            Carregar vídeo
          </button>

          <button
            onClick={() => setCameraMode((v) => !v)}
            style={{
              padding: '0.6rem 0.75rem',
              borderRadius: '0.65rem',
              border: cameraMode ? '1px solid #1a4a1a' : '1px solid #2a2a2a',
              background: cameraMode ? '#0d2e0d' : '#111',
              cursor: 'pointer',
            }}
            title={cameraMode ? 'Fechar câmera' : 'Abrir câmera com rastreamento de mãos'}
          >
            {cameraMode ? '📷 Fechar câmera' : '📷 Câmera'}
          </button>

          <input
            ref={filePickerRef}
            type="file"
            accept="video/*"
            onChange={(e) => {
              const file = e.target.files?.[0]
              if (!file) return
              const url = URL.createObjectURL(file)

              // Update the shared player state that powers the canvas.
              videoStateRef.current.src = url
              setVideoSrc(url)
              // Reset selection state inside VideoPlayer implicitly.
              setLoopRange({ active: false, startFrame: 0, endFrame: 0 })
              setPendingStartFrame(null)
              setLoopIndex(-1)
              setError('')
              // allow selecting same file again
              e.target.value = ''
            }}
            style={{ display: 'none' }}
          />

          <button
            onClick={onExportJson}
            style={{
              padding: '0.6rem 0.75rem',
              borderRadius: '0.65rem',
              border: '1px solid #2a2a2a',
              background: '#111',
              cursor: 'pointer',
            }}
            disabled={busy}
          >
            Exportar JSON
          </button>

          <button
            onClick={refreshAll}
            style={{
              padding: '0.6rem 0.75rem',
              borderRadius: '0.65rem',
              border: '1px solid #2a2a2a',
              background: busy ? '#222' : '#1f2937',
              cursor: 'pointer',
            }}
            disabled={busy}
          >
            {busy ? 'Atualizando…' : 'Atualizar'}
          </button>

          <button
            onClick={onResetProject}
            style={{
              padding: '0.6rem 0.75rem',
              borderRadius: '0.65rem',
              border: '1px solid #4b1d1d',
              background: '#2a1212',
              cursor: 'pointer',
            }}
            disabled={busy}
            title="Zera o projeto salvo e volta ao estado inicial"
          >
            Resetar
          </button>

          <button
            onClick={() => setActiveTab((t) => (t === 'dashboard' ? 'editor' : 'dashboard'))}
            style={{
              padding: '0.6rem 0.75rem',
              borderRadius: '0.65rem',
              border: activeTab === 'dashboard' ? '1px solid #2a4a1a' : '1px solid #2a2a2a',
              background: activeTab === 'dashboard' ? '#172910' : '#111',
              cursor: 'pointer',
              fontWeight: activeTab === 'dashboard' ? 600 : 400,
            }}
            title="Abrir painel de análises"
          >
            📊 Dashboard
          </button>
        </div>
      </header>

      {error ? (
        <div
          style={{
            margin: '0.75rem',
            padding: '0.75rem',
            borderRadius: '0.65rem',
            border: '1px solid #4b1d1d',
            background: '#2a1212',
            color: '#ffb4b4',
            whiteSpace: 'pre-wrap',
          }}
        >
          {error}
        </div>
      ) : null}

      {/* Main work area: locked to viewport; we scale down on small screens instead of page scroll. */}
      <main style={{ flex: 1, minHeight: 0, overflow: 'hidden', display: 'flex', flexDirection: 'column' }}>
        {/* ── DASHBOARD TAB ── */}
        {activeTab === 'dashboard' && (
          <div style={{ flex: 1, minHeight: 0, padding: 'var(--cta-pad)', display: 'flex', flexDirection: 'column' }}>
            <h2 style={{ margin: '0 0 0.5rem', fontSize: '1rem' }}>📊 Dashboard de Análises</h2>
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
                        videoRef={videoStateRef.current.videoRef}
                        src={videoSrc}
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

      <footer style={{ padding: '0.6rem 0.75rem', color: '#aaa', fontSize: '0.85rem', borderTop: '1px solid #202020' }}>
        Dica: o backend expõe docs interativas em <code>/docs</code>.
      </footer>
    </div>
  )
}

export default App

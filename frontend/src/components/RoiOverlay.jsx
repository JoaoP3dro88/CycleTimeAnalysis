/**
 * RoiOverlay.jsx
 *
 * SVG overlay rendered on top of the camera feed or video.
 * Handles:
 *   - Drawing new polygonal ROIs by clicking on the video
 *   - Displaying existing ROIs with labels
 *   - Highlighting active ROIs (when a hand is inside)
 *
 * Props:
 *   rois          [{name, points:[{x,y}]}]  — list of defined ROIs (normalised 0-1)
 *   activeRois    {Left: roiIndex|null, Right: roiIndex|null}
 *   drawingMode   boolean — when true, clicks add polygon points
 *   onRoisChange  (nextRois) => void
 *   mirror        boolean — true for camera (CSS scaleX(-1)), false for video
 *   videoRef      React ref — optional; used to sync SVG viewBox to video aspect ratio
 *                 so ROI coords match MediaPipe landmark coords exactly.
 */

const ROI_COLORS = ['#00ff00', '#ff00ff', '#00ffff', '#ffff00', '#ff4444', '#ff8800']

export default function RoiOverlay({ rois, activeRois, drawingMode, onRoisChange, mirror = true, videoRef }) {
  // In-progress polygon points (normalised 0-1)
  const [draft, setDraft] = React.useState([])
  const [pendingName, setPendingName] = React.useState(null) // set when awaiting name input
  const svgRef = React.useRef(null)

  // Track video intrinsic dimensions so the SVG viewBox matches the video
  // aspect ratio — this makes SVG coordinate space identical to MediaPipe's
  // normalized [0,1] coordinate space (both relative to the video content area).
  const [videoSize, setVideoSize] = React.useState({ w: 1, h: 1 })
  React.useEffect(() => {
    const video = videoRef?.current
    if (!video) return
    function onMeta() {
      if (video.videoWidth && video.videoHeight) {
        setVideoSize({ w: video.videoWidth, h: video.videoHeight })
      }
    }
    video.addEventListener('loadedmetadata', onMeta)
    video.addEventListener('loadeddata', onMeta)
    onMeta()
    return () => {
      video.removeEventListener('loadedmetadata', onMeta)
      video.removeEventListener('loadeddata', onMeta)
    }
  }, [videoRef])

  // When videoRef is provided, use aspect-ratio-aware viewBox + meet so the SVG
  // letterboxes exactly like the video (object-fit:contain).
  // When no videoRef (camera mode), use square 0-0-1-1 stretched to fill.
  const viewBox = videoRef
    ? `0 0 ${videoSize.w} ${videoSize.h}`
    : '0 0 1 1'
  const preserveAspectRatio = videoRef ? 'xMidYMid meet' : 'none'
  // Scale factors: SVG viewBox units → normalized [0,1]
  const normW = videoSize.w
  const normH = videoSize.h

  // Convert a mouse/pointer event to normalised [0,1] coords relative to the
  // VIDEO CONTENT area (matching MediaPipe landmark coordinates).
  // Uses SVG's own coordinate transform via getScreenCTM so the viewBox
  // letterboxing is automatically accounted for.
  // When mirror=true (camera mode): X is flipped (1-x) to match CSS scaleX(-1).
  function toNorm(e) {
    const svg = svgRef.current
    if (!svg) return null
    // Use SVG point transform: maps screen coords → SVG viewBox coords
    const pt = svg.createSVGPoint()
    pt.x = e.clientX
    pt.y = e.clientY
    const ctm = svg.getScreenCTM()
    if (!ctm) return null
    const svgPt = pt.matrixTransform(ctm.inverse())
    // Normalise to [0,1] by dividing by viewBox dimensions
    const rawX = svgPt.x / normW
    const y = Math.max(0, Math.min(1, svgPt.y / normH))
    const x = Math.max(0, Math.min(1, mirror ? 1 - rawX : rawX))
    return { x, y }
  }

  function handleSvgClick(e) {
    if (!drawingMode) return
    if (e.button !== 0) return // left click only
    const pt = toNorm(e)
    if (!pt) return
    setDraft((d) => [...d, pt])
  }

  function handleSvgRightClick(e) {
    e.preventDefault()
    if (!drawingMode) return
    if (draft.length < 3) {
      setDraft([]) // cancel
      return
    }
    // Prompt for ROI name — use a simple browser prompt for now
    setPendingName('')
  }

  function handleSvgDoubleClick(e) {
    // Double-click also finishes the polygon
    if (!drawingMode || draft.length < 3) return
    e.preventDefault()
    setPendingName('')
  }

  function confirmRoi({ name, leftCategory, rightCategory }) {
    const roiName = name.trim() || `ROI ${rois.length + 1}`
    onRoisChange([...rois, { name: roiName, points: draft, leftCategory, rightCategory }])
    setDraft([])
    setPendingName(null)
  }

  function cancelRoi() {
    setDraft([])
    setPendingName(null)
  }

  // Build SVG point string from normalized [0,1] points, scaled to viewBox dimensions.
  // In camera mode (mirror=true): X is flipped for display (1-x) to undo the
  // coord-flip done in toNorm(), so polygons appear on the correct side.
  function toSvgPts(points) {
    return points.map((p) => {
      const sx = mirror ? (1 - p.x) * normW : p.x * normW
      const sy = p.y * normH
      return `${sx},${sy}`
    }).join(' ')
  }

  // SVG stroke/radius values scale with the viewBox — base them on normW.
  const sw = normW        // viewBox width (1 for camera, videoWidth for video)

  return (
    <>
      <svg
        ref={svgRef}
        style={{
          position: 'absolute',
          inset: 0,
          width: '100%',
          height: '100%',
          cursor: drawingMode ? 'crosshair' : 'default',
          pointerEvents: drawingMode ? 'all' : 'none',
        }}
        viewBox={viewBox}
        preserveAspectRatio={preserveAspectRatio}
        onClick={handleSvgClick}
        onContextMenu={handleSvgRightClick}
        onDoubleClick={handleSvgDoubleClick}
      >
        {/* Existing ROIs */}
        {rois.map((roi, idx) => {
          if (roi.points.length < 3) return null
          const color = ROI_COLORS[idx % ROI_COLORS.length]
          const isActiveLeft = activeRois?.Left === idx
          const isActiveRight = activeRois?.Right === idx
          const isActive = isActiveLeft || isActiveRight
          const pointStr = toSvgPts(roi.points)
          // Centroid in SVG coords
          const dispPts = roi.points.map((p) => ({
            sx: mirror ? (1 - p.x) * normW : p.x * normW,
            sy: p.y * normH,
          }))
          const cx = dispPts.reduce((s, p) => s + p.sx, 0) / dispPts.length
          const cy = dispPts.reduce((s, p) => s + p.sy, 0) / dispPts.length

          return (
            <g key={idx}>
              <polygon
                points={pointStr}
                fill={isActive ? `${color}33` : `${color}1a`}
                stroke={color}
                strokeWidth={isActive ? sw * 0.006 : sw * 0.003}
                strokeDasharray={isActive ? '' : `${sw * 0.012} ${sw * 0.006}`}
              />
              <text
                x={cx}
                y={cy}
                textAnchor="middle"
                dominantBaseline="middle"
                fontSize={sw * 0.045}
                fill={color}
                stroke="#000"
                strokeWidth={sw * 0.004}
                paintOrder="stroke"
              >
                {roi.name}
                {isActiveLeft && isActiveRight ? ' ✋✋' : isActiveLeft ? ' (E)' : isActiveRight ? ' (D)' : ''}
              </text>
            </g>
          )
        })}

        {/* Draft polygon */}
        {draft.length > 0 && (() => {
          const dPts = draft.map((p) => ({
            sx: mirror ? (1 - p.x) * normW : p.x * normW,
            sy: p.y * normH,
          }))
          return (
            <g>
              {dPts.length > 1 && (
                <polyline
                  points={dPts.map((p) => `${p.sx},${p.sy}`).join(' ')}
                  fill="none"
                  stroke="#ffffff"
                  strokeWidth={sw * 0.004}
                  strokeDasharray={`${sw * 0.012} ${sw * 0.006}`}
                />
              )}
              {dPts.map((p, i) => (
                <circle key={i} cx={p.sx} cy={p.sy} r={sw * 0.012} fill="#fff" stroke="#000" strokeWidth={sw * 0.003} />
              ))}
              {dPts.length >= 3 && (
                <line
                  x1={dPts[dPts.length - 1].sx}
                  y1={dPts[dPts.length - 1].sy}
                  x2={dPts[0].sx}
                  y2={dPts[0].sy}
                  stroke="#ffffff66"
                  strokeWidth={sw * 0.003}
                  strokeDasharray={`${sw * 0.008} ${sw * 0.006}`}
                />
              )}
            </g>
          )
        })()}
      </svg>

      {/* Name input dialog */}
      {pendingName !== null && (
        <NameDialog
          defaultName={`ROI ${rois.length + 1}`}
          onConfirm={confirmRoi}
          onCancel={cancelRoi}
        />
      )}

      {/* Drawing mode hint */}
      {drawingMode && (
        <div
          style={{
            position: 'absolute',
            bottom: '0.5rem',
            left: '50%',
            transform: 'translateX(-50%)',
            background: 'rgba(0,0,0,0.7)',
            color: '#fff',
            fontSize: '0.75rem',
            padding: '0.3rem 0.7rem',
            borderRadius: '0.4rem',
            pointerEvents: 'none',
            whiteSpace: 'nowrap',
            zIndex: 20,
          }}
        >
          {draft.length < 3
            ? `Clique para adicionar pontos (${draft.length}/3 mínimo)`
            : `${draft.length} pontos — duplo-clique ou clique-direito para fechar`}
        </div>
      )}
    </>
  )
}

// Dialog for ROI name + per-hand category
// onConfirm({ name, leftCategory, rightCategory })
function NameDialog({ defaultName, onConfirm, onCancel }) {
  const [name, setName] = React.useState(defaultName)
  const [leftCat, setLeftCat] = React.useState('TAV')
  const [rightCat, setRightCat] = React.useState('TAV')

  const CATEGORIES = ['TAV', 'NNVA', 'TNAV', '']
  const CAT_LABELS = { TAV: 'TAV', NNVA: 'NNVA', TNAV: 'TNAV', '': 'Nenhuma' }
  const CAT_COLORS = { TAV: '#2ca02c', NNVA: '#d62728', TNAV: '#ff7f0e', '': '#666' }

  function handleKey(e) {
    if (e.key === 'Enter') handleConfirm()
    if (e.key === 'Escape') onCancel()
  }

  function handleConfirm() {
    onConfirm({ name, leftCategory: leftCat, rightCategory: rightCat })
  }

  const selectStyle = {
    background: '#0b0b0b',
    border: '1px solid #444',
    borderRadius: '0.4rem',
    color: '#fff',
    padding: '0.35rem 0.5rem',
    fontSize: '0.85rem',
    cursor: 'pointer',
  }

  return (
    <div
      style={{
        position: 'absolute',
        inset: 0,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        background: 'rgba(0,0,0,0.6)',
        zIndex: 30,
      }}
    >
      <div
        style={{
          background: '#1a1a1a',
          border: '1px solid #444',
          borderRadius: '0.75rem',
          padding: '1.25rem 1.5rem',
          display: 'flex',
          flexDirection: 'column',
          gap: '0.9rem',
          minWidth: '300px',
        }}
      >
        <span style={{ fontWeight: 600, fontSize: '0.95rem' }}>Configurar ROI</span>

        {/* Name */}
        <label style={{ display: 'flex', flexDirection: 'column', gap: '0.3rem', fontSize: '0.82rem', color: '#aaa' }}>
          Nome da ROI
          <input
            autoFocus
            value={name}
            onChange={(e) => setName(e.target.value)}
            onKeyDown={handleKey}
            style={{
              background: '#0b0b0b',
              border: '1px solid #444',
              borderRadius: '0.4rem',
              color: '#fff',
              padding: '0.4rem 0.6rem',
              fontSize: '0.9rem',
            }}
          />
        </label>

        {/* Per-hand categories */}
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.75rem' }}>
          <label style={{ display: 'flex', flexDirection: 'column', gap: '0.3rem', fontSize: '0.82rem', color: '#aaa' }}>
            🤚 Mão Esquerda
            <select value={leftCat} onChange={(e) => setLeftCat(e.target.value)} style={selectStyle}>
              {CATEGORIES.map((c) => (
                <option key={c} value={c} style={{ color: CAT_COLORS[c] }}>
                  {CAT_LABELS[c]}
                </option>
              ))}
            </select>
            <span style={{ color: CAT_COLORS[leftCat], fontSize: '0.75rem', fontWeight: 600 }}>
              {leftCat || '—'}
            </span>
          </label>

          <label style={{ display: 'flex', flexDirection: 'column', gap: '0.3rem', fontSize: '0.82rem', color: '#aaa' }}>
            ✋ Mão Direita
            <select value={rightCat} onChange={(e) => setRightCat(e.target.value)} style={selectStyle}>
              {CATEGORIES.map((c) => (
                <option key={c} value={c} style={{ color: CAT_COLORS[c] }}>
                  {CAT_LABELS[c]}
                </option>
              ))}
            </select>
            <span style={{ color: CAT_COLORS[rightCat], fontSize: '0.75rem', fontWeight: 600 }}>
              {rightCat || '—'}
            </span>
          </label>
        </div>

        <div style={{ display: 'flex', gap: '0.5rem', justifyContent: 'flex-end' }}>
          <button
            onClick={onCancel}
            style={{ padding: '0.4rem 0.8rem', borderRadius: '0.4rem', border: '1px solid #444', background: '#222', cursor: 'pointer' }}
          >
            Cancelar
          </button>
          <button
            onClick={handleConfirm}
            style={{ padding: '0.4rem 0.8rem', borderRadius: '0.4rem', border: '1px solid #1a4a1a', background: '#0d2e0d', cursor: 'pointer' }}
          >
            Confirmar
          </button>
        </div>
      </div>
    </div>
  )
}

// Need React in scope for the inline components
import React from 'react'

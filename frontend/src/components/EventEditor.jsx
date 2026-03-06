import { useMemo, useState } from 'react'
import '../styles/controls.css'

function badgeClass(category) {
  if (category === 'TAV') return 'badge badgeTAV'
  if (category === 'NNVA') return 'badge badgeNNVA'
  if (category === 'TNAV') return 'badge badgeTNAV'
  return 'badge'
}

// Returns true when the event is missing a meaningful category
function isMissingCategory(event) {
  return !event.category || event.category.trim() === ''
}

export default function EventEditor({
  fps = 30,
  events,
  onChange,
  pendingStartFrame,
  onCreateFromRange,
  loopIndex,
  onLoopIndexChange,
  onSeekStart,
  onSeekEnd,
  tableMaxHeight,
}) {
  const [selectedIndex, setSelectedIndex] = useState(-1)

  const safeEvents = events ?? []

  const selected = useMemo(
    () => (selectedIndex >= 0 ? safeEvents[selectedIndex] : null),
    [safeEvents, selectedIndex]
  )

  function updateEvent(idx, patch) {
    const next = safeEvents.map((e, i) => (i === idx ? { ...e, ...patch } : e))

    // keep duration consistent
    const e = next[idx]
    const start = Number(e.start_frame)
    const end = Number(e.end_frame)
    if (Number.isFinite(start) && Number.isFinite(end) && fps > 0 && end > start) {
      next[idx] = { ...e, duration: Number(((end - start) / fps).toFixed(6)) }
    }

    onChange(next)
  }

  function addManual() {
    const base = {
      operation: 'Nova Operação',
      start_frame: 0,
      end_frame: Math.max(1, Math.floor(fps)),
      duration: 1,
      category: '',
      object: 'Objeto',
      resource: 'Recurso',
    }
    const next = [...safeEvents, base]
    onChange(next)
    setSelectedIndex(next.length - 1)
  }

  function removeSelected() {
    if (selectedIndex < 0) return
    const next = safeEvents.filter((_, i) => i !== selectedIndex)
    onChange(next)
    setSelectedIndex(Math.min(selectedIndex, next.length - 1))

    if (loopIndex === selectedIndex) onLoopIndexChange?.(-1)
    if (loopIndex > selectedIndex) onLoopIndexChange?.(loopIndex - 1)
  }

  function moveSelected(delta) {
    if (selectedIndex < 0) return
    const to = selectedIndex + delta
    if (to < 0 || to >= safeEvents.length) return

    const next = [...safeEvents]
    const tmp = next[selectedIndex]
    next[selectedIndex] = next[to]
    next[to] = tmp
    onChange(next)
    setSelectedIndex(to)

    // keep loopIndex consistent
    if (loopIndex === selectedIndex) onLoopIndexChange?.(to)
    else if (loopIndex === to) onLoopIndexChange?.(selectedIndex)
  }

  const thStyle = {
    textAlign: 'left',
    padding: '0.55rem',
    fontSize: '0.85rem',
    fontWeight: 600,
    whiteSpace: 'nowrap',
  }

  const tdStyle = {
    padding: '0.4rem',
    verticalAlign: 'middle',
    fontSize: '0.85rem',
  }

  const inputCellStyle = {
    width: '100%',
    minWidth: '4.5rem',
  }

  const inputNumStyle = {
    width: '100%',
    minWidth: '3.2rem',
    textAlign: 'right',
  }

  const inputShortStyle = {
    width: '100%',
    minWidth: '3.8rem',
  }

  return (
    <div
      className="card"
      style={{ height: '100%', display: 'flex', flexDirection: 'column', minHeight: 0, overflow: 'hidden' }}
    >
      <div className="ctaRow" style={{ justifyContent: 'space-between' }}>
        <div style={{ display: 'flex', gap: '0.65rem', alignItems: 'center', flexWrap: 'wrap' }}>
          <button className="btn" onClick={addManual}>
            + Adicionar manual
          </button>
          <button className="btn" onClick={() => moveSelected(-1)} disabled={selectedIndex <= 0}>
            ↑ Mover
          </button>
          <button
            className="btn"
            onClick={() => moveSelected(1)}
            disabled={selectedIndex < 0 || selectedIndex >= safeEvents.length - 1}
          >
            ↓ Mover
          </button>
          <button className="btn" onClick={removeSelected} disabled={selectedIndex < 0}>
            Remover
          </button>

          {pendingStartFrame != null ? (
            <span className="badge">
              Início marcado: <b>{pendingStartFrame}</b>
            </span>
          ) : (
            <span className="badge"></span>
          )}

          <button
            className="btn"
            disabled={selectedIndex < 0}
            onClick={() => {
              const e = safeEvents[selectedIndex]
              if (!e) return
              onSeekStart?.(e.start_frame)
            }}
          >
            Ir p/ início
          </button>
          <button
            className="btn"
            disabled={selectedIndex < 0}
            onClick={() => {
              const e = safeEvents[selectedIndex]
              if (!e) return
              onSeekEnd?.(e.end_frame)
            }}
          >
            Ir p/ fim
          </button>
        </div>

        <div style={{ display: 'flex', gap: '0.65rem', alignItems: 'center', flexWrap: 'wrap' }}>
          <span className="badge">Eventos: {safeEvents.length}</span>
          {safeEvents.filter(isMissingCategory).length > 0 && (
            <span
              title="Estes eventos não têm categoria e serão contados como desperdício no dashboard"
              style={{
                padding: '0.2rem 0.5rem',
                borderRadius: '0.4rem',
                fontSize: '0.78rem',
                background: 'rgba(255,127,14,0.12)',
                border: '1px solid rgba(255,127,14,0.45)',
                color: '#ffb347',
                cursor: 'default',
                whiteSpace: 'nowrap',
              }}
            >
              ⚠ {safeEvents.filter(isMissingCategory).length} sem categoria
            </span>
          )}
        </div>
      </div>

      <div
        style={{
          marginTop: '0.75rem',
          overflowX: 'auto',
          overflowY: tableMaxHeight ? 'auto' : 'visible',
          height: tableMaxHeight == null ? 'auto' : tableMaxHeight,
          border: tableMaxHeight ? '1px solid #1f1f1f' : 'none',
          borderRadius: tableMaxHeight ? '0.65rem' : 0,
          minHeight: 0,
          flex: tableMaxHeight ? 1 : 'initial',
        }}
      >
        <table style={{ width: '100%', borderCollapse: 'collapse', tableLayout: 'fixed' }}>
          <colgroup>
            {/* Operação (larga) */}
            <col style={{ width: '34%' }} />
            {/* Início / Fim */}
            <col style={{ width: '10%' }} />
            <col style={{ width: '10%' }} />
            {/* Duração */}
            <col style={{ width: '9%' }} />
            {/* Categoria */}
            <col style={{ width: '16%' }} />
            {/* Objeto / Recurso (bem menores) */}
            <col style={{ width: '11%' }} />
            <col style={{ width: '11%' }} />
            {/* Loop */}
            <col style={{ width: '5%' }} />
          </colgroup>
          <thead>
            <tr style={{ background: '#141414' }}>
              <th style={thStyle}>Operação</th>
              <th style={{ ...thStyle, textAlign: 'right' }}>Início(F)</th>
              <th style={{ ...thStyle, textAlign: 'right' }}>Fim(F)</th>
              <th style={{ ...thStyle, textAlign: 'right' }}>Duração(s)</th>
              <th style={thStyle}>Categoria</th>
              <th style={thStyle}>Objeto</th>
              <th style={thStyle}>Recurso</th>
              <th style={{ ...thStyle, textAlign: 'center' }}>Loop</th>
            </tr>
          </thead>
          <tbody>
            {safeEvents.map((e, idx) => (
              <tr
                key={idx}
                style={{
                  borderTop: '1px solid #222',
                  background: idx === selectedIndex
                    ? 'rgba(31, 41, 55, 0.6)'
                    : isMissingCategory(e)
                    ? 'rgba(255, 127, 14, 0.04)'
                    : 'transparent',
                  outline: isMissingCategory(e) ? '1px solid rgba(255,127,14,0.2)' : 'none',
                  cursor: 'pointer',
                }}
                onClick={() => setSelectedIndex(idx)}
              >
                <td style={tdStyle}>
                  <input
                    className="input"
                    value={e.operation}
                    onChange={(ev) => updateEvent(idx, { operation: ev.target.value })}
                    style={{ ...inputCellStyle, maxWidth: '100%' }}
                  />
                </td>
                <td style={{ ...tdStyle, textAlign: 'right' }}>
                  <input
                    className="input"
                    type="number"
                    value={e.start_frame}
                    onChange={(ev) => updateEvent(idx, { start_frame: Number(ev.target.value) })}
                    onDoubleClick={() => onSeekStart?.(e.start_frame)}
                    style={{ ...inputNumStyle, maxWidth: '100%' }}
                  />
                </td>
                <td style={{ ...tdStyle, textAlign: 'right' }}>
                  <input
                    className="input"
                    type="number"
                    value={e.end_frame}
                    onChange={(ev) => updateEvent(idx, { end_frame: Number(ev.target.value) })}
                    onDoubleClick={() => onSeekEnd?.(e.end_frame)}
                    style={{ ...inputNumStyle, maxWidth: '100%' }}
                  />
                </td>
                <td style={{ ...tdStyle, textAlign: 'right' }}>
                  <span className="badge" style={{ fontSize: '0.78rem' }}>
                    {Number(e.duration ?? 0).toFixed(2)}
                  </span>
                </td>
                <td style={tdStyle}>
                  <div
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: '0.5rem',
                      flexWrap: 'nowrap',
                      minWidth: 0,
                    }}
                  >
                    <select
                      className="select"
                      value={e.category ?? ''}
                      onChange={(ev) => updateEvent(idx, { category: ev.target.value })}
                      style={{ width: '100%', minWidth: '4.75rem', maxWidth: '100%' }}
                    >
                      <option value="">—</option>
                      <option value="TAV">TAV</option>
                      <option value="NNVA">NNVA</option>
                      <option value="TNAV">TNAV</option>
                    </select>
                    <span className={badgeClass(e.category)} style={{ whiteSpace: 'nowrap' }}>
                      {e.category || '—'}
                    </span>
                  </div>
                </td>
                <td style={tdStyle}>
                  <input
                    className="input"
                    value={e.object}
                    onChange={(ev) => updateEvent(idx, { object: ev.target.value })}
                    style={{ ...inputShortStyle, maxWidth: '100%' }}
                  />
                </td>
                <td style={tdStyle}>
                  <input
                    className="input"
                    value={e.resource}
                    onChange={(ev) => updateEvent(idx, { resource: ev.target.value })}
                    style={{ ...inputShortStyle, maxWidth: '100%' }}
                  />
                </td>
                <td style={{ ...tdStyle, textAlign: 'center' }}>
                  <input
                    type="checkbox"
                    checked={loopIndex === idx}
                    onChange={(ev) => {
                      const checked = ev.currentTarget.checked
                      onLoopIndexChange?.(checked ? idx : -1)
                    }}
                    title={loopIndex === idx ? 'Desativar loop deste evento' : 'Ativar loop neste evento'}
                  />
                </td>
              </tr>
            ))}

            {safeEvents.length === 0 ? (
              <tr>
                <td colSpan={8} style={{ padding: '0.9rem', color: '#aaa' }}>
                  Sem eventos ainda. Crie um manualmente, ou marque início/fim no player.
                </td>
              </tr>
            ) : null}
          </tbody>
        </table>
      </div>

      {selected ? (
        <div
          style={{
            marginTop: '0.75rem',
            display: 'flex',
            gap: '0.65rem',
            alignItems: 'center',
            flexWrap: 'wrap',
          }}
        >
          <span className="badge">
            Selecionado: <b>#{selectedIndex + 1}</b>
          </span>
          <span className="badge">
            Frames: <b>{selected.start_frame}</b> → <b>{selected.end_frame}</b>
          </span>
          <span className="badge">
            Duração: <b>{Number(selected.duration ?? 0).toFixed(2)}s</b>
          </span>
          <button
            className="btn"
            onClick={() => {
              if (!onCreateFromRange) return
              onCreateFromRange(selected.start_frame, selected.end_frame)
            }}
            disabled={!onCreateFromRange}
            title="Cria um novo evento copiando o range do selecionado"
          >
            Duplicar
          </button>
        </div>
      ) : null}
    </div>
  )
}

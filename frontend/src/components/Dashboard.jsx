/**
 * Dashboard.jsx
 *
 * Analytical dashboard identical to the legacy Python DashboardWidget.
 * Uses plotly.js-dist-min (installed locally) rendered directly into a <div>
 * via Plotly.react() — no iframe, no CDN, no COEP issues.
 *
 * Charts (matching ProcessTracer_Hands.py DashboardWidget):
 *   1. Resumo Executivo  — KPI cards + Yamazumi bar stacked
 *   2. Análise de Mãos   — Pie Esq vs Dir + grouped bar
 *   3. Sequenciamento Geral — Gantt horizontal ambas as mãos
 *   4. Sequenciamento Mão Esquerda
 *   5. Sequenciamento Mão Direita
 *   6. Análise de Recursos — Sunburst Recurso → Categoria → Nome
 *   7. Análise de Valor    — Bar por Categoria (TAV/NNVA/TNAV)
 *   8. Interações          — Heatmap ROI × Mão
 *
 * Props:
 *   events    {Array}  — project.events list
 *   taktTime  {number} — takt time in seconds (project.meta.takt_time)
 *   fps       {number} — project fps
 */

import { useEffect, useMemo, useRef, useState } from 'react'
import {
  LayoutDashboard, Hand, GanttChart, GanttChartSquare,
  Network, TrendingUp, Grid3x3, FileDown, Loader,
  ChartNoAxesColumn,
} from 'lucide-react'
import Plotly from 'plotly.js-dist-min'

// ─── Constants ───────────────────────────────────────────────────────────────

const COLOR_MAP = {
  TAV:  '#2ca02c',
  NNVA: '#d62728',
  TNAV: '#ff7f0e',
  '':   '#aaaaaa',
}

const CHART_LIST = [
  { id: 'summary',     label: 'Resumo Executivo (KPIs)',          Icon: LayoutDashboard },
  { id: 'hands',       label: 'Análise Detalhada de Mãos',        Icon: Hand            },
  { id: 'gantt',       label: 'Sequenciamento Geral',             Icon: GanttChart      },
  { id: 'gantt_left',  label: 'Sequenciamento Mão Esquerda',      Icon: GanttChartSquare},
  { id: 'gantt_right', label: 'Sequenciamento Mão Direita',       Icon: GanttChartSquare},
  { id: 'resources',   label: 'Análise de Recursos (Sunburst)',   Icon: Network         },
  { id: 'value',       label: 'Análise de Valor (TAV/Desperdício)', Icon: TrendingUp    },
  { id: 'heatmap',     label: 'Interações (Heatmap Mão x ROI)',   Icon: Grid3x3         },
]

const PLOTLY_CONFIG = { responsive: true, displayModeBar: true, scrollZoom: false }

// ─── Data preparation ────────────────────────────────────────────────────────

function prepareData(events) {
  return events.map((ev, i) => ({
    _idx:        i,              // numeric sequential index — used as Gantt Y axis
    Nome:        String(ev.operation ?? ev.resource ?? 'ROI'),
    start_frame: Number(ev.start_frame ?? 0),
    end_frame:   Number(ev.end_frame   ?? 0),
    Duracao_s:   Number(ev.duration    ?? 0),
    Categoria:   String(ev.category    ?? ''),
    Mao:         ev.object === 'Mão Esquerda' ? 'Esq'
               : ev.object === 'Mão Direita'  ? 'Dir'
               : String(ev.object ?? '-'),
    Recurso:     String(ev.resource || 'HD1'),
  }))
}

// ─── Chart builders (return { traces, layout }) ───────────────────────────────

function buildSummary(df, taktTime) {
  const agg = {}
  for (const r of df) {
    if (!agg[r.Recurso]) agg[r.Recurso] = {}
    agg[r.Recurso][r.Categoria] = (agg[r.Recurso][r.Categoria] ?? 0) + r.Duracao_s
  }
  const recursos = Object.keys(agg)
  const cats     = [...new Set(df.map((r) => r.Categoria))]

  const traces = cats.map((cat) => ({
    type: 'bar',
    name: cat || '(sem categoria)',
    x: recursos,
    y: recursos.map((rec) => +(agg[rec][cat] ?? 0).toFixed(3)),
    marker: { color: COLOR_MAP[cat] ?? '#aaa' },
    text: recursos.map((rec) => (agg[rec][cat] ?? 0).toFixed(1)),
    textposition: 'auto',
  }))

  const shapes = taktTime > 0 ? [{
    type: 'line', xref: 'paper', x0: 0, x1: 1,
    y0: taktTime, y1: taktTime,
    line: { color: 'red', dash: 'dot', width: 2 },
  }] : []

  const annotations = taktTime > 0 ? [{
    xref: 'paper', x: 1, y: taktTime, xanchor: 'right',
    text: `Takt: ${taktTime}s`, font: { color: 'red', size: 12 },
    showarrow: false, bgcolor: 'rgba(0,0,0,0.5)',
  }] : []

  return {
    traces,
    layout: {
      title: { text: '📊 Balanceamento Geral (Yamazumi)', font: { size: 16 } },
      barmode: 'stack',
      xaxis: { title: 'Recurso' },
      yaxis: { title: 'Duração (s)' },
      shapes,
      annotations,
      legend: { orientation: 'h', y: -0.2 },
      margin: { t: 60, b: 80 },
    },
  }
}

function buildHands(df) {
  const handDf = df.filter((r) => r.Mao === 'Esq' || r.Mao === 'Dir')

  const pieAgg = {}
  for (const r of handDf) pieAgg[r.Mao] = (pieAgg[r.Mao] ?? 0) + r.Duracao_s
  const pie = {
    type: 'pie',
    labels: Object.keys(pieAgg),
    values: Object.values(pieAgg).map((v) => +v.toFixed(3)),
    name: 'Balanceamento',
    marker: { colors: Object.keys(pieAgg).map((m) => m === 'Esq' ? '#1f77b4' : '#d62728') },
    domain: { x: [0, 0.42] },
    title: { text: 'Balanceamento<br>Esq vs Dir', position: 'bottom center' },
    textinfo: 'label+percent',
    hovertemplate: '%{label}: %{value:.2f}s (%{percent})<extra></extra>',
  }

  const rois = [...new Set(handDf.map((r) => r.Nome))]
  const barTraces = ['Esq', 'Dir'].map((mao) => ({
    type: 'bar',
    name: mao,
    x: rois,
    y: rois.map((nome) =>
      +(handDf.filter((r) => r.Nome === nome && r.Mao === mao)
              .reduce((s, r) => s + r.Duracao_s, 0)).toFixed(3)
    ),
    marker: { color: mao === 'Esq' ? '#1f77b4' : '#d62728' },
    xaxis: 'x2', yaxis: 'y2',
  }))

  return {
    traces: [pie, ...barTraces],
    layout: {
      title: { text: '🤲 Análise Detalhada de Mãos (Esq vs Dir)', font: { size: 16 } },
      grid: { rows: 1, columns: 2, pattern: 'independent' },
      xaxis2: { title: 'ROI', domain: [0.55, 1], anchor: 'y2' },
      yaxis2: { title: 'Duração (s)', anchor: 'x2' },
      barmode: 'group',
      legend: { orientation: 'h', y: -0.2 },
      margin: { t: 60, b: 80 },
    },
  }
}

function buildGanttTracesFromRows(rows) {
  const sorted = [...rows].sort((a, b) => a.start_frame - b.start_frame)
  const cats   = [...new Set(sorted.map((r) => r.Categoria))]
  const traces = []

  // Use numeric y_position (index) + ticktext labels — identical to legacy gen_gantt().
  // This prevents Plotly from collapsing multiple events with the same label into one row.
  for (const cat of cats) {
    const catRows = sorted.filter((r) => r.Categoria === cat)
    let isFirst = true
    for (const row of catRows) {
      traces.push({
        type: 'bar',
        orientation: 'h',
        name: cat || '(sem cat)',
        legendgroup: cat,
        showlegend: isFirst,
        x: [row.end_frame - row.start_frame],
        y: [row._idx],           // numeric position — no label collision
        base: [row.start_frame],
        marker: { color: COLOR_MAP[cat] ?? '#aaa', opacity: 0.85 },
        text: [`${row.Nome} (${row.Duracao_s.toFixed(1)}s)`],
        textposition: 'inside',
        insidetextanchor: 'middle',
        textfont: { color: '#fff', size: 10 },
        hovertemplate:
          `<b>${row.Nome}</b><br>` +
          `Mão: ${row.Mao}<br>` +
          `Categoria: ${row.Categoria || '—'}<br>` +
          `Início: ${row.start_frame} | Fim: ${row.end_frame}<br>` +
          `Duração: ${row.Duracao_s.toFixed(2)}s<extra></extra>`,
      })
      isFirst = false
    }
  }

  const tickvals = sorted.map((r) => r._idx)
  const ticktext = sorted.map((r) => `${r.Mao} — ${r.Nome}`)
  return { traces, tickvals, ticktext, height: Math.max(400, sorted.length * 30 + 120) }
}

function buildGantt(df, title) {
  const { traces, tickvals, ticktext, height } = buildGanttTracesFromRows(df)
  return {
    traces,
    layout: {
      title: { text: title, font: { size: 16 } },
      barmode: 'overlay',
      height,
      hovermode: 'closest',
      xaxis: { title: 'Frames', showgrid: true, gridcolor: 'rgba(200,200,200,0.3)' },
      yaxis: {
        autorange: 'reversed',
        tickmode: 'array',
        tickvals,            // numeric positions (0,1,2...)
        ticktext,            // string labels ("Esq — Mesa", ...)
        automargin: true,
      },
      legend: { orientation: 'h', y: -0.1 },
      margin: { t: 60, l: 20, b: 60, r: 20 },
    },
  }
}

function buildResources(df) {
  const ids = [], labels = [], parents = [], values = [], colors = []

  const recursos = [...new Set(df.map((r) => r.Recurso))]
  for (const rec of recursos) {
    const total = df.filter((r) => r.Recurso === rec).reduce((s, r) => s + r.Duracao_s, 0)
    ids.push(rec); labels.push(rec); parents.push(''); values.push(+total.toFixed(3)); colors.push('#888')
  }

  for (const rec of recursos) {
    const cats = [...new Set(df.filter((r) => r.Recurso === rec).map((r) => r.Categoria))]
    for (const cat of cats) {
      const id    = `${rec}/${cat}`
      const total = df.filter((r) => r.Recurso === rec && r.Categoria === cat).reduce((s, r) => s + r.Duracao_s, 0)
      ids.push(id); labels.push(cat || '—'); parents.push(rec); values.push(+total.toFixed(3))
      colors.push(COLOR_MAP[cat] ?? '#aaa')
    }
  }

  for (const row of df) {
    const parentId = `${row.Recurso}/${row.Categoria}`
    const id       = `${parentId}/${row.Nome}/${row.start_frame}`
    ids.push(id); labels.push(row.Nome); parents.push(parentId); values.push(+row.Duracao_s.toFixed(3))
    colors.push(COLOR_MAP[row.Categoria] ?? '#ccc')
  }

  return {
    traces: [{
      type: 'sunburst',
      ids, labels, parents, values,
      marker: { colors },
      branchvalues: 'total',
      hovertemplate: '<b>%{label}</b><br>%{value:.2f}s<extra></extra>',
      maxdepth: 3,
    }],
    layout: {
      title: { text: '🎯 Distribuição de Carga por Recurso', font: { size: 16 } },
      margin: { t: 60, b: 20, l: 20, r: 20 },
    },
  }
}

function buildValue(df) {
  const agg = {}
  for (const r of df) agg[r.Categoria] = (agg[r.Categoria] ?? 0) + r.Duracao_s
  const cats = Object.keys(agg)

  return {
    traces: [{
      type: 'bar',
      x: cats.map((c) => c || '(sem cat)'),
      y: cats.map((c) => +agg[c].toFixed(3)),
      text: cats.map((c) => agg[c].toFixed(2)),
      textposition: 'auto',
      marker: { color: cats.map((c) => COLOR_MAP[c] ?? '#aaa') },
      hovertemplate: '%{x}: %{y:.2f}s<extra></extra>',
    }],
    layout: {
      title: { text: '💎 Análise de Valor Agregado', font: { size: 16 } },
      xaxis: { title: 'Categoria' },
      yaxis: { title: 'Duração (s)' },
      margin: { t: 60, b: 60 },
    },
  }
}

function buildHeatmap(df) {
  const handDf = df.filter((r) => r.Mao === 'Esq' || r.Mao === 'Dir')
  const rois   = [...new Set(handDf.map((r) => r.Nome))]
  const maos   = ['Dir', 'Esq']

  const z = rois.map((roi) =>
    maos.map((mao) =>
      +(handDf
          .filter((r) => r.Nome === roi && r.Mao === mao)
          .reduce((s, r) => s + r.Duracao_s, 0)
        ).toFixed(3)
    )
  )

  return {
    traces: [{
      type: 'heatmap',
      z, x: maos, y: rois,
      text: z.map((row) => row.map((v) => v.toFixed(2))),
      texttemplate: '%{text}',
      colorscale: 'Viridis',
      colorbar: { title: { text: 'Tempo (s)', side: 'right' } },
      hovertemplate: 'ROI: %{y}<br>Mão: %{x}<br>%{z:.2f}s<extra></extra>',
    }],
    layout: {
      title: { text: '🔥 Matriz de Intensidade: ROI × Mão', font: { size: 16 } },
      xaxis: { title: 'Mão' },
      yaxis: { title: 'ROI', automargin: true },
      margin: { t: 60, l: 20, b: 60, r: 80 },
    },
  }
}

// ─── KPI Bar ─────────────────────────────────────────────────────────────────

function KpiBar({ df, taktTime }) {
  const totalTime  = df.reduce((s, r) => s + r.Duracao_s, 0)
  const tavTime    = df.filter((r) => r.Categoria === 'TAV').reduce((s, r) => s + r.Duracao_s, 0)
  const wastePerc  = totalTime > 0 ? (100 - (tavTime / totalTime) * 100) : 0
  const uniqueRois = new Set(df.map((r) => r.Nome)).size

  const kpis = [
    { label: 'Tempo de Ciclo Total', value: `${totalTime.toFixed(2)}s` },
    { label: 'ROIs Únicas',          value: String(uniqueRois) },
    { label: '% Desperdício (≠TAV)', value: `${wastePerc.toFixed(1)}%` },
    ...(taktTime > 0 ? [{ label: 'Takt Time', value: `${taktTime}s` }] : []),
  ]

  return (
    <div style={{
      display: 'flex', gap: '1rem', flexWrap: 'wrap',
      background: 'linear-gradient(135deg,#1a2a4a,#2d1f3d)',
      borderRadius: '0.6rem', padding: '1rem', marginBottom: '0.75rem',
    }}>
      {kpis.map((k) => (
        <div key={k.label} style={{ flex: '1 1 120px', textAlign: 'center', color: '#fff' }}>
          <div style={{ fontSize: '1.5rem', fontWeight: 700, lineHeight: 1.1 }}>{k.value}</div>
          <div style={{ fontSize: '0.72rem', opacity: 0.8, marginTop: '0.2rem' }}>{k.label}</div>
        </div>
      ))}
    </div>
  )
}

// ─── PlotPanel — renders a Plotly chart directly in a div ────────────────────

function PlotPanel({ traces, layout }) {
  const divRef       = useRef(null)
  const containerRef = useRef(null)

  useEffect(() => {
    if (!divRef.current || !traces.length) return

    // If the layout has an explicit height (e.g. Gantt charts sized by row count),
    // honour it and let the container scroll.
    // Otherwise fill the container height so the chart is never squashed.
    const containerH = containerRef.current?.clientHeight ?? 0
    const plotHeight  = layout.height ?? (containerH > 80 ? containerH : 500)

    const fullLayout = {
      paper_bgcolor: 'rgba(0,0,0,0)',
      plot_bgcolor:  'rgba(0,0,0,0)',
      font: { color: '#e0e0e0' },
      ...layout,
      height: plotHeight,
    }

    Plotly.react(divRef.current, traces, fullLayout, PLOTLY_CONFIG)

    const ro = new ResizeObserver(() => {
      if (!divRef.current || !containerRef.current) return
      // Gantt charts keep their explicit height; all others stretch to fill.
      const h = layout.height ?? (containerRef.current.clientHeight || 500)
      Plotly.relayout(divRef.current, { height: h }).catch(() => {})
    })
    ro.observe(containerRef.current)
    return () => ro.disconnect()
  }, [traces, layout])

  // hasFixedHeight: Gantt charts pass an explicit pixel height — those scroll.
  // All other charts stretch to fill the available space.
  const hasFixedHeight = Boolean(layout.height)

  return (
    <div
      ref={containerRef}
      style={{
        width: '100%',
        height: '100%',
        minHeight: 0,
        overflowY: hasFixedHeight ? 'auto' : 'hidden',
        overflowX: 'hidden',
      }}
    >
      <div ref={divRef} style={{ width: '100%', height: hasFixedHeight ? layout.height : '100%' }} />
    </div>
  )
}

// ─── Empty state ─────────────────────────────────────────────────────────────

function EmptyState() {
  return (
    <div style={{
      flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center',
      flexDirection: 'column', gap: '0.5rem', color: '#555', padding: '3rem',
    }}>
      <ChartNoAxesColumn size={48} strokeWidth={1.25} style={{ opacity: 0.35 }} />
      <p style={{ margin: 0, textAlign: 'center' }}>
        Sem dados para exibir.<br />Adicione eventos ao projeto.
      </p>
    </div>
  )
}

// ─── Export helper ───────────────────────────────────────────────────────────

async function exportFullHtml(df, taktTime) {
  const jobs = [
    { fn: () => buildSummary(df, taktTime),                                           title: 'Resumo Executivo' },
    { fn: () => buildHands(df),                                                        title: 'Análise de Mãos' },
    { fn: () => buildGantt(df, 'Sequenciamento Geral'),                               title: 'Sequenciamento Geral' },
    { fn: () => buildGantt(df.filter((r) => r.Mao === 'Esq'), 'Mão Esquerda'),        title: 'Mão Esquerda' },
    { fn: () => buildGantt(df.filter((r) => r.Mao === 'Dir'), 'Mão Direita'),         title: 'Mão Direita' },
    { fn: () => buildResources(df),                                                    title: 'Recursos' },
    { fn: () => buildValue(df),                                                        title: 'Valor' },
    { fn: () => buildHeatmap(df),                                                      title: 'Heatmap' },
  ]

  const sections = []
  for (const job of jobs) {
    const { traces, layout } = job.fn()
    const div = document.createElement('div')
    div.style.cssText = 'position:fixed;left:-9999px;top:0;width:960px;height:520px;background:#fff'
    document.body.appendChild(div)
    await Plotly.react(div, traces, {
      ...layout,
      paper_bgcolor: '#ffffff',
      plot_bgcolor:  '#f9f9f9',
      font: { color: '#222' },
      width: 960, height: 500,
    }, { ...PLOTLY_CONFIG, responsive: false })
    const img = await Plotly.toImage(div, { format: 'svg', width: 960, height: 500 })
    document.body.removeChild(div)
    sections.push(`<div class="section"><h2>${job.title}</h2><img src="${img}" style="width:100%"/></div>`)
  }

  const html = `<!DOCTYPE html>
<html lang="pt-BR">
<head>
  <meta charset="utf-8">
  <title>Relatório — Cycle Time Analysis</title>
  <style>
    body{margin:0;padding:24px;font-family:Arial,sans-serif;background:#f0f0f0}
    h1,h2{color:#333;text-align:center}
    p.sub{text-align:center;color:#777;margin-top:0}
    .section{background:#fff;border-radius:8px;padding:16px;margin-bottom:32px;box-shadow:0 2px 8px rgba(0,0,0,.1)}
  </style>
</head>
<body>
  <h1>Relatório Completo — Cycle Time Analysis</h1>
  <p class="sub">Gerado em ${new Date().toLocaleString('pt-BR')}</p>
  ${sections.join('\n')}
</body>
</html>`

  const blob = new Blob([html], { type: 'text/html' })
  const url  = URL.createObjectURL(blob)
  const a    = document.createElement('a')
  a.href = url; a.download = 'relatorio_completo.html'; a.click()
  URL.revokeObjectURL(url)
}

// ─── Main component ───────────────────────────────────────────────────────────

export default function Dashboard({ events = [], taktTime = 0, fps = 30 }) {
  const [activeChart, setActiveChart] = useState('summary')
  const [exporting,   setExporting]   = useState(false)

  const df = useMemo(() => prepareData(events), [events])

  const { traces, layout } = useMemo(() => {
    if (!df.length) return { traces: [], layout: {} }
    switch (activeChart) {
      case 'summary':     return buildSummary(df, taktTime)
      case 'hands':       return buildHands(df)
      case 'gantt':       return buildGantt(df, 'Sequenciamento Geral (Ambas Mãos)')
      case 'gantt_left':  return buildGantt(df.filter((r) => r.Mao === 'Esq'), 'Sequenciamento Mão Esquerda')
      case 'gantt_right': return buildGantt(df.filter((r) => r.Mao === 'Dir'), 'Sequenciamento Mão Direita')
      case 'resources':   return buildResources(df)
      case 'value':       return buildValue(df)
      case 'heatmap':     return buildHeatmap(df)
      default:            return { traces: [], layout: {} }
    }
  }, [df, taktTime, activeChart])

  async function handleExport() {
    if (!df.length || exporting) return
    setExporting(true)
    try { await exportFullHtml(df, taktTime) }
    finally { setExporting(false) }
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', minHeight: 0 }}>

      {/* ── Toolbar ── */}
      <div style={{ display: 'flex', gap: '0.35rem', alignItems: 'center', flexWrap: 'wrap', marginBottom: '0.5rem' }}>

        {/* Icon-tab buttons */}
        {CHART_LIST.map(({ id, label, Icon }) => {
          const isActive = activeChart === id
          return (
            <button
              key={id}
              onClick={() => setActiveChart(id)}
              title={label}
              style={{
                display: 'flex', alignItems: 'center', gap: '0.3rem',
                padding: '0.35rem 0.6rem',
                borderRadius: '0.4rem',
                border: isActive ? '1px solid #2a4a1a' : '1px solid #2a2a2a',
                background: isActive ? '#172910' : '#111',
                color: isActive ? '#e0e0e0' : '#888',
                cursor: 'pointer',
                fontSize: '0.78rem',
                fontWeight: isActive ? 600 : 400,
                whiteSpace: 'nowrap',
                transition: 'border-color 0.15s, background 0.15s, color 0.15s',
              }}
            >
              <Icon size={13} strokeWidth={2} />
              <span style={{ display: 'none' }}>{label}</span>
            </button>
          )
        })}

        {/* Active chart label */}
        <span style={{ fontSize: '0.8rem', color: '#aaa', marginLeft: '0.15rem', flex: 1 }}>
          {CHART_LIST.find((c) => c.id === activeChart)?.label}
        </span>

        {/* Export button */}
        <button
          onClick={handleExport}
          disabled={!df.length || exporting}
          style={{
            display: 'flex', alignItems: 'center', gap: '0.35rem',
            padding: '0.35rem 0.7rem',
            borderRadius: '0.4rem',
            border: '1px solid #1a4a2a',
            background: df.length && !exporting ? '#0d2e1a' : '#1a1a1a',
            color: df.length && !exporting ? '#fff' : '#666',
            cursor: df.length && !exporting ? 'pointer' : 'not-allowed',
            fontSize: '0.82rem',
            whiteSpace: 'nowrap',
          }}
        >
          {exporting
            ? <><Loader size={13} strokeWidth={2} style={{ animation: 'spin 1s linear infinite' }} /> Exportando…</>
            : <><FileDown size={13} strokeWidth={2} /> Exportar HTML</>
          }
        </button>

        <span style={{ fontSize: '0.75rem', color: '#666' }}>
          {df.length} evento{df.length !== 1 ? 's' : ''}
        </span>
      </div>

      {/* ── KPI bar (only on summary chart) ── */}
      {activeChart === 'summary' && df.length > 0 && (
        <KpiBar df={df} taktTime={taktTime} />
      )}

      {/* ── Chart area ── */}
      <div style={{
        flex: 1, minHeight: 0,
        border: '1px solid #222', borderRadius: '0.5rem',
        background: '#111',
        overflow: 'hidden',
        padding: '0.5rem',
        display: 'flex',
        flexDirection: 'column',
      }}>
        {df.length === 0
          ? <EmptyState />
          : <PlotPanel traces={traces} layout={layout} />
        }
      </div>
    </div>
  )
}

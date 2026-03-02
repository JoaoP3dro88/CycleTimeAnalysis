import sys
import cv2
import numpy as np
import pandas as pd
import json
import time
from datetime import datetime
from pathlib import Path

# PyQt6
from PyQt6.QtCore import Qt, QTimer, QPoint, QRect, QUrl
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QSlider, QFileDialog, QMessageBox, QComboBox,
    QGroupBox, QSplitter, QTabWidget, QDoubleSpinBox, QTableWidget,
    QTableWidgetItem, QHeaderView, QCheckBox, QSizePolicy, QInputDialog,
    QDialog, QButtonGroup, QRadioButton
)
from PyQt6.QtGui import QImage, QPixmap, QPainter, QPen, QColor, QFont
from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput
from PyQt6.QtMultimediaWidgets import QVideoWidget

# Plotly para gráficos
import plotly.express as px
import plotly.graph_objects as go

try:
    from PyQt6.QtWebEngineWidgets import QWebEngineView
except ImportError:
    print("ERRO: Instale PyQt6-WebEngine: pip install PyQt6-WebEngine")
    sys.exit(1)

# =============================================================================
# CONFIGURAÇÕES GLOBAIS
# =============================================================================
FRAME_WIDTH = 640
FRAME_HEIGHT = 480

CATEGORY_COLORS = {
    'TAV': '#2ca02c',
    'NNVA': '#ff7f0e', 
    'TNAV': '#d62728',
    '': '#999999'
}


# =============================================================================
# WIDGET DE VÍDEO SIMPLIFICADO
# =============================================================================
class VideoCanvas(QLabel):
    """Canvas simples para exibir vídeo"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setStyleSheet("background-color: #1a1a1a; border: 2px solid #333;")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        
        self.current_frame = None

    def update_frame(self, q_image):
        self.current_frame = q_image
        self.update()
        
    def get_image_rect(self):
        """Calcula o retângulo da imagem mantendo aspect ratio"""
        if not self.current_frame:
            return self.rect()
            
        img_size = self.current_frame.size()
        widget_size = self.size()
        
        img_ratio = img_size.width() / img_size.height()
        widget_ratio = widget_size.width() / widget_size.height()
        
        if widget_ratio > img_ratio:
            new_h = widget_size.height()
            new_w = int(new_h * img_ratio)
        else:
            new_w = widget_size.width()
            new_h = int(new_w / img_ratio)
            
        x = (widget_size.width() - new_w) // 2
        y = (widget_size.height() - new_h) // 2
        
        return QRect(x, y, new_w, new_h)
                        
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(0, 0, 0))
        
        if not self.current_frame or self.current_frame.isNull():
            return

        target_rect = self.get_image_rect()
        painter.drawImage(target_rect, self.current_frame)


# =============================================================================
# DASHBOARD ANALÍTICO
# =============================================================================
class DashboardWidget(QWidget):
    """Widget de dashboard com gráficos Plotly"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        
        # Controles
        ctrl = QHBoxLayout()
        ctrl.addWidget(QLabel("<b>Visualização:</b>"))
        
        self.combo_chart = QComboBox()
        self.combo_chart.addItems([
            "📊 Resumo Executivo (KPIs)",
            "🎯 Análise por Tipo de Objeto",
            "📅 Sequenciamento (Gantt Chart)",
            "💎 Análise de Valor (TAV/Desperdício)",
            "🔥 Interações (Heatmap Objeto x Operação)"
        ])
        self.combo_chart.currentIndexChanged.connect(self.update_view)
        ctrl.addWidget(self.combo_chart)
        ctrl.addStretch()
        
        btn_export = QPushButton("💾 Exportar HTML")
        btn_export.clicked.connect(self.export_html)
        ctrl.addWidget(btn_export)
        
        layout.addLayout(ctrl)
        
        # Browser
        self.browser = QWebEngineView()
        self.browser.setStyleSheet("background: white;")
        layout.addWidget(self.browser)
        
        # Estado
        self.df = pd.DataFrame()
        self.takt_time = 0
        
        # Cores oficiais
        self.color_map = {
            'TAV': '#2ca02c', 
            'NNVA': '#ff7f0e', 
            'TNAV': '#d62728', 
            '': '#999999'
        }
    
    def load_data(self, events, takt):
        """Carrega dados dos eventos"""
        if not events:
            self.browser.setHtml("<h3 style='text-align:center; color:#999; padding:50px;'>🔭 Sem dados para exibir</h3>")
            return
            
        self.df = pd.DataFrame(events)
        self.takt_time = takt
        
        # Limpeza de dados
        self.df['start_frame'] = pd.to_numeric(self.df.get('start_frame', 0), errors='coerce').fillna(0)
        self.df['end_frame'] = pd.to_numeric(self.df.get('end_frame', 0), errors='coerce').fillna(0)
        self.df['duration'] = pd.to_numeric(self.df.get('duration', 0), errors='coerce').fillna(0)
        self.df['category'] = self.df.get('category', '').fillna("")
        self.df['object'] = self.df.get('object', 'Objeto').fillna("Objeto").replace("", "Objeto")
        self.df['operation'] = self.df.get('operation', 'Operação').fillna("Operação")
        self.df['resource'] = self.df.get('resource', 'Recurso').fillna("Recurso")
        
        # Renomear colunas
        self.df = self.df.rename(columns={
            'operation': 'Nome',
            'duration': 'Duracao_s',
            'category': 'Categoria',
            'object': 'Objeto',
            'resource': 'Recurso'
        })
        
        self.update_view()
        
    def update_view(self):
        if self.df.empty:
            return
            
        chart_type = self.combo_chart.currentText()
        
        try:
            html = ""
            if "Resumo" in chart_type:
                html = self.gen_summary()
            elif "Tipo de Objeto" in chart_type:
                html = self.gen_object_analysis()
            elif "Sequenciamento" in chart_type:
                html = self.gen_gantt()
            elif "Valor" in chart_type:
                html = self.gen_value_analysis()
            elif "Interações" in chart_type:
                html = self.gen_heatmap()
            else:
                html = "<h3>Visualização não implementada</h3>"
                
            self.browser.setHtml(html)
        except Exception as e:
            self.browser.setHtml(f"<h3 style='color:red'>❌ Erro: {str(e)}</h3>")
    
    def gen_summary(self):
        """Resumo Executivo com KPIs"""
        total_time = self.df['Duracao_s'].sum()
        tav_time = self.df[self.df['Categoria'] == 'TAV']['Duracao_s'].sum()
        waste_percent = 100 - ((tav_time / total_time) * 100) if total_time > 0 else 0
        
        # Gráfico Yamazumi
        fig = px.bar(self.df, x="Recurso", y="Duracao_s", color="Categoria",
                     title="📊 Balanceamento Geral (Yamazumi)",
                     color_discrete_map=self.color_map, 
                     text_auto='.1f',
                     labels={'Duracao_s': 'Duração (s)', 'Recurso': 'Recurso'})
        
        if self.takt_time > 0:
            fig.add_hline(y=self.takt_time, line_dash="dot", 
                         line_color="red", 
                         annotation_text=f"Takt: {self.takt_time}s")
        
        kpi_html = f"""
        <div style="font-family: Arial; padding: 20px; display: flex; justify-content: space-around; 
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; 
                    border-radius: 10px; margin: 20px;">
            <div style="text-align: center;">
                <h2 style="margin: 0; font-size: 48px;">{total_time:.2f}s</h2>
                <p style="margin: 5px 0 0 0; opacity: 0.9;">Tempo de Ciclo Total</p>
            </div>
            <div style="text-align: center;">
                <h2 style="margin: 0; font-size: 48px;">{len(self.df)}</h2>
                <p style="margin: 5px 0 0 0; opacity: 0.9;">Total de Operações</p>
            </div>
            <div style="text-align: center;">
                <h2 style="margin: 0; font-size: 48px;">{waste_percent:.1f}%</h2>
                <p style="margin: 5px 0 0 0; opacity: 0.9;">% Desperdício</p>
            </div>
        </div>
        """
        
        return kpi_html + fig.to_html(full_html=False, include_plotlyjs='cdn')
    
    def gen_value_analysis(self):
        """Análise de Valor Agregado"""
        df_agg = self.df.groupby('Categoria')['Duracao_s'].sum().reset_index()
        
        fig = px.bar(df_agg, x='Categoria', y='Duracao_s', 
                     color='Categoria',
                     text_auto='.2f', 
                     title="💎 Análise de Valor Agregado",
                     color_discrete_map=self.color_map,
                     labels={'Duracao_s': 'Duração (s)', 'Categoria': 'Categoria'})
        
        return fig.to_html(full_html=False, include_plotlyjs='cdn')
    
    def gen_object_analysis(self):
        """Análise por Tipo de Objeto"""
        df_obj = self.df.groupby('Objeto')['Duracao_s'].sum().reset_index()
        df_obj.columns = ['Objeto', 'Tempo_Total']
        
        fig_pie = px.pie(df_obj, values='Tempo_Total', names='Objeto',
                        title="🎯 Distribuição de Tempo por Tipo de Objeto",
                        color_discrete_sequence=px.colors.qualitative.Set3)
        
        fig_bar = px.bar(self.df, x="Nome", y="Duracao_s", color="Objeto", 
                        barmode="group",
                        title="📊 Tempo por Operação e Tipo de Objeto",
                        labels={'Duracao_s': 'Duração (s)', 'Nome': 'Operação'})
        
        return fig_pie.to_html(full_html=False, include_plotlyjs='cdn') + \
               fig_bar.to_html(full_html=False, include_plotlyjs=False)

    def gen_gantt(self):
        """Gantt Chart"""
        df_g = self.df.sort_values("start_frame").copy()
        
        fig = go.Figure()
        
        for categoria in df_g["Categoria"].unique():
            df_cat = df_g[df_g["Categoria"] == categoria]
            
            for idx, row in df_cat.iterrows():
                duracao = row["end_frame"] - row["start_frame"]
                is_first = bool(idx == df_cat.index[0])
                
                label_y = f"{row['Objeto']} - {row['Nome']}"
                
                fig.add_trace(go.Bar(
                    x=[duracao],
                    y=[label_y],
                    name=categoria,
                    orientation='h',
                    marker=dict(color=self.color_map.get(categoria, '#999999')),
                    base=row["start_frame"],
                    text=f"{row['Nome']} ({row['Duracao_s']:.1f}s)",
                    textposition="inside",
                    textfont=dict(color="white", size=10),
                    hovertemplate=f"<b>{row['Nome']}</b><br>" +
                                f"Objeto: {row['Objeto']}<br>" +
                                f"Início: {row['start_frame']:.0f}<br>" +
                                f"Fim: {row['end_frame']:.0f}<br>" +
                                f"Duração: {row['Duracao_s']:.2f}s<extra></extra>",
                    showlegend=is_first,
                    legendgroup=categoria
                ))
        
        fig.update_layout(
            title="📊 Sequenciamento de Operações",
            xaxis_title="Frames (Tempo)",
            yaxis_title="Objeto - Operação",
            barmode='overlay',
            height=max(400, len(df_g) * 30),
            hovermode='closest',
            plot_bgcolor='rgba(240, 240, 240, 0.5)',
            xaxis=dict(showgrid=True, gridwidth=1, gridcolor='rgba(200, 200, 200, 0.3)'),
            yaxis=dict(autorange="reversed")
        )
        
        return fig.to_html(full_html=False, include_plotlyjs='cdn')

    def gen_heatmap(self):
        """Heatmap: Objeto x Operação"""
        if self.df.empty:
            return "<h3 style='text-align:center; padding:50px;'>⚠️ Sem dados para Heatmap.</h3>"
        
        pivot = self.df.pivot_table(index='Nome', columns='Objeto', 
                                    values='Duracao_s', aggfunc='sum').fillna(0)
        
        fig = px.imshow(pivot, text_auto=True, aspect="auto",
                        title="📥 Matriz de Intensidade: Operação x Objeto",
                        color_continuous_scale='Viridis',
                        labels={'color': 'Tempo (s)'})
        
        return fig.to_html(full_html=False, include_plotlyjs='cdn')
        
    def export_html(self):
        path, _ = QFileDialog.getSaveFileName(self, "Salvar Relatório", 
                                            "relatorio_completo.html", "HTML (*.html)")
        if path:
            html = f"""
            <html>
            <head>
                <meta charset="utf-8">
                <title>Relatório T&M Analytics Manual</title>
                <style>
                    body {{ font-family: Arial, sans-serif; margin: 20px; background: #f5f5f5; }}
                    h1 {{ color: #333; text-align: center; }}
                    hr {{ border: none; border-top: 2px solid #ddd; margin: 40px 0; }}
                </style>
            </head>
            <body>
                <h1>📊 Relatório Completo - T&M Manual</h1>
                <p style="text-align:center; color:#666;">Gerado em: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}</p>
                <hr>
                {self.gen_summary()}
                <hr>
                {self.gen_object_analysis()}
                <hr>
                <h2>Gráfico de Sequenciamento</h2>
                {self.gen_gantt()}
                <hr>
                {self.gen_value_analysis()}
                <hr>
                {self.gen_heatmap()}
            </body>
            </html>
            """
            
            with open(path, 'w', encoding='utf-8') as f:
                f.write(html)
            
            QMessageBox.information(self, "Sucesso", f"✅ Relatório salvo:\n{path}")


# =============================================================================
# TABELA CUSTOMIZADA COM DRAG & DROP - VERSÃO CORRIGIDA
# =============================================================================
class DraggableTableWidget(QTableWidget):
    """Tabela com suporte a drag & drop de linhas inteiras"""
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDragDropOverwriteMode(False)
        self.setDragDropMode(QTableWidget.DragDropMode.InternalMove)
        self.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
    
    def dropEvent(self, event):
        """Evento de soltar - reordena as linhas - VERSÃO CORRIGIDA"""
        if not event.source() == self:
            return
        
        # Pegar linha de origem
        drop_row = self.indexAt(event.position().toPoint()).row()
        selected_rows = self.selectionModel().selectedRows()
        
        if not selected_rows:
            return
        
        drag_row = selected_rows[0].row()
        
        # Se soltou fora da tabela, adiciona no final
        if drop_row == -1:
            drop_row = self.rowCount()
        
        # Não fazer nada se soltar na mesma linha
        if drag_row == drop_row:
            return
        
        # Bloquear sinais durante a movimentação
        self.blockSignals(True)
        
        # Salvar TODOS os dados da linha arrastada
        row_data = []
        for col in range(self.columnCount()):
            item = self.item(drag_row, col)
            if item:
                row_data.append(item.text())
            else:
                row_data.append("")
        
        # Salvar widgets (categoria e loop checkbox)
        cat_widget = self.cellWidget(drag_row, 4)
        loop_widget = self.cellWidget(drag_row, 7)
        
        # Salvar estado dos botões de categoria
        category_state = None
        if cat_widget:
            for btn in cat_widget.findChildren(QPushButton):
                if btn.isChecked():
                    category_state = btn.text()
                    break
        
        # Salvar estado do checkbox de loop
        loop_state = False
        if loop_widget:
            checkbox = loop_widget.findChild(QCheckBox)
            if checkbox:
                loop_state = checkbox.isChecked()
        
        # Remover linha original
        self.removeRow(drag_row)
        
        # Ajustar índice de destino se necessário
        if drop_row > drag_row:
            drop_row -= 1
        
        # Inserir nova linha no destino
        self.insertRow(drop_row)
        
        # Restaurar TODOS os dados das células normais
        for col in range(len(row_data)):
            if col not in [3, 4, 7]:  # Pular duração (calculada), categoria e loop (widgets)
                self.setItem(drop_row, col, QTableWidgetItem(row_data[col]))
        
        # Restaurar célula de duração (read-only)
        if len(row_data) > 3:
            item_dur = QTableWidgetItem(row_data[3])
            item_dur.setFlags(Qt.ItemFlag.ItemIsEnabled)
            self.setItem(drop_row, 3, item_dur)
        
        # Restaurar widget de categoria
        cat_widget_new = QWidget()
        cat_layout = QHBoxLayout(cat_widget_new)
        cat_layout.setContentsMargins(1, 1, 1, 1)
        cat_layout.setSpacing(1)
        
        colors = {'TAV': '#2ca02c', 'NNVA': '#ff7f0e', 'TNAV': '#d62728'}
        
        # Encontrar a janela principal navegando pela hierarquia de widgets
        main_window = None
        parent = self.parent()
        while parent is not None:
            if isinstance(parent, TMAnalyzerManual):
                main_window = parent
                break
            parent = parent.parent()
        
        for cat in ['TAV', 'NNVA', 'TNAV']:
            btn = QPushButton(cat)
            btn.setCheckable(True)
            btn.setFixedSize(32, 20)
            btn.setStyleSheet("font-size: 9px;")
            
            if cat == category_state:
                btn.setChecked(True)
                btn.setStyleSheet(f"background: {colors[cat]}; color: white; font-weight: bold; font-size: 9px;")
            
            # Conectar ao handler da janela principal
            if main_window:
                btn.clicked.connect(lambda checked, r=drop_row, c=cat, w=main_window: w.on_category_click(r, c))
            
            cat_layout.addWidget(btn)
        
        self.setCellWidget(drop_row, 4, cat_widget_new)
        
        # Restaurar checkbox de loop
        loop_checkbox_new = QCheckBox()
        loop_checkbox_new.setChecked(loop_state)
        
        # Conectar ao handler da janela principal
        if main_window:
            loop_checkbox_new.stateChanged.connect(
                lambda state, r=drop_row, w=main_window: w.on_loop_checkbox_changed(r, state)
            )
        
        loop_widget_new = QWidget()
        loop_layout_new = QHBoxLayout(loop_widget_new)
        loop_layout_new.addWidget(loop_checkbox_new)
        loop_layout_new.setAlignment(Qt.AlignmentFlag.AlignCenter)
        loop_layout_new.setContentsMargins(0, 0, 0, 0)
        
        self.setCellWidget(drop_row, 7, loop_widget_new)
        
        # Selecionar a nova linha
        self.selectRow(drop_row)
        
        # Reabilitar sinais
        self.blockSignals(False)
        
        # Sincronizar eventos com a nova ordem
        if main_window:
            main_window.sync_events_with_table()
        
        event.accept()


# =============================================================================
# APLICAÇÃO PRINCIPAL
# =============================================================================
class TMAnalyzerManual(QMainWindow):
    """Aplicação de análise manual de T&M"""
    
    def __init__(self):
        super().__init__()
        self.setWindowTitle("🎯 T&M Manual Analyzer - Criação Manual de Eventos")
        self.setGeometry(100, 100, 1600, 900)
        
        # Estado
        self.video_path = None
        self.cap = None
        self.fps = 30
        self.total_frames = 0
        self.current_frame = 0
        
        # Dados
        self.events = []
        
        # Timers
        self.play_timer = QTimer()
        self.play_timer.timeout.connect(self.play_frame)
        
        self.is_playing = False
        self.playback_speed = 1.0
        
        # Sistema de loop
        self.loop_active = False
        self.loop_start_frame = 0
        self.loop_end_frame = 0
        
        self.setup_ui()
        
    def setup_ui(self):
        """Configura interface"""
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        layout = QVBoxLayout(main_widget)
        
        # === BARRA SUPERIOR ===
        top_bar = QHBoxLayout()
        
        btn_load = QPushButton("🎬 Carregar Vídeo")
        btn_load.clicked.connect(self.load_video)
        btn_load.setStyleSheet("background: #3498db; color: white; padding: 8px; font-weight: bold;")
        top_bar.addWidget(btn_load)
        
        btn_export_events = QPushButton("💾 Exportar Eventos (JSON)")
        btn_export_events.clicked.connect(self.export_events)
        btn_export_events.setStyleSheet("background: #27ae60; color: white; padding: 8px; font-weight: bold;")
        top_bar.addWidget(btn_export_events)
        
        btn_import_events = QPushButton("📂 Importar Eventos (JSON)")
        btn_import_events.clicked.connect(self.import_events)
        btn_import_events.setStyleSheet("background: #f39c12; color: white; padding: 8px; font-weight: bold;")
        top_bar.addWidget(btn_import_events)
        
        top_bar.addWidget(QLabel("|"))
        top_bar.addWidget(QLabel("<b>Takt Time (s):</b>"))
        self.spin_takt = QDoubleSpinBox()
        self.spin_takt.setRange(0, 9999)
        self.spin_takt.setValue(10.0)
        top_bar.addWidget(self.spin_takt)
        
        top_bar.addStretch()
        
        layout.addLayout(top_bar)
        
        # === CORPO PRINCIPAL ===
        splitter = QSplitter(Qt.Orientation.Horizontal)
        
        # --- ESQUERDA: CONTROLES E DADOS ---
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        
        self.tabs = QTabWidget()
        
        # TAB 1: EVENTOS
        tab_events = QWidget()
        events_layout = QVBoxLayout(tab_events)
        
        evt_ctrl = QHBoxLayout()
        
        btn_mark_start = QPushButton("🔵 Marcar Início")
        btn_mark_start.clicked.connect(self.mark_start)
        btn_mark_start.setStyleSheet("background: #3498db; color: white; padding: 8px; font-weight: bold;")
        evt_ctrl.addWidget(btn_mark_start)
        
        btn_mark_end = QPushButton("🔴 Marcar Fim")
        btn_mark_end.clicked.connect(self.mark_end)
        btn_mark_end.setStyleSheet("background: #e74c3c; color: white; padding: 8px; font-weight: bold;")
        evt_ctrl.addWidget(btn_mark_end)
        
        evt_ctrl.addWidget(QLabel("|"))
        
        btn_add_evt = QPushButton("➕ Adicionar Manual")
        btn_add_evt.clicked.connect(self.add_manual_event)
        evt_ctrl.addWidget(btn_add_evt)
        
        btn_del_evt = QPushButton("➖ Remover")
        btn_del_evt.clicked.connect(self.delete_event)
        evt_ctrl.addWidget(btn_del_evt)
        
        btn_clear_evt = QPushButton("🗑️ Limpar Todos")
        btn_clear_evt.clicked.connect(self.clear_events)
        evt_ctrl.addWidget(btn_clear_evt)
        
        evt_ctrl.addWidget(QLabel("|"))
        
        btn_move_up = QPushButton("⬆️ Mover p/ Cima")
        btn_move_up.clicked.connect(self.move_event_up)
        btn_move_up.setToolTip("Move o evento selecionado uma posição acima")
        evt_ctrl.addWidget(btn_move_up)
        
        btn_move_down = QPushButton("⬇️ Mover p/ Baixo")
        btn_move_down.clicked.connect(self.move_event_down)
        btn_move_down.setToolTip("Move o evento selecionado uma posição abaixo")
        evt_ctrl.addWidget(btn_move_down)
        
        events_layout.addLayout(evt_ctrl)
        
        # Informação de marcação
        self.lbl_mark_info = QLabel("💡 Marque o início e fim de uma operação usando os botões acima")
        self.lbl_mark_info.setStyleSheet("background: #34495e; color: white; padding: 8px; border-radius: 3px;")
        events_layout.addWidget(self.lbl_mark_info)
        
        # Tabela com drag & drop
        self.table = DraggableTableWidget(0, 8)
        self.table.setHorizontalHeaderLabels([
            "Operação", "Início (F)", "Fim (F)", "Duração (s)", 
            "Categoria", "Objeto", "Recurso", "🔄 Loop"
        ])
        header = self.table.horizontalHeader()
        
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(6, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(7, QHeaderView.ResizeMode.Fixed)
        
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        
        self.table.setColumnWidth(4, 106)
        self.table.setColumnWidth(7, 60)
        
        self.table.cellChanged.connect(self.on_table_changed)
        self.table.cellDoubleClicked.connect(self.on_cell_double_clicked)
        events_layout.addWidget(self.table)
        
        self.tabs.addTab(tab_events, "1️⃣ Eventos")
        
        # TAB 2: DASHBOARD
        tab_dash = QWidget()
        dash_layout = QVBoxLayout(tab_dash)
        
        btn_refresh = QPushButton("🔄 ATUALIZAR DASHBOARD")
        btn_refresh.clicked.connect(self.refresh_dashboard)
        btn_refresh.setStyleSheet("background: #16a085; color: white; padding: 10px; font-weight: bold; font-size: 14px;")
        dash_layout.addWidget(btn_refresh)
        
        self.dashboard = DashboardWidget()
        dash_layout.addWidget(self.dashboard)
        
        self.tabs.addTab(tab_dash, "2️⃣ Dashboard")
        
        left_layout.addWidget(self.tabs)
        
        # Player Controls
        player_group = QGroupBox("🎮 Controles de Vídeo")
        player_layout = QVBoxLayout(player_group)
        
        # Slider
        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.sliderMoved.connect(self.on_slider_moved)
        player_layout.addWidget(self.slider)
        
        # Controles principais
        h_player = QHBoxLayout()
        
        self.btn_play_pause = QPushButton("▶️ Play")
        self.btn_play_pause.clicked.connect(self.toggle_play_pause)
        self.btn_play_pause.setFixedWidth(80)
        self.btn_play_pause.setEnabled(False)
        h_player.addWidget(self.btn_play_pause)
        
        btn_prev = QPushButton("⏮ -1F")
        btn_prev.clicked.connect(self.prev_frame)
        btn_prev.setFixedWidth(70)
        h_player.addWidget(btn_prev)
        
        btn_next = QPushButton("+1F ⏭")
        btn_next.clicked.connect(self.next_frame)
        btn_next.setFixedWidth(70)
        h_player.addWidget(btn_next)
        
        h_player.addWidget(QLabel("|"))
        
        self.lbl_time = QLabel("00:00 / 00:00")
        self.lbl_time.setFixedWidth(120)
        h_player.addWidget(self.lbl_time)
        
        h_player.addWidget(QLabel("|"))
        
        h_player.addWidget(QLabel("Frame:"))
        self.spin_goto_frame = QDoubleSpinBox()
        self.spin_goto_frame.setRange(0, 10000)
        self.spin_goto_frame.setValue(0)
        self.spin_goto_frame.setDecimals(0)
        self.spin_goto_frame.setFixedWidth(80)
        h_player.addWidget(self.spin_goto_frame)
        
        btn_goto = QPushButton("✓ Ir")
        btn_goto.clicked.connect(self.goto_frame)
        btn_goto.setFixedWidth(50)
        h_player.addWidget(btn_goto)
        
        h_player.addStretch()
        
        player_layout.addLayout(h_player)
        
        # Velocidade
        h_speed = QHBoxLayout()
        h_speed.addWidget(QLabel("<b>Velocidade:</b>"))
        
        self.speed_buttons = {}
        speeds = [0.25, 0.5, 1.0, 2.0, 4.0]
        
        for speed in speeds:
            btn = QPushButton(f"{speed}x")
            btn.setCheckable(True)
            btn.setFixedWidth(50)
            if speed == 1.0:
                btn.setChecked(True)
                btn.setStyleSheet("background: #27ae60; color: white; font-weight: bold;")
            btn.clicked.connect(lambda checked, s=speed: self.set_playback_speed(s))
            self.speed_buttons[speed] = btn
            h_speed.addWidget(btn)
        
        h_speed.addStretch()
        player_layout.addLayout(h_speed)
        
        left_layout.addWidget(player_group)
        
        # Status
        self.lbl_status = QLabel("💡 Status: Carregue um vídeo para começar")
        self.lbl_status.setStyleSheet("background: #34495e; color: white; padding: 8px; border-radius: 3px;")
        left_layout.addWidget(self.lbl_status)
        
        splitter.addWidget(left_widget)
        
        # --- DIREITA: VÍDEO ---
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        
        self.canvas = VideoCanvas()
        right_layout.addWidget(self.canvas)
        
        splitter.addWidget(right_widget)
        splitter.setSizes([500, 1100])
        
        layout.addWidget(splitter)
        
        # Estado de marcação
        self.pending_start_frame = None
    
    # ========== CONTROLE DE VÍDEO ==========
    
    def load_video(self):
        """Carrega arquivo de vídeo"""
        path, _ = QFileDialog.getOpenFileName(self, "Selecionar Vídeo", "", 
                                             "Vídeos (*.mp4 *.avi *.mov *.mkv)")
        
        if not path:
            return
        
        # Fechar vídeo anterior se existir
        if self.cap:
            self.cap.release()
        
        self.cap = cv2.VideoCapture(path)
        if not self.cap.isOpened():
            QMessageBox.critical(self, "Erro", f"❌ Não foi possível abrir: {path}")
            return
        
        self.video_path = path
        self.fps = self.cap.get(cv2.CAP_PROP_FPS)
        if self.fps <= 0:
            self.fps = 30
            
        self.total_frames = int(self.cap.get(cv2.CAP_PROP_FRAME_COUNT))
        self.current_frame = 0
        
        self.slider.setMaximum(self.total_frames)
        self.spin_goto_frame.setMaximum(self.total_frames)
        self.slider.setValue(0)
        
        self.btn_play_pause.setEnabled(True)
        
        self.lbl_status.setText(f"✅ Vídeo Carregado: {Path(path).name}")
        
        # Carregar primeiro frame
        self.seek_frame(0)
        
        self.update_time_label()
    
    def toggle_play_pause(self):
        """Alterna entre play e pause"""
        if not self.cap:
            return
        
        if self.is_playing:
            self.play_timer.stop()
            self.is_playing = False
            self.btn_play_pause.setText("▶️ Play")
        else:
            delay = int(1000 / (self.fps * self.playback_speed))
            self.play_timer.start(max(16, delay))
            self.is_playing = True
            self.btn_play_pause.setText("⏸️ Pause")
    
    def play_frame(self):
        """Avança um frame durante o play"""
        if not self.cap:
            return
        
        # ✅ VERIFICAR SE ATINGIU O FIM DO LOOP
        if self.loop_active and self.current_frame >= self.loop_end_frame:
            # Voltar para o início do loop
            self.seek_frame(self.loop_start_frame)
            return
        
        ret, frame = self.cap.read()
        if not ret:
            self.toggle_play_pause()
            return
        
        self.current_frame = int(self.cap.get(cv2.CAP_PROP_POS_FRAMES))
        
        # Atualizar canvas
        h, w = frame.shape[:2]
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        qimg = QImage(rgb.data, w, h, rgb.strides[0], QImage.Format.Format_RGB888).copy()
        self.canvas.update_frame(qimg)
        
        # Atualizar controles
        self.slider.blockSignals(True)
        self.slider.setValue(self.current_frame)
        self.slider.blockSignals(False)
        
        self.spin_goto_frame.blockSignals(True)
        self.spin_goto_frame.setValue(self.current_frame)
        self.spin_goto_frame.blockSignals(False)
        
        self.update_time_label()
    
    def prev_frame(self):
        """Retrocede um frame"""
        if not self.cap:
            return
        
        was_playing = self.is_playing
        if was_playing:
            self.toggle_play_pause()
        
        new_frame = max(0, self.current_frame - 1)
        self.seek_frame(new_frame)
    
    def next_frame(self):
        """Avança um frame"""
        if not self.cap:
            return
        
        was_playing = self.is_playing
        if was_playing:
            self.toggle_play_pause()
        
        new_frame = min(self.total_frames - 1, self.current_frame + 1)
        self.seek_frame(new_frame)
    
    def goto_frame(self):
        """Pula para um frame específico"""
        if not self.cap:
            return
        
        was_playing = self.is_playing
        if was_playing:
            self.toggle_play_pause()
        
        target_frame = int(self.spin_goto_frame.value())
        self.seek_frame(target_frame)
    
    def on_slider_moved(self, value):
        """Quando o slider é movido"""
        if not self.cap:
            return
        
        was_playing = self.is_playing
        if was_playing:
            self.toggle_play_pause()
        
        self.seek_frame(value)
    
    def seek_frame(self, frame):
        """Busca frame específico"""
        if not self.cap:
            return
        
        frame = max(0, min(self.total_frames - 1, frame))
        
        self.cap.set(cv2.CAP_PROP_POS_FRAMES, frame)
        ret, img = self.cap.read()
        
        if ret:
            self.current_frame = frame
            h, w = img.shape[:2]
            
            rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
            qimg = QImage(rgb.data, w, h, rgb.strides[0], QImage.Format.Format_RGB888).copy()
            self.canvas.update_frame(qimg)
            
            self.slider.blockSignals(True)
            self.slider.setValue(frame)
            self.slider.blockSignals(False)
            
            self.spin_goto_frame.blockSignals(True)
            self.spin_goto_frame.setValue(frame)
            self.spin_goto_frame.blockSignals(False)
            
            self.update_time_label()
    
    def set_playback_speed(self, speed):
        """Define velocidade de reprodução"""
        self.playback_speed = speed
        
        for btn_speed, btn in self.speed_buttons.items():
            if btn_speed == speed:
                btn.setChecked(True)
                btn.setStyleSheet("background: #27ae60; color: white; font-weight: bold;")
            else:
                btn.setChecked(False)
                btn.setStyleSheet("")
        
        if self.is_playing:
            self.toggle_play_pause()
            self.toggle_play_pause()
    
    def update_time_label(self):
        """Atualiza label de tempo"""
        current_time = self.current_frame / self.fps
        total_time = self.total_frames / self.fps
        self.lbl_time.setText(
            f"{int(current_time//60):02d}:{int(current_time%60):02d} / "
            f"{int(total_time//60):02d}:{int(total_time%60):02d}"
        )
    
    # ========== MARCAÇÃO DE EVENTOS ==========
    
    def mark_start(self):
        """Marca frame de início"""
        if not self.cap:
            QMessageBox.warning(self, "Aviso", "⚠️ Carregue um vídeo primeiro!")
            return
        
        self.pending_start_frame = self.current_frame
        self.lbl_mark_info.setText(f"✅ Início marcado no frame {self.current_frame}. Avance o vídeo e clique em 'Marcar Fim'")
        self.lbl_mark_info.setStyleSheet("background: #27ae60; color: white; padding: 8px; border-radius: 3px; font-weight: bold;")
    
    def mark_end(self):
        """Marca frame de fim e cria evento"""
        if not self.cap:
            QMessageBox.warning(self, "Aviso", "⚠️ Carregue um vídeo primeiro!")
            return
        
        if self.pending_start_frame is None:
            QMessageBox.warning(self, "Aviso", "⚠️ Marque o início primeiro!")
            return
        
        if self.current_frame <= self.pending_start_frame:
            QMessageBox.warning(self, "Aviso", "⚠️ O frame de fim deve ser maior que o de início!")
            return
        
        # Criar evento
        duration = (self.current_frame - self.pending_start_frame) / self.fps
        
        event = {
            'operation': 'Nova Operação',
            'start_frame': self.pending_start_frame,
            'end_frame': self.current_frame,
            'duration': duration,
            'category': '',
            'object': 'Objeto',
            'resource': 'Recurso'
        }
        
        self.add_event_to_table(event)
        
        # Resetar estado
        self.pending_start_frame = None
        self.lbl_mark_info.setText(f"✅ Evento criado! Frames {event['start_frame']} → {event['end_frame']} ({duration:.2f}s)")
        self.lbl_mark_info.setStyleSheet("background: #3498db; color: white; padding: 8px; border-radius: 3px; font-weight: bold;")
        
        QMessageBox.information(self, "Sucesso", 
            f"✅ Evento criado!\n\nFrames: {event['start_frame']} → {event['end_frame']}\nDuração: {duration:.2f}s")
    
    # ========== GESTÃO DE EVENTOS ==========
    
    def add_event_to_table(self, event):
        """Adiciona evento à tabela"""
        self.table.blockSignals(True)
        
        row = self.table.rowCount()
        self.table.insertRow(row)
        
        self.table.setItem(row, 0, QTableWidgetItem(event.get('operation', 'Operação')))
        self.table.setItem(row, 1, QTableWidgetItem(str(event.get('start_frame', 0))))
        self.table.setItem(row, 2, QTableWidgetItem(str(event.get('end_frame', 0))))
        
        duration = event.get('duration', 0)
        item_dur = QTableWidgetItem(f"{duration:.2f}")
        item_dur.setFlags(Qt.ItemFlag.ItemIsEnabled)
        self.table.setItem(row, 3, item_dur)
        
        # Categoria
        cat_widget = QWidget()
        cat_layout = QHBoxLayout(cat_widget)
        cat_layout.setContentsMargins(1, 1, 1, 1)
        cat_layout.setSpacing(1)
        
        event_category = event.get('category', '')
        
        for cat in ['TAV', 'NNVA', 'TNAV']:
            btn = QPushButton(cat)
            btn.setCheckable(True)
            btn.setFixedSize(32, 20)
            btn.setStyleSheet("font-size: 9px;")
            
            if cat == event_category:
                btn.setChecked(True)
                colors = {'TAV': '#2ca02c', 'NNVA': '#ff7f0e', 'TNAV': '#d62728'}
                btn.setStyleSheet(f"background: {colors[cat]}; color: white; font-weight: bold; font-size: 9px;")
            
            btn.clicked.connect(lambda checked, r=row, c=cat: self.on_category_click(r, c))
            cat_layout.addWidget(btn)

        self.table.setCellWidget(row, 4, cat_widget)
        
        self.table.setItem(row, 5, QTableWidgetItem(event.get('object', 'Objeto')))
        self.table.setItem(row, 6, QTableWidgetItem(event.get('resource', 'Recurso')))
        
        # ✅ CHECKBOX DE LOOP
        loop_checkbox = QCheckBox()
        loop_checkbox.setChecked(False)
        loop_checkbox.stateChanged.connect(lambda state, r=row: self.on_loop_checkbox_changed(r, state))
        
        loop_widget = QWidget()
        loop_layout = QHBoxLayout(loop_widget)
        loop_layout.addWidget(loop_checkbox)
        loop_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        loop_layout.setContentsMargins(0, 0, 0, 0)
        
        self.table.setCellWidget(row, 7, loop_widget)
        
        self.events.append({})
        self.table.blockSignals(False)
        self.update_event_data(row)
    
    def add_manual_event(self):
        """Adiciona evento manual sem marcação"""
        event = {
            'operation': 'Nova Operação',
            'start_frame': self.current_frame,
            'end_frame': self.current_frame + 30,
            'duration': 1.0,
            'category': '',
            'object': 'Objeto',
            'resource': 'Recurso'
        }
        self.add_event_to_table(event)
    
    def delete_event(self):
        """Remove evento selecionado"""
        row = self.table.currentRow()
        if row >= 0:
            self.table.removeRow(row)
            self.events.pop(row)
    
    def clear_events(self):
        """Limpa todos os eventos"""
        reply = QMessageBox.question(
            self, "Confirmar",
            "🗑️ Limpar todos os eventos?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            self.table.setRowCount(0)
            self.events = []
    
    def move_event_up(self):
        """Move evento selecionado uma posição acima"""
        current_row = self.table.currentRow()
        
        if current_row <= 0:
            return  # Já está no topo ou nada selecionado
        
        self.swap_rows(current_row, current_row - 1)
        self.table.selectRow(current_row - 1)
    
    def move_event_down(self):
        """Move evento selecionado uma posição abaixo"""
        current_row = self.table.currentRow()
        
        if current_row == -1 or current_row >= self.table.rowCount() - 1:
            return  # Nada selecionado ou já está no fim
        
        self.swap_rows(current_row, current_row + 1)
        self.table.selectRow(current_row + 1)
    
    def swap_rows(self, row1, row2):
        """Troca duas linhas de posição"""
        self.table.blockSignals(True)
        
        # Salvar dados de ambas as linhas
        data1 = []
        data2 = []
        
        for col in range(self.table.columnCount()):
            item1 = self.table.item(row1, col)
            item2 = self.table.item(row2, col)
            
            data1.append(item1.text() if item1 else "")
            data2.append(item2.text() if item2 else "")
        
        # Salvar widgets de categoria
        cat_widget1 = self.table.cellWidget(row1, 4)
        cat_widget2 = self.table.cellWidget(row2, 4)
        
        cat_state1 = None
        cat_state2 = None
        
        if cat_widget1:
            for btn in cat_widget1.findChildren(QPushButton):
                if btn.isChecked():
                    cat_state1 = btn.text()
                    break
        
        if cat_widget2:
            for btn in cat_widget2.findChildren(QPushButton):
                if btn.isChecked():
                    cat_state2 = btn.text()
                    break
        
        # Salvar widgets de loop
        loop_widget1 = self.table.cellWidget(row1, 7)
        loop_widget2 = self.table.cellWidget(row2, 7)
        
        loop_state1 = False
        loop_state2 = False
        
        if loop_widget1:
            checkbox = loop_widget1.findChild(QCheckBox)
            if checkbox:
                loop_state1 = checkbox.isChecked()
        
        if loop_widget2:
            checkbox = loop_widget2.findChild(QCheckBox)
            if checkbox:
                loop_state2 = checkbox.isChecked()
        
        # Trocar dados das células normais
        for col in range(self.table.columnCount()):
            if col not in [4, 7]:  # Pular widgets
                self.table.setItem(row1, col, QTableWidgetItem(data2[col]))
                self.table.setItem(row2, col, QTableWidgetItem(data1[col]))
        
        # Recriar widgets de categoria
        colors = {'TAV': '#2ca02c', 'NNVA': '#ff7f0e', 'TNAV': '#d62728'}
        
        for row, cat_state in [(row1, cat_state2), (row2, cat_state1)]:
            cat_widget_new = QWidget()
            cat_layout = QHBoxLayout(cat_widget_new)
            cat_layout.setContentsMargins(1, 1, 1, 1)
            cat_layout.setSpacing(1)
            
            for cat in ['TAV', 'NNVA', 'TNAV']:
                btn = QPushButton(cat)
                btn.setCheckable(True)
                btn.setFixedSize(32, 20)
                btn.setStyleSheet("font-size: 9px;")
                
                if cat == cat_state:
                    btn.setChecked(True)
                    btn.setStyleSheet(f"background: {colors[cat]}; color: white; font-weight: bold; font-size: 9px;")
                
                btn.clicked.connect(lambda checked, r=row, c=cat: self.on_category_click(r, c))
                cat_layout.addWidget(btn)
            
            self.table.setCellWidget(row, 4, cat_widget_new)
        
        # Recriar widgets de loop
        for row, loop_state in [(row1, loop_state2), (row2, loop_state1)]:
            loop_checkbox_new = QCheckBox()
            loop_checkbox_new.setChecked(loop_state)
            loop_checkbox_new.stateChanged.connect(lambda state, r=row: self.on_loop_checkbox_changed(r, state))
            
            loop_widget_new = QWidget()
            loop_layout_new = QHBoxLayout(loop_widget_new)
            loop_layout_new.addWidget(loop_checkbox_new)
            loop_layout_new.setAlignment(Qt.AlignmentFlag.AlignCenter)
            loop_layout_new.setContentsMargins(0, 0, 0, 0)
            
            self.table.setCellWidget(row, 7, loop_widget_new)
        
        self.table.blockSignals(False)
        
        # Sincronizar eventos
        self.sync_events_with_table()
    
    def on_loop_checkbox_changed(self, row, state):
        """Handler para quando checkbox de loop é marcada/desmarcada"""
        # Desmarcar todos os outros checkboxes
        for r in range(self.table.rowCount()):
            if r != row:
                loop_widget = self.table.cellWidget(r, 7)
                if loop_widget:
                    checkbox = loop_widget.findChild(QCheckBox)
                    if checkbox:
                        checkbox.blockSignals(True)
                        checkbox.setChecked(False)
                        checkbox.blockSignals(False)
        
        # Se foi marcado
        if state == Qt.CheckState.Checked.value:
            try:
                start_frame = int(float(self.table.item(row, 1).text()))
                end_frame = int(float(self.table.item(row, 2).text()))
                operation = self.table.item(row, 0).text()
                
                # Ativar loop
                self.loop_active = True
                self.loop_start_frame = start_frame
                self.loop_end_frame = end_frame
                
                # Pular para o início do loop
                self.seek_frame(start_frame)
                
                # Iniciar reprodução automaticamente
                if not self.is_playing:
                    self.toggle_play_pause()
                
                duration = (end_frame - start_frame) / self.fps
                self.lbl_status.setText(
                    f"🔄 LOOP ATIVO: {operation}\n"
                    f"Frames: {start_frame}→{end_frame} ({duration:.2f}s)"
                )
                self.lbl_status.setStyleSheet("background: #e74c3c; color: white; padding: 8px; border-radius: 3px; font-weight: bold;")
                
            except Exception as e:
                QMessageBox.warning(self, "Erro", f"⚠️ Erro ao ativar loop: {str(e)}")
                # Desmarcar checkbox
                loop_widget = self.table.cellWidget(row, 7)
                if loop_widget:
                    checkbox = loop_widget.findChild(QCheckBox)
                    if checkbox:
                        checkbox.blockSignals(True)
                        checkbox.setChecked(False)
                        checkbox.blockSignals(False)
        
        # Se foi desmarcado
        else:
            self.loop_active = False
            self.loop_start_frame = 0
            self.loop_end_frame = 0
            self.lbl_status.setText("✅ Loop desativado - Reprodução normal")
            self.lbl_status.setStyleSheet("background: #34495e; color: white; padding: 8px; border-radius: 3px;")
    
    def on_category_click(self, row, category):
        """Handler para clique nos botões de categoria"""
        widget = self.table.cellWidget(row, 4)
        if not widget:
            return
        
        colors = {'TAV': '#2ca02c', 'NNVA': '#ff7f0e', 'TNAV': '#d62728'}
        
        for btn in widget.findChildren(QPushButton):
            if btn.text() == category:
                if btn.isChecked():
                    c = colors.get(category, 'gray')
                    btn.setStyleSheet(f"background: {c}; color: white; font-weight: bold; font-size: 9px;")
                else:
                    btn.setStyleSheet("font-size: 9px;")
            else:
                btn.setChecked(False)
                btn.setStyleSheet("font-size: 9px;")
        
        self.update_event_data(row)
    
    def on_table_changed(self, row, col):
        """Atualiza dados quando célula muda"""
        if col in [1, 2]:  # Frames mudaram
            try:
                start = int(float(self.table.item(row, 1).text()))
                end = int(float(self.table.item(row, 2).text()))
                dur = (end - start) / self.fps if self.fps > 0 else 0
                self.table.item(row, 3).setText(f"{dur:.2f}")
            except:
                pass
        
        self.update_event_data(row)
    
    def on_cell_double_clicked(self, row, col):
        """Pula para o frame do evento ao dar double click"""
        if col in [1, 2]:  # Colunas de frame
            try:
                frame = int(float(self.table.item(row, col).text()))
                self.seek_frame(frame)
            except:
                pass
    
    def update_event_data(self, row):
        """Atualiza dados internos do evento"""
        if row >= len(self.events):
            return
        
        try:
            # Ler categoria dos botões
            cat_widget = self.table.cellWidget(row, 4)
            category = ""
            if cat_widget:
                for btn in cat_widget.findChildren(QPushButton):
                    if btn.isChecked():
                        category = btn.text()
                        break
            
            self.events[row] = {
                'operation': self.table.item(row, 0).text(),
                'start_frame': int(float(self.table.item(row, 1).text())),
                'end_frame': int(float(self.table.item(row, 2).text())),
                'duration': float(self.table.item(row, 3).text()),
                'category': category,
                'object': self.table.item(row, 5).text(),
                'resource': self.table.item(row, 6).text()
            }
        except:
            pass
    
    def refresh_dashboard(self):
        """Atualiza dashboard com dados atuais"""
        # Sincronizar todos os dados da tabela
        self.events = []
        for row in range(self.table.rowCount()):
            self.events.append({})
            self.update_event_data(row)
        
        if not self.events:
            QMessageBox.warning(self, "Aviso", "⚠️ Nenhum evento para visualizar!")
            return
        
        self.dashboard.load_data(self.events, self.spin_takt.value())
        self.tabs.setCurrentIndex(1)  # Mudar para aba do dashboard
        QMessageBox.information(self, "Sucesso", "✅ Dashboard atualizado!")
    
    def export_events(self):
        """Exporta eventos para JSON"""
        if not self.events:
            QMessageBox.warning(self, "Aviso", "⚠️ Nenhum evento para exportar!")
            return
        
        # Sincronizar dados
        self.events = []
        for row in range(self.table.rowCount()):
            self.events.append({})
            self.update_event_data(row)
        
        path, _ = QFileDialog.getSaveFileName(
            self, "Exportar Eventos", 
            f"eventos_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
            "JSON (*.json)"
        )
        
        if path:
            data = {
                'video_path': self.video_path,
                'fps': self.fps,
                'total_frames': self.total_frames,
                'takt_time': self.spin_takt.value(),
                'events': self.events,
                'timestamp': datetime.now().isoformat()
            }
            
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            
            QMessageBox.information(self, "Sucesso", f"✅ Eventos exportados:\n{path}")
    
    def import_events(self):
        """Importa eventos de JSON"""
        path, _ = QFileDialog.getOpenFileName(
            self, "Importar Eventos",
            "",
            "JSON (*.json)"
        )
        
        if not path:
            return
        
        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # Limpar eventos atuais
            self.table.setRowCount(0)
            self.events = []
            
            # Carregar vídeo se especificado
            video_path = data.get('video_path')
            if video_path and Path(video_path).exists():
                reply = QMessageBox.question(
                    self, "Carregar Vídeo",
                    f"Deseja carregar o vídeo associado?\n{video_path}",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
                )
                
                if reply == QMessageBox.StandardButton.Yes:
                    self.video_path = video_path
                    if self.cap:
                        self.cap.release()
                    self.cap = cv2.VideoCapture(video_path)
                    if self.cap.isOpened():
                        self.fps = self.cap.get(cv2.CAP_PROP_FPS)
                        self.total_frames = int(self.cap.get(cv2.CAP_PROP_FRAME_COUNT))
                        self.slider.setMaximum(self.total_frames)
                        self.spin_goto_frame.setMaximum(self.total_frames)
                        self.btn_play_pause.setEnabled(True)
                        self.seek_frame(0)
            
            # Carregar takt time
            if 'takt_time' in data:
                self.spin_takt.setValue(data['takt_time'])
            
            # Carregar eventos
            for event in data.get('events', []):
                self.add_event_to_table(event)
            
            QMessageBox.information(
                self, "Sucesso",
                f"✅ {len(self.events)} eventos importados com sucesso!"
            )
            
        except Exception as e:
            QMessageBox.critical(self, "Erro", f"❌ Erro ao importar eventos:\n{str(e)}")
    
    def closeEvent(self, event):
        """Limpeza ao fechar"""
        if self.cap:
            self.cap.release()
        event.accept()
    
    def sync_events_with_table(self):
        """Sincroniza a lista de eventos com a ordem atual da tabela"""
        new_events = []
        for row in range(self.table.rowCount()):
            try:
                # Ler categoria dos botões
                cat_widget = self.table.cellWidget(row, 4)
                category = ""
                if cat_widget:
                    for btn in cat_widget.findChildren(QPushButton):
                        if btn.isChecked():
                            category = btn.text()
                            break
                
                event_data = {
                    'operation': self.table.item(row, 0).text(),
                    'start_frame': int(float(self.table.item(row, 1).text())),
                    'end_frame': int(float(self.table.item(row, 2).text())),
                    'duration': float(self.table.item(row, 3).text()),
                    'category': category,
                    'object': self.table.item(row, 5).text(),
                    'resource': self.table.item(row, 6).text()
                }
                new_events.append(event_data)
            except:
                pass
        
        self.events = new_events


# =============================================================================
# EXECUÇÃO
# =============================================================================
if __name__ == '__main__':
    app = QApplication(sys.argv)
    app.setStyle('Fusion')
    
    app.setStyleSheet("""
        QToolTip { 
            color: #FFFFFF;
            background-color: #2c3e50;
            border: 2px solid #16a085;
            padding: 2px;
            border-radius: 5px;
        }
        QGroupBox {
            font-size: 14px;
            font-weight: bold;
            border: 1px solid #C0C0C0;
            border-radius: 5px;
            margin-top: 10px;
        }
        QGroupBox::title {
            subcontrol-origin: margin;
            subcontrol-position: top left;
            padding: 0 5px 0 5px;
        }
    """)
    
    window = TMAnalyzerManual()
    window.show()
    
    sys.exit(app.exec())
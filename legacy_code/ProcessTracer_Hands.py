import sys
import cv2
import numpy as np
import pandas as pd
import json
import time
from datetime import datetime
from pathlib import Path

# MediaPipe
import mediapipe as mp

# PyQt6
from PyQt6.QtCore import Qt, QTimer, QPoint, QRect, QUrl
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QSlider, QFileDialog, QMessageBox, QComboBox,
    QGroupBox, QSplitter, QTabWidget, QDoubleSpinBox, QTableWidget,
    QTableWidgetItem, QHeaderView, QCheckBox, QSizePolicy, QInputDialog, QGraphicsDropShadowEffect,
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


from PyQt6.QtCore import QThread, pyqtSignal


# =============================================================================
# CONFIGURAÇÕES GLOBAIS
# =============================================================================
FRAME_WIDTH = 1280
FRAME_HEIGHT = 720
GRID_SIZE = 4
FPS_TARGET = 30

ROI_COLORS = [
    (0, 255, 0), (255, 0, 255), (0, 255, 255), 
    (255, 255, 0), (0, 0, 255), (255, 128, 0)
]

CATEGORY_COLORS = {
    'TAV': '#2ca02c',
    'NNVA': '#ff7f0e', 
    'TNAV': '#d62728',
    '': '#999999'
}

CONFIRMATION_FRAMES = 3  # Número de frames consecutivos para confirmar entrada/saída
REENTRY_GRACE_FRAMES = 10  # Janela de frames para permitir reentrada sem evento


# =============================================================================
# DIALOG DE CONFIGURAÇÃO DE ROI
# =============================================================================
class ROIConfigDialog(QDialog):
    """Dialog para configurar nome e categorias da ROI"""
    
    def __init__(self, parent=None, roi_name=""):
        super().__init__(parent)
        self.setWindowTitle("Configurar ROI")
        self.setModal(True)
        self.setMinimumWidth(400)
        
        layout = QVBoxLayout(self)
        
        # Nome da ROI
        layout.addWidget(QLabel("<b>Nome da ROI:</b>"))
        self.txt_name = QLabel()
        self.txt_name.setText(roi_name if roi_name else "Nova ROI")
        self.txt_name.setStyleSheet("padding: 8px; background: #f0f0f0; border-radius: 4px;")
        layout.addWidget(self.txt_name)
        
        # Configuração Mão Esquerda
        grp_left = QGroupBox("🤚 Mão Esquerda")
        left_layout = QVBoxLayout(grp_left)
        
        self.btn_group_left = QButtonGroup()
        self.radio_left_tav = QRadioButton("TAV - Trabalho que Agrega Valor")
        self.radio_left_nnva = QRadioButton("NNVA - Necessário, Não Agrega Valor")
        self.radio_left_tnav = QRadioButton("TNAV - Não Agrega Valor")
        self.radio_left_none = QRadioButton("(Sem categoria padrão)")
        
        self.btn_group_left.addButton(self.radio_left_tav)
        self.btn_group_left.addButton(self.radio_left_nnva)
        self.btn_group_left.addButton(self.radio_left_tnav)
        self.btn_group_left.addButton(self.radio_left_none)
        
        self.radio_left_none.setChecked(True)
        
        left_layout.addWidget(self.radio_left_tav)
        left_layout.addWidget(self.radio_left_nnva)
        left_layout.addWidget(self.radio_left_tnav)
        left_layout.addWidget(self.radio_left_none)
        
        layout.addWidget(grp_left)
        
        # Configuração Mão Direita
        grp_right = QGroupBox("✋ Mão Direita")
        right_layout = QVBoxLayout(grp_right)
        
        self.btn_group_right = QButtonGroup()
        self.radio_right_tav = QRadioButton("TAV - Trabalho que Agrega Valor")
        self.radio_right_nnva = QRadioButton("NNVA - Necessário, Não Agrega Valor")
        self.radio_right_tnav = QRadioButton("TNAV - Não Agrega Valor")
        self.radio_right_none = QRadioButton("(Sem categoria padrão)")
        
        self.btn_group_right.addButton(self.radio_right_tav)
        self.btn_group_right.addButton(self.radio_right_nnva)
        self.btn_group_right.addButton(self.radio_right_tnav)
        self.btn_group_right.addButton(self.radio_right_none)
        
        self.radio_right_none.setChecked(True)
        
        right_layout.addWidget(self.radio_right_tav)
        right_layout.addWidget(self.radio_right_nnva)
        right_layout.addWidget(self.radio_right_tnav)
        right_layout.addWidget(self.radio_right_none)
        
        layout.addWidget(grp_right)
        
        # Botões
        btn_layout = QHBoxLayout()
        btn_ok = QPushButton("✅ Confirmar")
        btn_ok.clicked.connect(self.accept)
        btn_cancel = QPushButton("❌ Cancelar")
        btn_cancel.clicked.connect(self.reject)
        
        btn_layout.addWidget(btn_cancel)
        btn_layout.addWidget(btn_ok)
        layout.addLayout(btn_layout)
    
    def get_config(self):
        """Retorna a configuração escolhida"""
        left_cat = None
        if self.radio_left_tav.isChecked():
            left_cat = 'TAV'
        elif self.radio_left_nnva.isChecked():
            left_cat = 'NNVA'
        elif self.radio_left_tnav.isChecked():
            left_cat = 'TNAV'
        
        right_cat = None
        if self.radio_right_tav.isChecked():
            right_cat = 'TAV'
        elif self.radio_right_nnva.isChecked():
            right_cat = 'NNVA'
        elif self.radio_right_tnav.isChecked():
            right_cat = 'TNAV'
        
        return {
            'name': self.txt_name.text(),
            'left_category': left_cat,
            'right_category': right_cat
        }



# =============================================================================
# DIALOG DE CONFIGURAÇÃO DE SEQUÊNCIA DE OPERAÇÕES
# =============================================================================
class SequenceConfigDialog(QDialog):
    """Dialog para configurar a sequência de operações do ciclo"""
    
    def __init__(self, parent=None, available_rois=None):
        super().__init__(parent)
        self.setWindowTitle("Configurar Sequência de Operações")
        self.setModal(True)
        self.setMinimumSize(600, 500)
        
        self.available_rois = available_rois or []
        
        layout = QVBoxLayout(self)
        
        # Instruções
        info = QLabel("""
        <b>📋 Configuração da Sequência Padrão do Ciclo</b><br>
        Defina a ordem correta das operações (ROIs) que devem ser executadas em cada ciclo.<br>
        A ROI de início do ciclo será automaticamente adicionada no começo e no fim.
        """)
        info.setStyleSheet("padding: 10px; border-radius: 5px; margin-bottom: 10px;")
        layout.addWidget(info)
        
        # Layout principal dividido
        main_layout = QHBoxLayout()
        
        # === COLUNA ESQUERDA: ROIs Disponíveis ===
        left_group = QGroupBox("ROIs Disponíveis")
        left_layout = QVBoxLayout(left_group)
        
        self.list_available = QTableWidget(0, 1)
        self.list_available.setHorizontalHeaderLabels(["ROI"])
        self.list_available.horizontalHeader().setStretchLastSection(True)
        self.list_available.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.list_available.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        
        # Preencher com ROIs disponíveis
        for roi_name in self.available_rois:
            row = self.list_available.rowCount()
            self.list_available.insertRow(row)
            self.list_available.setItem(row, 0, QTableWidgetItem(roi_name))
        
        left_layout.addWidget(self.list_available)
        main_layout.addWidget(left_group)
        
        # === COLUNA DO MEIO: Botões de Controle ===
        middle_layout = QVBoxLayout()
        middle_layout.addStretch()
        
        btn_add = QPushButton("➡️\nAdicionar")
        btn_add.setMinimumHeight(60)
        btn_add.clicked.connect(self.add_to_sequence)
        btn_add.setStyleSheet("font-weight: bold;")
        middle_layout.addWidget(btn_add)
        
        btn_remove = QPushButton("⬅️\nRemover")
        btn_remove.setMinimumHeight(60)
        btn_remove.clicked.connect(self.remove_from_sequence)
        btn_remove.setStyleSheet("font-weight: bold;")
        middle_layout.addWidget(btn_remove)
        
        middle_layout.addSpacing(20)
        
        btn_up = QPushButton("⬆️\nSubir")
        btn_up.setMinimumHeight(60)
        btn_up.clicked.connect(self.move_up)
        btn_up.setStyleSheet("font-weight: bold;")
        middle_layout.addWidget(btn_up)
        
        btn_down = QPushButton("⬇️\nDescer")
        btn_down.setMinimumHeight(60)
        btn_down.clicked.connect(self.move_down)
        btn_down.setStyleSheet("font-weight: bold;")
        middle_layout.addWidget(btn_down)
        
        middle_layout.addStretch()
        main_layout.addLayout(middle_layout)
        
        # === COLUNA DIREITA: Sequência Definida ===
        right_group = QGroupBox("Sequência do Ciclo (em ordem)")
        right_layout = QVBoxLayout(right_group)
        
        self.list_sequence = QTableWidget(0, 2)
        self.list_sequence.setHorizontalHeaderLabels(["#", "ROI"])
        self.list_sequence.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.list_sequence.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.list_sequence.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.list_sequence.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        
        right_layout.addWidget(self.list_sequence)
        
        btn_clear = QPushButton("🗑️ Limpar Sequência")
        btn_clear.clicked.connect(self.clear_sequence)
        right_layout.addWidget(btn_clear)
        
        main_layout.addWidget(right_group)
        
        layout.addLayout(main_layout)
        
        # Botões finais
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        
        btn_cancel = QPushButton("❌ Cancelar")
        btn_cancel.clicked.connect(self.reject)
        btn_layout.addWidget(btn_cancel)
        
        btn_ok = QPushButton("✅ Confirmar")
        btn_ok.clicked.connect(self.accept)
        btn_ok.setStyleSheet("background: #27ae60; color: white; font-weight: bold;")
        btn_layout.addWidget(btn_ok)
        
        layout.addLayout(btn_layout)
    
    def add_to_sequence(self):
        """Adiciona ROI selecionada à sequência"""
        selected = self.list_available.selectedItems()
        if not selected:
            return
        
        roi_name = selected[0].text()
        row = self.list_sequence.rowCount()
        self.list_sequence.insertRow(row)
        self.list_sequence.setItem(row, 0, QTableWidgetItem(str(row + 1)))
        self.list_sequence.setItem(row, 1, QTableWidgetItem(roi_name))
    
    def remove_from_sequence(self):
        """Remove ROI selecionada da sequência"""
        selected_row = self.list_sequence.currentRow()
        if selected_row >= 0:
            self.list_sequence.removeRow(selected_row)
            self.update_sequence_numbers()
    
    def move_up(self):
        """Move item para cima na sequência"""
        row = self.list_sequence.currentRow()
        if row > 0:
            roi_name = self.list_sequence.item(row, 1).text()
            self.list_sequence.removeRow(row)
            self.list_sequence.insertRow(row - 1)
            self.list_sequence.setItem(row - 1, 0, QTableWidgetItem(str(row)))
            self.list_sequence.setItem(row - 1, 1, QTableWidgetItem(roi_name))
            self.list_sequence.setCurrentCell(row - 1, 1)
            self.update_sequence_numbers()
    
    def move_down(self):
        """Move item para baixo na sequência"""
        row = self.list_sequence.currentRow()
        if row >= 0 and row < self.list_sequence.rowCount() - 1:
            roi_name = self.list_sequence.item(row, 1).text()
            self.list_sequence.removeRow(row)
            self.list_sequence.insertRow(row + 1)
            self.list_sequence.setItem(row + 1, 0, QTableWidgetItem(str(row + 2)))
            self.list_sequence.setItem(row + 1, 1, QTableWidgetItem(roi_name))
            self.list_sequence.setCurrentCell(row + 1, 1)
            self.update_sequence_numbers()
    
    def clear_sequence(self):
        """Limpa toda a sequência"""
        self.list_sequence.setRowCount(0)
    
    def update_sequence_numbers(self):
        """Atualiza a numeração da sequência"""
        for row in range(self.list_sequence.rowCount()):
            self.list_sequence.setItem(row, 0, QTableWidgetItem(str(row + 1)))
    
    def get_sequence(self):
        """Retorna a lista de ROIs na sequência definida"""
        sequence = []
        for row in range(self.list_sequence.rowCount()):
            roi_name = self.list_sequence.item(row, 1).text()
            sequence.append(roi_name)
        return sequence



# =============================================================================
# WIDGET DE VÍDEO COM DESENHO DE ROI
# =============================================================================
class VideoCanvas(QLabel):
    """Canvas com Aspect Ratio Correto (Letterbox) e sem espelhamento"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setMouseTracking(True)
        self.setStyleSheet("background-color: #1a1a1a; border: 2px solid #333;")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        
        self.current_frame = None 
        self.drawing_enabled = False
        self.current_roi_points = []
        self.final_rois = [] 
        
        self.grid_map = {}
        self.cell_w = FRAME_WIDTH // GRID_SIZE
        self.cell_h = FRAME_HEIGHT // GRID_SIZE

    def update_frame(self, q_image):
        self.current_frame = q_image
        self.update()
        
    def get_image_rect(self):
        """Calcula o retângulo da imagem mantendo aspect ratio (Letterbox)"""
        if not self.current_frame:
            return self.rect()
            
        img_size = self.current_frame.size()
        widget_size = self.size()
        
        img_ratio = img_size.width() / img_size.height()
        widget_ratio = widget_size.width() / widget_size.height()
        
        new_w, new_h = 0, 0
        
        if widget_ratio > img_ratio:
            # Widget é mais largo que a imagem (barras laterais)
            new_h = widget_size.height()
            new_w = int(new_h * img_ratio)
        else:
            # Widget é mais alto que a imagem (barras em cima/baixo)
            new_w = widget_size.width()
            new_h = int(new_w / img_ratio)
            
        x = (widget_size.width() - new_w) // 2
        y = (widget_size.height() - new_h) // 2
        
        return QRect(x, y, new_w, new_h)

    def enable_drawing(self):
        self.drawing_enabled = True
        self.setCursor(Qt.CursorShape.CrossCursor)
        
    def disable_drawing(self):
        self.drawing_enabled = False
        self.setCursor(Qt.CursorShape.ArrowCursor)
        
    def mousePressEvent(self, event):
        if not self.drawing_enabled or not self.current_frame:
            return
            
        # Obter retângulo real da imagem
        img_rect = self.get_image_rect()
        
        # Ignorar cliques nas barras pretas
        if not img_rect.contains(event.position().toPoint()):
            return
            
        if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
            self.clear_rois()
            return
            
        if event.button() == Qt.MouseButton.LeftButton:
            # Converter clique da janela para coordenadas da imagem (0.0 a 1.0)
            click_x = event.position().x() - img_rect.x()
            click_y = event.position().y() - img_rect.y()
            
            x_norm = click_x / img_rect.width()
            y_norm = click_y / img_rect.height()
            
            # Travar entre 0 e 1 por segurança
            x_norm = max(0.0, min(1.0, x_norm))
            y_norm = max(0.0, min(1.0, y_norm))
            
            self.current_roi_points.append((x_norm, y_norm))
            self.update()
            
        elif event.button() == Qt.MouseButton.RightButton:
            if len(self.current_roi_points) >= 3:
                # Pedir nome da ROI
                name, ok = QInputDialog.getText(self, "Nome da ROI", "Digite o nome do posto/área:")
                if not ok or not name:
                    name = f"ROI {len(self.final_rois)}"
                
                # Abrir dialog de configuração
                dialog = ROIConfigDialog(self, name)
                if dialog.exec() == QDialog.DialogCode.Accepted:
                    config = dialog.get_config()
                    
                    new_roi = {
                        'name': config['name'],
                        'points': list(self.current_roi_points),
                        'left_category': config['left_category'],
                        'right_category': config['right_category']
                    }
                    self.final_rois.append(new_roi)
                    self.current_roi_points = []
                    self.rebuild_grid_map()
                    self.disable_drawing()
                    self.update()
                else:
                    # Cancelou - limpa pontos
                    self.current_roi_points = []
            else:
                self.current_roi_points = []
                
    def clear_rois(self):
        self.final_rois = []
        self.current_roi_points = []
        self.grid_map = {}
        self.update()
        
    def rebuild_grid_map(self):
        # Lógica de grid permanece baseada no FRAME_WIDTH original (lógico)
        self.grid_map = {}
        for idx, roi_data in enumerate(self.final_rois):
            poly_points = roi_data['points']
            if len(poly_points) < 3: continue
            
            points_px = [(int(x * FRAME_WIDTH), int(y * FRAME_HEIGHT)) for x, y in poly_points]
            poly_array = np.array(points_px, dtype=np.int32)
            x, y, w, h = cv2.boundingRect(poly_array)
            
            start_col = max(0, x // self.cell_w)
            end_col = min(GRID_SIZE - 1, (x + w) // self.cell_w)
            start_row = max(0, y // self.cell_h)
            end_row = min(GRID_SIZE - 1, (y + h) // self.cell_h)
            
            for r in range(start_row, end_row + 1):
                for c in range(start_col, end_col + 1):
                    cell_key = (r, c)
                    if cell_key not in self.grid_map: self.grid_map[cell_key] = []
                    if idx not in self.grid_map[cell_key]: self.grid_map[cell_key].append(idx)
                        
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        # 1. Preencher fundo com preto (para as barras laterais/superiores)
        painter.fillRect(self.rect(), QColor(0, 0, 0))
        
        if not self.current_frame or self.current_frame.isNull():
            return

        # 2. Calcular onde desenhar a imagem para manter proporção
        target_rect = self.get_image_rect()
        painter.drawImage(target_rect, self.current_frame)

        # Dados para converter coordenadas normalizadas para tela
        off_x = target_rect.x()
        off_y = target_rect.y()
        draw_w = target_rect.width()
        draw_h = target_rect.height()

        # 3. Desenhar polígono em construção
        if self.current_roi_points:
            painter.setPen(QPen(QColor(0, 165, 255), 3, Qt.PenStyle.DashLine))
            points = []
            for x, y in self.current_roi_points:
                px = int(off_x + x * draw_w)
                py = int(off_y + y * draw_h)
                points.append(QPoint(px, py))
                
            if len(points) > 1:
                for i in range(len(points)-1): painter.drawLine(points[i], points[i+1])
            for pt in points:
                painter.setBrush(QColor(0, 165, 255))
                painter.drawEllipse(pt, 5, 5)
                
        # 4. Desenhar ROIs finalizadas
        for idx, roi_data in enumerate(self.final_rois):
            poly_points = roi_data['points']
            roi_name = roi_data['name']
            
            color_bgr = ROI_COLORS[idx % len(ROI_COLORS)]
            color = QColor(color_bgr[2], color_bgr[1], color_bgr[0])
            
            painter.setPen(QPen(color, 3))
            points = []
            for x, y in poly_points:
                px = int(off_x + x * draw_w)
                py = int(off_y + y * draw_h)
                points.append(QPoint(px, py))
            
            # Fechar polígono
            points.append(points[0])  
            
            for i in range(len(points)-1):
                painter.drawLine(points[i], points[i+1])
                
            # Label
            painter.setFont(QFont("Arial", 12, QFont.Weight.Bold))
            text_pos = points[0]
            
            painter.setPen(QColor(0,0,0)) # Sombra
            painter.drawText(text_pos.x() + 11, text_pos.y() + 26, roi_name)
            
            painter.setPen(QColor(255, 255, 255)) # Texto
            painter.drawText(text_pos.x() + 10, text_pos.y() + 25, roi_name)
            
    # Métodos save/load permanecem iguais
    def save_rois(self, filename='rois_config.json'):
        data = {'timestamp': datetime.now().isoformat(), 'rois': self.final_rois}
        with open(filename, 'w') as f: json.dump(data, f, indent=2)
        
    def load_rois(self, filename='rois_config.json'):
        try:
            with open(filename, 'r') as f:
                data = json.load(f)
                raw_rois = data['rois']
                self.final_rois = []
                for i, item in enumerate(raw_rois):
                    if isinstance(item, list):
                        self.final_rois.append({'name': f"ROI {i}", 'points': item})
                    else:
                        self.final_rois.append(item)
                self.rebuild_grid_map()
                self.update()
                return True
        except Exception as e:
            print(f"Erro: {e}")
            return False



# =============================================================================
# ENGINE DE PROCESSAMENTO DE VÍDEO/CÂMERA
# =============================================================================
class VideoProcessor:
    """Processa frames de vídeo ou câmera com MediaPipe"""
    
    def __init__(self):
        # MediaPipe
        self.mp_hands = mp.solutions.hands
        self.hands = self.mp_hands.Hands(
            static_image_mode=False,
            max_num_hands=2,
            min_detection_confidence=0.5,
            min_tracking_confidence=0.5
        )
        self.mp_draw = mp.solutions.drawing_utils
        
        # Estado de rastreamento
        self.tracking_state = {
            'Left': {'total_time': 0.0, 'roi_states': {}, 'current_roi': None, 'entry_frame': None},
            'Right': {'total_time': 0.0, 'roi_states': {}, 'current_roi': None, 'entry_frame': None}
        }
        self.event_log = []
        self.last_time = time.time()
        
        # === NOVO: Sistema de confirmação e buffer ===
        self.detection_buffer = {
            'Left': {'current_roi': None, 'buffer': [], 'lost_frames': 0, 'last_known_roi': None},
            'Right': {'current_roi': None, 'buffer': [], 'lost_frames': 0, 'last_known_roi': None}
        }
        
        # 🆕 NOVO: Cache de detecções
        self.detection_cache = None
        self.use_cache = False
        self.current_frame = 0
        self.fps = 30
    
    def set_detection_cache(self, cache):
        """Define cache de detecções para modo rápido"""
        self.detection_cache = cache
        self.use_cache = True
    
    def clear_cache(self):
        """Limpa cache e volta ao modo tempo real"""
        self.detection_cache = None
        self.use_cache = False
    
    def set_current_frame(self, frame_num, fps):
        """Define o frame atual e FPS para cálculos de tempo"""
        self.current_frame = frame_num
        self.fps = fps
        
    def reset_tracking(self):
        """Reseta estado de rastreamento"""
        self.tracking_state = {
            'Left': {'total_time': 0.0, 'roi_states': {}, 'current_roi': None, 'entry_frame': None},
            'Right': {'total_time': 0.0, 'roi_states': {}, 'current_roi': None, 'entry_frame': None}
        }
        self.event_log = []
        self.detection_buffer = {
            'Left': {'current_roi': None, 'buffer': [], 'lost_frames': 0, 'last_known_roi': None},
            'Right': {'current_roi': None, 'buffer': [], 'lost_frames': 0, 'last_known_roi': None}
        }
        self.current_frame = 0
        self.last_time = time.time()
    
    def process_frame(self, frame, rois, grid_map, run_detection=True):
        """
        Processa frame com sistema de confirmação para reduzir ruído
        CORREÇÃO: Uma mão só pode estar em UMA ROI por vez
        """
        current_time = time.time()
        new_events = []
        
        h, w = frame.shape[:2]
        
        hands_detected = {}  # hand_label -> roi_idx (apenas uma ROI por mão!)
        
        # 🔧 NOVO: Usar cache se disponível
        cached_hands = []
        if self.use_cache and self.detection_cache:
            cached_hands = self.detection_cache.get_detection(self.current_frame)
        
        # 🔧 DETECÇÃO: Cache ou Tempo Real
        if self.use_cache and self.detection_cache and cached_hands:
            # Processar mãos do cache
            for hand_data in cached_hands:
                original_label = hand_data['handedness']
                hand_label = 'Right' if original_label == 'Left' else 'Left'
                
                # Coordenada da ponta do indicador
                x_px = hand_data['index_tip'][0]
                y_px = hand_data['index_tip'][1]
                
                # Visualização
                cv2.circle(frame, (x_px, y_px), 12, (0, 255, 255), -1)
                cv2.circle(frame, (x_px, y_px), 14, (0, 0, 0), 2)
                
                # Detectar ROI - APENAS UMA ROI por mão!
                cell_w = w // GRID_SIZE
                cell_h = h // GRID_SIZE
                cell_col = x_px // cell_w
                cell_row = y_px // cell_h
                cell_key = (cell_row, cell_col)
                candidate_rois = grid_map.get(cell_key, []) if 0 <= cell_row < GRID_SIZE and 0 <= cell_col < GRID_SIZE else []
                
                detected_roi = None
                for roi_idx in candidate_rois:
                    if roi_idx >= len(rois): continue
                    
                    roi_data = rois[roi_idx]
                    poly_points = [(int(x*w), int(y*h)) for x, y in roi_data['points']]
                    poly_array = np.array(poly_points, dtype=np.int32)
                    
                    if cv2.pointPolygonTest(poly_array, (x_px, y_px), False) >= 0:
                        detected_roi = roi_idx
                        break  # ✅ PARE APÓS ENCONTRAR A PRIMEIRA ROI!
                
                hands_detected[hand_label] = detected_roi
                
                # Status visual
                if detected_roi is not None:
                    roi_name = rois[detected_roi].get('name', f"ROI {detected_roi}")
                    status = roi_name
                    color = (0, 255, 0)
                else:
                    status = 'FORA'
                    color = (128, 128, 128)
                
                cv2.putText(frame, f"{hand_label}: {status}", (x_px + 20, y_px), 
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)
        
        elif run_detection:
            # Processar com MediaPipe (modo tempo real)
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            rgb.flags.writeable = False
            results = self.hands.process(rgb)
            rgb.flags.writeable = True
            frame = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
            
            if results.multi_hand_landmarks and results.multi_handedness:
                cell_w = w // GRID_SIZE
                cell_h = h // GRID_SIZE
                
                for i, hand_landmarks in enumerate(results.multi_hand_landmarks):
                    original_label = results.multi_handedness[i].classification[0].label
                    hand_label = 'Right' if original_label == 'Left' else 'Left'
                    
                    # Coordenada da ponta do indicador
                    tip = hand_landmarks.landmark[self.mp_hands.HandLandmark.INDEX_FINGER_TIP]
                    x_px = int(tip.x * w)
                    y_px = int(tip.y * h)
                    
                    # Visualização
                    cv2.circle(frame, (x_px, y_px), 12, (0, 255, 255), -1)
                    cv2.circle(frame, (x_px, y_px), 14, (0, 0, 0), 2)
                    
                    # Detectar ROI - APENAS UMA ROI por mão!
                    cell_col = x_px // cell_w
                    cell_row = y_px // cell_h
                    cell_key = (cell_row, cell_col)
                    candidate_rois = grid_map.get(cell_key, []) if 0 <= cell_row < GRID_SIZE and 0 <= cell_col < GRID_SIZE else []
                    
                    detected_roi = None
                    for roi_idx in candidate_rois:
                        if roi_idx >= len(rois): continue
                        
                        roi_data = rois[roi_idx]
                        poly_points = [(int(x*w), int(y*h)) for x, y in roi_data['points']]
                        poly_array = np.array(poly_points, dtype=np.int32)
                        
                        if cv2.pointPolygonTest(poly_array, (x_px, y_px), False) >= 0:
                            detected_roi = roi_idx
                            break  # ✅ PARE APÓS ENCONTRAR A PRIMEIRA ROI!
                    
                    hands_detected[hand_label] = detected_roi
                    
                    # Desenho da mão
                    self.mp_draw.draw_landmarks(
                        frame, hand_landmarks, self.mp_hands.HAND_CONNECTIONS,
                        self.mp_draw.DrawingSpec(color=(0, 0, 255), thickness=2, circle_radius=3),
                        self.mp_draw.DrawingSpec(color=(0, 255, 0), thickness=2)
                    )
                    
                    # Status visual
                    if detected_roi is not None:
                        roi_name = rois[detected_roi].get('name', f"ROI {detected_roi}")
                        status = roi_name
                        color = (0, 255, 0)
                    else:
                        status = 'FORA'
                        color = (128, 128, 128)
                    
                    cv2.putText(frame, f"{hand_label}: {status}", (x_px + 20, y_px), 
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)
        
        # === PROCESSAR CADA MÃO COM SISTEMA DE CONFIRMAÇÃO ===
        for hand_label in ['Left', 'Right']:
            buffer_state = self.detection_buffer[hand_label]
            detected_roi = hands_detected.get(hand_label)
            
            if hand_label not in hands_detected:
                # Mão não detectada - incrementar contador de frames perdidos
                buffer_state['lost_frames'] += 1
                
                # Se passou da janela de tolerância, processar saída
                if buffer_state['lost_frames'] > REENTRY_GRACE_FRAMES:
                    current_roi = buffer_state['current_roi']
                    if current_roi is not None:
                        roi_state = self.tracking_state[hand_label]['roi_states'].get(current_roi)
                        if roi_state and roi_state['in_zone']:
                            duration = current_time - roi_state['entry_time']
                            roi_state['in_zone'] = False
                            roi_state['entry_time'] = None
                            roi_state['total_time'] += duration
                            self.tracking_state[hand_label]['total_time'] += duration
                            
                            event = {
                                'type': 'SAIDA_PERDA',
                                'hand': hand_label,
                                'roi': current_roi,
                                'roi_name': roi_state.get('name', f"ROI {current_roi}"),
                                'duration': duration,
                                'timestamp': current_time,
                                'start_frame': roi_state.get('entry_frame'),
                                'end_frame': self.current_frame,
                                'frame_time': self.current_frame,
                                'category': roi_state.get(f'{hand_label.lower()}_category')
                            }
                            new_events.append(event)
                            self.event_log.append(event)
                    
                    buffer_state['current_roi'] = None
                    buffer_state['last_known_roi'] = None
                
                continue
            
            # Mão detectada - resetar contador
            buffer_state['lost_frames'] = 0
            
            # === VERIFICAR SE MUDOU DE ROI ===
            current_roi = buffer_state['current_roi']
            
            # Se saiu de uma ROI para entrar em outra (ou sair para FORA)
            if current_roi is not None and current_roi != detected_roi:
                # Processar SAÍDA da ROI atual
                roi_state = self.tracking_state[hand_label]['roi_states'].get(current_roi)
                if roi_state and roi_state['in_zone']:
                    duration = current_time - roi_state['entry_time']
                    
                    # Filtrar saídas muito curtas (ruído)
                    if duration >= 0.15:  # Pelo menos 150ms
                        roi_state['in_zone'] = False
                        roi_state['entry_time'] = None
                        roi_state['total_time'] += duration
                        self.tracking_state[hand_label]['total_time'] += duration
                        
                        event = {
                            'type': 'SAIDA',
                            'hand': hand_label,
                            'roi': current_roi,
                            'roi_name': roi_state.get('name', f"ROI {current_roi}"),
                            'duration': duration,
                            'timestamp': current_time,
                            'start_frame': roi_state.get('entry_frame'),
                            'end_frame': self.current_frame,
                            'frame_time': self.current_frame,
                            'category': roi_state.get(f'{hand_label.lower()}_category')
                        }
                        new_events.append(event)
                        self.event_log.append(event)
                
                buffer_state['current_roi'] = None
            
            # === PROCESSAR ENTRADA EM NOVA ROI ===
            if detected_roi is not None and buffer_state['current_roi'] is None:
                # Adicionar ao buffer de confirmação
                buffer_state['buffer'].append((detected_roi, 'ENTRADA'))
                
                # Verificar se tem frames consecutivos suficientes
                recent_entries = [b for b in buffer_state['buffer'][-CONFIRMATION_FRAMES:] 
                                if b == (detected_roi, 'ENTRADA')]
                
                if len(recent_entries) >= CONFIRMATION_FRAMES:
                    # CONFIRMADO - Registrar entrada
                    roi_data = rois[detected_roi]
                    roi_name = roi_data.get('name', f"ROI {detected_roi}")
                    
                    if detected_roi not in self.tracking_state[hand_label]['roi_states']:
                        self.tracking_state[hand_label]['roi_states'][detected_roi] = {
                            'in_zone': False, 'entry_time': None, 'total_time': 0.0, 'name': roi_name,
                            'entry_frame': None
                        }
                    
                    roi_state = self.tracking_state[hand_label]['roi_states'][detected_roi]
                    roi_state['name'] = roi_name
                    roi_state['in_zone'] = True
                    roi_state['entry_time'] = current_time
                    roi_state['entry_frame'] = self.current_frame  # ✅ SALVAR FRAME DE ENTRADA
                    roi_state['left_category'] = roi_data.get('left_category')
                    roi_state['right_category'] = roi_data.get('right_category')
                    
                    buffer_state['current_roi'] = detected_roi
                    buffer_state['last_known_roi'] = detected_roi
                    
                    event = {
                        'type': 'ENTRADA',
                        'hand': hand_label,
                        'roi': detected_roi,
                        'roi_name': roi_name,
                        'timestamp': current_time,
                        'frame_time': self.current_frame,
                        'entry_frame': self.current_frame  # ✅ INCLUIR NA ENTRADA TAMBÉM
                    }
                    new_events.append(event)
                    self.event_log.append(event)
                    
                    # Limpar buffer
                    buffer_state['buffer'] = []
            
            # Limitar tamanho do buffer
            if len(buffer_state['buffer']) > CONFIRMATION_FRAMES * 3:
                buffer_state['buffer'] = buffer_state['buffer'][-CONFIRMATION_FRAMES * 3:]
        
        # Desenhar ROIs
        for idx, roi_data in enumerate(rois):
            poly_points = roi_data['points']
            roi_name = roi_data.get('name', f"ROI {idx}")
            if len(poly_points) < 3: continue
            
            color = ROI_COLORS[idx % len(ROI_COLORS)]
            points_px = [(int(x*w), int(y*h)) for x, y in poly_points]
            poly_array = np.array(points_px, dtype=np.int32)
            cv2.polylines(frame, [poly_array], True, color, 3)
        
        # HUD
        cv2.putText(frame, f"Left Total: {self.tracking_state['Left']['total_time']:.1f}s",
                (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 100, 100), 2)
        cv2.putText(frame, f"Right Total: {self.tracking_state['Right']['total_time']:.1f}s",
                (10, 65), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (100, 100, 255), 2)
        
        # DEBUG: Mostrar ROI atual de cada mão
        y_offset = 100
        for hand_label in ['Left', 'Right']:
            current_roi = self.detection_buffer[hand_label]['current_roi']
            if current_roi is not None:
                roi_name = rois[current_roi].get('name', f"ROI {current_roi}") if current_roi < len(rois) else "N/A"
                cv2.putText(frame, f"{hand_label} em: {roi_name}",
                        (10, y_offset), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (200, 200, 0), 2)
                y_offset += 25
        
        self.last_time = current_time
        return frame, new_events



# =============================================================================
# CACHE PARA MEDIAPIPE
# =============================================================================
class MediaPipeCache:
    """Cache de detecções do MediaPipe Hands para reprodução rápida"""
    
    def __init__(self):
        self.detections = {}  # frame_num -> [list of hand detections]
        self.fps = 30
        self.total_frames = 0
        self.video_path = None
        
    def clear(self):
        """Limpa o cache"""
        self.detections = {}
        self.fps = 30
        self.total_frames = 0
        self.video_path = None
    
    def add_detection(self, frame_num, hands):
        """Adiciona detecções de mãos de um frame"""
        self.detections[frame_num] = hands
    
    def get_detection(self, frame_num):
        """Recupera detecções de mãos de um frame"""
        return self.detections.get(frame_num, [])
    
    def has_detections(self):
        """Verifica se há detecções no cache"""
        return len(self.detections) > 0
    
    def save_to_file(self, filepath):
        """Salva cache em arquivo JSON"""
        data = {
            'video_path': self.video_path,
            'fps': self.fps,
            'total_frames': self.total_frames,
            'detections': {str(k): v for k, v in self.detections.items()}
        }
        with open(filepath, 'w') as f:
            json.dump(data, f, default=self._serialize_hand)
    
    def _serialize_hand(self, obj):
        """Função auxiliar para serializar objetos de mão"""
        if isinstance(obj, dict):
            return obj
        return str(obj)
    
    def load_from_file(self, filepath):
        """Carrega cache de arquivo JSON"""
        try:
            with open(filepath, 'r') as f:
                data = json.load(f)
            
            self.video_path = data['video_path']
            self.fps = data['fps']
            self.total_frames = data['total_frames']
            self.detections = {int(k): v for k, v in data['detections'].items()}
            return True
        except:
            return False


class MediaPipePreprocessThread(QThread):
    """Thread para pré-processar vídeo com MediaPipe Hands"""
    
    progress = pyqtSignal(int, int, str)  # frame_atual, total_frames, mensagem
    finished = pyqtSignal(object)  # MediaPipeCache
    error = pyqtSignal(str)
    
    def __init__(self, video_path):
        super().__init__()
        self.video_path = video_path
        self.mp_hands = mp.solutions.hands
        self.hands = self.mp_hands.Hands(
            static_image_mode=False,
            max_num_hands=2,
            min_detection_confidence=0.5,
            min_tracking_confidence=0.5
        )
        self.should_stop = False
        
    def run(self):
        """Processa vídeo inteiro com MediaPipe"""
        try:
            cap = cv2.VideoCapture(self.video_path)
            if not cap.isOpened():
                self.error.emit(f"Erro ao abrir vídeo: {self.video_path}")
                return
            
            fps = cap.get(cv2.CAP_PROP_FPS)
            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            
            cache = MediaPipeCache()
            cache.video_path = self.video_path
            cache.fps = fps
            cache.total_frames = total_frames
            
            frame_num = 0
            
            while True:
                if self.should_stop:
                    break
                
                ret, frame = cap.read()
                if not ret:
                    break
                
                # Processar com MediaPipe
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                rgb.flags.writeable = False
                results = self.hands.process(rgb)
                rgb.flags.writeable = True
                
                hands_data = []
                if results.multi_hand_landmarks and results.multi_handedness:
                    h, w = frame.shape[:2]
                    
                    for i, hand_landmarks in enumerate(results.multi_hand_landmarks):
                        original_label = results.multi_handedness[i].classification[0].label
                        
                        # Coordenada da ponta do indicador
                        tip = hand_landmarks.landmark[self.mp_hands.HandLandmark.INDEX_FINGER_TIP]
                        x_px = int(tip.x * w)
                        y_px = int(tip.y * h)
                        
                        hand_data = {
                            'handedness': original_label,
                            'index_tip': [x_px, y_px],
                            'landmarks': []
                        }
                        
                        # Salvar pontos importantes (para visualização futura)
                        for landmark in hand_landmarks.landmark:
                            hand_data['landmarks'].append({
                                'x': landmark.x,
                                'y': landmark.y,
                                'z': landmark.z
                            })
                        
                        hands_data.append(hand_data)
                
                cache.add_detection(frame_num, hands_data)
                
                # Atualizar progresso
                frame_num += 1
                if frame_num % 10 == 0:  # Atualizar a cada 10 frames
                    self.progress.emit(frame_num, total_frames, f"Processando frame {frame_num}/{total_frames}")
            
            cap.release()
            self.finished.emit(cache)
            
        except Exception as e:
            self.error.emit(f"Erro no processamento: {str(e)}")
    
    def stop(self):
        """Para o processamento"""
        self.should_stop = True


class MediaPipePreprocessDialog(QDialog):
    """Dialog de progresso do pré-processamento com MediaPipe"""
    
    def __init__(self, parent=None, video_path=None):
        super().__init__(parent)
        self.setWindowTitle("Pré-processando Vídeo com MediaPipe")
        self.setModal(True)
        self.setMinimumWidth(500)
        
        layout = QVBoxLayout(self)
        
        # Informações
        info = QLabel(f"""
        <b>🤖 Processamento de Mãos em Andamento</b><br>
        O vídeo está sendo processado com MediaPipe Hands para detectar mãos.<br>
        Após concluir, a reprodução será muito mais rápida!
        """)
        info.setStyleSheet("padding: 15px; border-radius: 8px;")
        layout.addWidget(info)
        
        # Barra de progresso
        self.progress_bar = QSlider(Qt.Orientation.Horizontal)
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setEnabled(False)
        layout.addWidget(self.progress_bar)
        
        # Label de status
        self.lbl_status = QLabel("Iniciando...")
        self.lbl_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.lbl_status)
        
        # Label de tempo
        self.lbl_time = QLabel("Tempo estimado: calculando...")
        self.lbl_time.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_time.setStyleSheet("color: #666;")
        layout.addWidget(self.lbl_time)
        
        # Botão cancelar
        self.btn_cancel = QPushButton("❌ Cancelar")
        self.btn_cancel.clicked.connect(self.cancel_processing)
        layout.addWidget(self.btn_cancel)
        
        # Thread de processamento
        self.thread = MediaPipePreprocessThread(video_path)
        self.thread.progress.connect(self.update_progress)
        self.thread.finished.connect(self.processing_finished)
        self.thread.error.connect(self.processing_error)
        
        self.cache = None
        self.start_time = time.time()
        
    def start_processing(self):
        """Inicia o processamento"""
        self.start_time = time.time()
        self.thread.start()
    
    def update_progress(self, current, total, message):
        """Atualiza barra de progresso"""
        percent = int((current / total) * 100)
        self.progress_bar.setValue(percent)
        self.lbl_status.setText(message)
        
        # Calcular tempo estimado
        elapsed = time.time() - self.start_time
        if current > 0:
            time_per_frame = elapsed / current
            remaining_frames = total - current
            estimated_remaining = time_per_frame * remaining_frames
            
            self.lbl_time.setText(
                f"Tempo decorrido: {elapsed:.1f}s | "
                f"Estimado restante: {estimated_remaining:.1f}s"
            )
    
    def processing_finished(self, cache):
        """Processamento concluído"""
        self.cache = cache
        elapsed = time.time() - self.start_time
        
        QMessageBox.information(
            self,
            "Processamento Concluído",
            f"✅ Vídeo processado com sucesso!\n\n"
            f"Tempo total: {elapsed:.1f}s\n"
            f"Frames processados: {cache.total_frames}\n"
            f"Detecções de mãos encontradas: {sum(len(v) for v in cache.detections.values())}"
        )
        
        self.accept()
    
    def processing_error(self, error_msg):
        """Erro no processamento"""
        QMessageBox.critical(self, "Erro", f"❌ {error_msg}")
        self.reject()
    
    def cancel_processing(self):
        """Cancela o processamento"""
        reply = QMessageBox.question(
            self,
            "Cancelar",
            "⚠️ Tem certeza que deseja cancelar o processamento?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            self.thread.stop()
            self.reject()



# =============================================================================
# DASHBOARD ANALÍTICO (ATUALIZADO COM GRÁFICOS DA VERSÃO ANTIGA)
# =============================================================================
class DashboardWidget(QWidget):
    """Widget de dashboard com gráficos Plotly - Versão Completa"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        
        # Controles
        ctrl = QHBoxLayout()
        ctrl.addWidget(QLabel("<b>Visualização:</b>"))
        
        self.combo_chart = QComboBox()
        self.combo_chart.addItems([
            "📊 Resumo Executivo (KPIs)",
            "🤲 Análise Detalhada de Mãos (Esq vs Dir)",
            "📅 Sequenciamento Geral (Gantt Chart)",
            "✋ Sequenciamento Mão Esquerda (Gantt Chart)",
            "🤚 Sequenciamento Mão Direita (Gantt Chart)",
            "🎯 Análise de Recursos (HD1/Máquina)",
            "💎 Análise de Valor (TAV/Desperdício)",
            "🔥 Interações (Heatmap Mão x Região)"
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
            
        # 1. Cria DataFrame Robusto
        self.df = pd.DataFrame(events)
        self.takt_time = takt
        
        # 2. Limpeza e Tipagem de Dados (CRÍTICO)
        # Converter colunas numéricas forçando erro a virar 0 ou NaN
        self.df['start_frame'] = pd.to_numeric(self.df.get('start_frame', 0), errors='coerce').fillna(0)
        self.df['end_frame'] = pd.to_numeric(self.df.get('end_frame', 0), errors='coerce').fillna(0)
        self.df['duration'] = pd.to_numeric(self.df.get('duration', 0), errors='coerce').fillna(0)
        
        # Garante que strings vazias sejam tratadas
        self.df['category'] = self.df.get('category', '').fillna("")
        
        # Mapear 'Left'/'Right' para 'Esq'/'Dir'
        hand_map = {'Left': 'Esq', 'Right': 'Dir'}
        self.df['hand'] = self.df.get('hand', '-').fillna("-").replace(hand_map)
        
        self.df['resource'] = self.df.get('resource', 'HD1').fillna("HD1").replace("", "HD1")
        self.df['roi_name'] = self.df.get('roi_name', 'ROI').fillna("ROI")
        
        # ✅ CORREÇÃO: Usar nomes de coluna em inglês internamente
        # Apenas renomear quando necessário para exibição
        self.df = self.df.rename(columns={
            'roi_name': 'Nome',
            'duration': 'Duracao_s',
            'category': 'Categoria',
            'hand': 'Mao',
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
            elif "Mãos" in chart_type:
                html = self.gen_hand_analysis()
            elif "Sequenciamento" in chart_type and "Esquerda" in chart_type:
                html = self.gen_gantt_left_hand()
            elif "Sequenciamento" in chart_type and "Direita" in chart_type:
                html = self.gen_gantt_right_hand()
            elif "Sequenciamento" in chart_type and "Geral" in chart_type:
                html = self.gen_gantt()
            elif "Recursos" in chart_type:
                html = self.gen_resources()
            elif "Valor" in chart_type:
                html = self.gen_value_analysis()
            elif "Interações" in chart_type:
                html = self.gen_heatmap()
            else:
                html = "<h3>Visualização não implementada</h3>"
                
            self.browser.setHtml(html)
        except Exception as e:
            self.browser.setHtml(f"<h3 style='color:red'>❌ Erro: {str(e)}</h3>")
    
    # --- GERADORES DE GRÁFICOS (DA VERSÃO ANTIGA) ---
    
    def gen_summary(self):
        """Resumo Executivo com KPIs + Yamazumi"""
        # KPIs Texto
        total_time = self.df['Duracao_s'].sum()
        total_items = len(self.df)
        tav_time = self.df[self.df['Categoria'] == 'TAV']['Duracao_s'].sum()
        waste_percent = 100 - ((tav_time / total_time) * 100) if total_time > 0 else 0
        
        # Gráfico Yamazumi Geral (Balanceamento por Recurso)
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
                <h2 style="margin: 0; font-size: 48px;">{len(self.df['Nome'].unique())}</h2>
                <p style="margin: 5px 0 0 0; opacity: 0.9;">ROIs Únicas</p>
            </div>
            <div style="text-align: center;">
                <h2 style="margin: 0; font-size: 48px;">{waste_percent:.1f}%</h2>
                <p style="margin: 5px 0 0 0; opacity: 0.9;">% Desperdício (Não TAV)</p>
            </div>
        </div>
        """
        
        return kpi_html + fig.to_html(full_html=False, include_plotlyjs='cdn')
    
    def gen_hand_analysis(self):
        """Análise Detalhada de Mãos"""
        df_h = self.df[self.df['Mao'].isin(['Esq', 'Dir'])]
        
        if df_h.empty:
            return "<h3 style='text-align:center; padding:50px;'>⚠️ Nenhum dado de Mão Esquerda/Direita encontrado.</h3>"
        
        # 1. Pizza: Esq vs Dir
        fig_pie = px.pie(df_h, values='Duracao_s', names='Mao',
                         title="🖐 Balanceamento: Mão Esquerda vs Direita",
                         color='Mao', 
                         color_discrete_map={'Esq': '#1f77b4', 'Dir': '#d62728'})
        
        # 2. Barras: Onde cada mão atuou
        fig_bar = px.histogram(df_h, x="Nome", y="Duracao_s", color="Mao", 
                               barmode="group",
                               title="📊 Tempo Gasto por Região (Comparativo)",
                               color_discrete_map={'Esq': '#1f77b4', 'Dir': '#d62728'},
                               labels={'Duracao_s': 'Duração (s)', 'Nome': 'ROI'})
        
        return fig_pie.to_html(full_html=False, include_plotlyjs='cdn') + \
               fig_bar.to_html(full_html=False, include_plotlyjs=False)
    
    def gen_gantt(self):
        df_g = self.df.sort_values("start_frame").copy()
        
        df_g["start_frame"] = pd.to_numeric(df_g["start_frame"], errors='coerce')
        df_g["end_frame"] = pd.to_numeric(df_g["end_frame"], errors='coerce')
        
        df_g = df_g.reset_index(drop=True)  # Reset index para ter 0, 1, 2, 3...
        df_g['y_position'] = df_g.index  # Posição numérica no eixo Y
        df_g['y_label'] = df_g.apply(lambda x: f"{x['Mao']} - {x['Nome']}", axis=1)  # Label para exibição
        
        fig = go.Figure()
        
        for categoria in df_g["Categoria"].unique():
            df_cat = df_g[df_g["Categoria"] == categoria]
            
            for idx, row in df_cat.iterrows():
                duracao = row["end_frame"] - row["start_frame"]
                is_first = bool(idx == df_cat.index[0])
                
                fig.add_trace(go.Bar(
                    x=[duracao],
                    y=[row['y_position']],
                    name=categoria,
                    orientation='h',
                    marker=dict(color=self.color_map.get(categoria, '#999999')),
                    base=row["start_frame"],
                    text=f"{row['Nome']} ({row['Duracao_s']:.1f}s)",
                    textposition="inside",
                    textfont=dict(color="white", size=10),
                    hovertemplate=f"<b>{row['Nome']}</b><br>" +
                                f"Mão: {row['Mao']}<br>" +
                                f"Início: {row['start_frame']:.0f}<br>" +
                                f"Fim: {row['end_frame']:.0f}<br>" +
                                f"Duração: {row['Duracao_s']:.2f}s<extra></extra>",
                    showlegend=is_first,
                    legendgroup=categoria
                ))
        
        fig.update_layout(
            title="📊 Sequenciamento Geral (Ambas Mãos)",
            xaxis_title="Frames (Tempo)",
            yaxis_title="Mão - ROI / Evento",
            barmode='overlay',
            height=max(400, len(df_g) * 30),
            hovermode='closest',
            plot_bgcolor='rgba(240, 240, 240, 0.5)',
            xaxis=dict(showgrid=True, gridwidth=1, gridcolor='rgba(200, 200, 200, 0.3)'),
            yaxis=dict(
                autorange="reversed",
                tickmode='array',
                tickvals=df_g['y_position'].tolist(),  # Posições numéricas
                ticktext=df_g['y_label'].tolist()  # Labels de texto
            )
        )
        
        return fig.to_html(full_html=False, include_plotlyjs='cdn')
    
    def gen_gantt_left_hand(self):
        df_left = self.df[self.df['Mao'] == 'Esq'].sort_values("start_frame").copy()
        
        if df_left.empty:
            return "<h3 style='text-align:center; padding:50px;'>Nenhum dado para Mão Esquerda</h3>"
        
        df_left["start_frame"] = pd.to_numeric(df_left["start_frame"], errors='coerce')
        df_left["end_frame"] = pd.to_numeric(df_left["end_frame"], errors='coerce')
        
        fig = go.Figure()
        
        for categoria in df_left["Categoria"].unique():
            df_cat = df_left[df_left["Categoria"] == categoria]
            
            for idx, row in df_cat.iterrows():
                duracao = row["end_frame"] - row["start_frame"]
                is_first = bool(idx == df_cat.index[0])
                
                fig.add_trace(go.Bar(
                    x=[duracao],
                    y=[row['Nome']],
                    name=categoria,
                    orientation='h',
                    marker=dict(color=self.color_map.get(categoria, '#999999')),
                    base=row["start_frame"],
                    text=f"{row['Nome']} ({row['Duracao_s']:.1f}s)",
                    textposition="inside",
                    textfont=dict(color="white", size=10),
                    hovertemplate=f"<b>{row['Nome']}</b><br>" +
                                f"Início: {row['start_frame']:.0f}<br>" +
                                f"Fim: {row['end_frame']:.0f}<br>" +
                                f"Duração: {row['Duracao_s']:.2f}s<extra></extra>",
                    showlegend=is_first,
                    legendgroup=categoria
                ))
        
        fig.update_layout(
            title="✋ Sequenciamento - Mão Esquerda",
            xaxis_title="Frames (Tempo)",
            yaxis_title="ROI / Evento",
            barmode='overlay',
            height=max(400, len(df_left) * 30),
            hovermode='closest',
            plot_bgcolor='rgba(240, 240, 240, 0.5)',
            xaxis=dict(showgrid=True, gridwidth=1, gridcolor='rgba(200, 200, 200, 0.3)'),
            yaxis=dict(autorange="reversed")
        )
        
        return fig.to_html(full_html=False, include_plotlyjs='cdn')
        
    def gen_gantt_right_hand(self):
        df_right = self.df[self.df['Mao'] == 'Dir'].sort_values("start_frame").copy()
        
        if df_right.empty:
            return "<h3 style='text-align:center; padding:50px;'>Nenhum dado para Mão Direita</h3>"
        
        df_right["start_frame"] = pd.to_numeric(df_right["start_frame"], errors='coerce')
        df_right["end_frame"] = pd.to_numeric(df_right["end_frame"], errors='coerce')
        
        fig = go.Figure()
        
        for categoria in df_right["Categoria"].unique():
            df_cat = df_right[df_right["Categoria"] == categoria]
            
            for idx, row in df_cat.iterrows():
                duracao = row["end_frame"] - row["start_frame"]
                is_first = bool(idx == df_cat.index[0])
                
                fig.add_trace(go.Bar(
                    x=[duracao],
                    y=[row['Nome']],
                    name=categoria,
                    orientation='h',
                    marker=dict(color=self.color_map.get(categoria, '#999999')),
                    base=row["start_frame"],
                    text=f"{row['Nome']} ({row['Duracao_s']:.1f}s)",
                    textposition="inside",
                    textfont=dict(color="white", size=10),
                    hovertemplate=f"<b>{row['Nome']}</b><br>" +
                                f"Início: {row['start_frame']:.0f}<br>" +
                                f"Fim: {row['end_frame']:.0f}<br>" +
                                f"Duração: {row['Duracao_s']:.2f}s<extra></extra>",
                    showlegend=is_first,
                    legendgroup=categoria
                ))
        
        fig.update_layout(
            title="🤚 Sequenciamento - Mão Direita",
            xaxis_title="Frames (Tempo)",
            yaxis_title="ROI / Evento",
            barmode='overlay',
            height=max(400, len(df_right) * 30),
            hovermode='closest',
            plot_bgcolor='rgba(240, 240, 240, 0.5)',
            xaxis=dict(showgrid=True, gridwidth=1, gridcolor='rgba(200, 200, 200, 0.3)'),
            yaxis=dict(autorange="reversed")
        )
        
        return fig.to_html(full_html=False, include_plotlyjs='cdn')
            
    def gen_resources(self):
        """Análise de Recursos"""
        fig = px.sunburst(self.df, 
                          path=['Recurso', 'Categoria', 'Nome'], 
                          values='Duracao_s',
                          title="🎯 Distribuição de Carga por Recurso (Detalhado)",
                          color='Categoria', 
                          color_discrete_map=self.color_map)
        
        return fig.to_html(full_html=False, include_plotlyjs='cdn')
    
    def gen_value_analysis(self):
        """Análise de Valor Agregado"""
        df_agg = self.df.groupby('Categoria')['Duracao_s'].sum().reset_index()
        
        fig = px.bar(df_agg, x='Categoria', y='Duracao_s', 
                     color='Categoria',
                     text_auto='.2f', 
                     title="💎 Análise de Valor Agregado (Total)",
                     color_discrete_map=self.color_map,
                     labels={'Duracao_s': 'Duração (s)', 'Categoria': 'Categoria'})
        
        return fig.to_html(full_html=False, include_plotlyjs='cdn')
    
    def gen_heatmap(self):
        """Heatmap: Qual Mão interage com Qual ROI"""
        df_h = self.df[self.df['Mao'].isin(['Esq', 'Dir'])]
        
        if df_h.empty:
            return "<h3 style='text-align:center; padding:50px;'>⚠️ Sem dados de mão para Heatmap.</h3>"
        
        # Pivot Table
        pivot = df_h.pivot_table(index='Nome', columns='Mao', 
                                 values='Duracao_s', aggfunc='sum').fillna(0)

        pivot = pivot[pivot.columns[::-1]]
        
        fig = px.imshow(pivot, text_auto=True, aspect="auto",
                        title="📥 Matriz de Intensidade: Região x Mão (Segundos)",
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
                <title>Relatório T&M Analytics</title>
                <style>
                    body {{ font-family: Arial, sans-serif; margin: 20px; background: #f5f5f5; }}
                    h1 {{ color: #333; text-align: center; }}
                    hr {{ border: none; border-top: 2px solid #ddd; margin: 40px 0; }}
                </style>
            </head>
            <body>
                <h1>📊 Relatório Completo - T&M Analytics</h1>
                <p style="text-align:center; color:#666;">Gerado em: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}</p>
                <hr>
                {self.gen_summary()}
                <hr>
                {self.gen_hand_analysis()}
                <hr>
                <h2>Gráficos de sequenciamento</h2>
                {self.gen_gantt()}
                <hr>
                {self.gen_gantt_left_hand()}
                <hr>
                {self.gen_gantt_right_hand()}
                <hr>
                {self.gen_resources()}
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
# APLICAÇÃO PRINCIPAL
# =============================================================================
class TMAnalyzerApp(QMainWindow):
    """Aplicação principal integrada"""
    
    def __init__(self):
        super().__init__()
        self.setWindowTitle("🎯 T&M Advanced Analyzer - Hand Tracker")
        self.setGeometry(100, 100, 1600, 900)
        
        # Estado
        self.video_mode = None  # 'camera' ou 'file'
        self.video_path = None
        self.cap = None
        self.fps = 30
        self.total_frames = 0
        self.current_frame = 0
        
        # Processador
        self.processor = VideoProcessor()
        
        # Dados
        self.events = []
        
        # Timers
        self.process_timer = QTimer()
        self.process_timer.timeout.connect(self.process_frame)
        
        self.is_paused = False
        self.is_video_processed = False
        
        self.loop_range = None
        
        self.playback_speed = 1.0  # Velocidade de reprodução (novo)
        self.is_seeking = False    # Flag para saber se usuário está movendo o slider
        
        self.operation_sequence = []
        
        self.setup_ui()
    
    def toggle_pause(self):
        """Alterna entre Pausar e Continuar sem fechar a conexão"""
        if not self.cap:
            return

        if not self.is_paused:
            # --- AÇÃO: PAUSAR ---
            self.process_timer.stop()
            self.is_paused = True
            
            # Atualizar UI
            self.btn_action.setText("▶️ Continuar")
            self.btn_action.setStyleSheet("background: #27ae60; color: white; padding: 8px; font-weight: bold;")
            self.lbl_status.setText("⏸️ Status: PAUSADO (Clique em Continuar para retomar)")
            
            # Se estiver em modo arquivo, muda o botão do player também
            if self.video_mode == 'file':
                self.btn_play_pause.setText("▶️ Play")
                
        else:
            # --- AÇÃO: CONTINUAR ---
            self.is_paused = False
            
            # Truque para Câmera: Limpar buffer para evitar lag
            if self.video_mode == 'camera':
                for _ in range(5): # Lê e descarta 5 frames rápidos
                    self.cap.read()
            
            # Reiniciar timer
            fps_delay = int(1000 // (int(self.fps) * self.playback_speed)) if self.fps > 0 else 30
            self.process_timer.start(fps_delay)
            
            # Atualizar UI
            self.btn_action.setText("⏸️ Pausar")
            self.btn_action.setStyleSheet("background: #e74c3c; color: white; padding: 8px; font-weight: bold;")
            self.lbl_status.setText("🟢 Status: Processando...")

            if self.video_mode == 'file':
                self.btn_play_pause.setText("⏸️ Pause")

    def close_session(self):
        """Limpeza interna real (só chamada ao trocar de fonte ou sair)"""
        self.stop_processing()
        
        if self.cap:
            self.cap.release()
            self.cap = None
            
        self.video_mode = None
        self.events = []
        self.table.setRowCount(0)
        self.current_frame = 0
        self.loop_range = None
        self.is_paused = False
        self.is_video_processed = False
        
        
        self.btn_action.setEnabled(False)
        self.btn_action.setText("⏸️ Pausar")
        self.btn_action.setStyleSheet("background: #95a5a6; color: white; padding: 8px;")
        
    def play_event_loop(self, row):
        """Prepara o vídeo para tocar em loop o intervalo do evento selecionado"""
        if self.video_mode != 'file' or not self.cap:
            QMessageBox.warning(self, "Aviso", "⚠️ Carregue um vídeo primeiro!")
            return

        try:
            # Extrair frames
            start_frame_item = self.table.item(row, 1)
            end_frame_item = self.table.item(row, 2)
            roi_name = self.table.item(row, 0).text() if self.table.item(row, 0) else "ROI"
            
            if not start_frame_item or not end_frame_item:
                QMessageBox.warning(self, "Erro", "⚠️ Frames não foram preenchidos!")
                return
            
            start_frame_str = start_frame_item.text().strip()
            end_frame_str = end_frame_item.text().strip()
            
            if not start_frame_str or not end_frame_str:
                QMessageBox.warning(self, "Erro", "⚠️ Frames vazios!")
                return
            
            start_frame = int(float(start_frame_str))
            end_frame = int(float(end_frame_str))
            
            # Validações
            if start_frame < 0 or end_frame < 0:
                QMessageBox.warning(self, "Erro", "⚠️ Frames não podem ser negativos!")
                return
            
            if start_frame >= end_frame:
                QMessageBox.warning(self, "Erro", 
                    f"⚠️ Frame de início ({start_frame}) deve ser menor que fim ({end_frame})!")
                return
            
            if start_frame >= self.total_frames:
                QMessageBox.warning(self, "Erro", 
                    f"⚠️ Frame de início ({start_frame}) além do total ({self.total_frames})!")
                return
            
            # ✅ Configurar loop ANTES de buscar
            self.loop_range = (start_frame, end_frame)
            
            # ✅ Pular para o início
            self.seek_video(start_frame)
            
            self.spin_goto_frame.blockSignals(True)
            self.spin_goto_frame.setValue(start_frame)
            self.spin_goto_frame.blockSignals(False)
            
            # ✅ Garantir que está tocando
            if self.is_paused:
                self.toggle_pause()
            
            # ✅ Atualizar status
            duration_frames = end_frame - start_frame
            duration_seconds = duration_frames / self.fps
            self.lbl_status.setText(
                f"🔄 LOOP ATIVO: {roi_name}\n"
                f"Frames: {start_frame}→{end_frame} ({duration_frames} frames = {duration_seconds:.2f}s)"
            )

        except ValueError as e:
            QMessageBox.critical(self, "Erro", f"⚠️ Erro ao converter frames:\n{str(e)}")
        except Exception as e:
            QMessageBox.critical(self, "Erro", f"⚠️ Erro ao configurar loop:\n{str(e)}")
                 
    def update_cycle_roi_combo(self):
        current_selection = self.combo_cycle_roi.currentText()
        
        self.combo_cycle_roi.clear()
        self.combo_cycle_roi.addItem("(Nenhuma)")
        
        for roi_data in self.canvas.final_rois:
            roi_name = roi_data.get('name', 'ROI')
            self.combo_cycle_roi.addItem(roi_name)
        
        # Tentar restaurar seleção anterior
        index = self.combo_cycle_roi.findText(current_selection)
        if index >= 0:
            self.combo_cycle_roi.setCurrentIndex(index)
                
    def setup_ui(self):
        """Configura interface"""
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        layout = QVBoxLayout(main_widget)
        
        # === BARRA SUPERIOR ===
        top_bar = QHBoxLayout()
        
        SHADOW_RADIUS = 5
        SHADOW_OFFSET_X, SHADOW_OFFSET_Y = 1, 1
        SHADOW_COLOR = QColor(0, 0, 0, 153)
        
        # ===================================================
        # BOTÃO CÂMERA
        # ===================================================
        # CORREÇÃO: Usar self.btn_camera em vez de btn_camera
        self.btn_camera = QPushButton("📹 Câmera Tempo Real") 
        self.btn_camera.clicked.connect(self.start_camera)
        self.btn_camera.setToolTip("Inicia captura de vídeo da webcam em tempo real.")
        self.btn_camera.setStyleSheet("color: white; padding: 8px; font-weight: bold; border-radius: 4px;")
        
        # Aplicar Sombra
        shadow_effect = QGraphicsDropShadowEffect(self.btn_camera) # AGORA CORRETO
        shadow_effect.setBlurRadius(SHADOW_RADIUS)
        shadow_effect.setOffset(SHADOW_OFFSET_X, SHADOW_OFFSET_Y)
        shadow_effect.setColor(SHADOW_COLOR) 
        self.btn_camera.setGraphicsEffect(shadow_effect)
        
        # Adicionar à barra
        top_bar.addWidget(self.btn_camera) # CORREÇÃO: Adicionar o atributo self.

        # ===================================================
        # BOTÃO VÍDEO
        # ===================================================
        # CORREÇÃO: Usar self.btn_video em vez de btn_video
        self.btn_video = QPushButton("🎬 Carregar Vídeo")
        self.btn_video.clicked.connect(self.load_video)
        self.btn_video.setToolTip("Selecionar vídeo para análise.")
        self.btn_video.setStyleSheet("color: white; padding: 8px; font-weight: bold; border-radius: 4px;")
        
        # Aplicar Sombra
        shadow_effect2 = QGraphicsDropShadowEffect(self.btn_video) # AGORA CORRETO
        shadow_effect2.setBlurRadius(SHADOW_RADIUS)
        shadow_effect2.setOffset(SHADOW_OFFSET_X, SHADOW_OFFSET_Y)
        shadow_effect2.setColor(SHADOW_COLOR) 
        self.btn_video.setGraphicsEffect(shadow_effect2)
        
        # Adicionar à barra
        top_bar.addWidget(self.btn_video) # CORREÇÃO: Adicionar o atributo self.
        
        # ===================================================
        # BOTÃO AÇÃO (Pausa/Play)
        # ===================================================
        # Este já estava correto, mantido para referência
        self.btn_action = QPushButton("⏸️ Pausar")
        self.btn_action.clicked.connect(self.toggle_pause)
        self.btn_action.setStyleSheet("color: white; padding: 8px; font-weight: bold; border-radius: 4px;")
        
        # Aplicar Sombra
        shadow_effect3 = QGraphicsDropShadowEffect(self.btn_action)
        shadow_effect3.setBlurRadius(SHADOW_RADIUS)
        shadow_effect3.setOffset(SHADOW_OFFSET_X, SHADOW_OFFSET_Y)
        shadow_effect3.setColor(SHADOW_COLOR) 
        self.btn_action.setGraphicsEffect(shadow_effect3)
        self.btn_action.setEnabled(False)
        top_bar.addWidget(self.btn_action)
        
        top_bar.addWidget(QLabel("|"))
        top_bar.addWidget(QLabel("<b>Takt Time (s):</b>"))
        self.spin_takt = QDoubleSpinBox()
        self.spin_takt.setRange(0, 9999)
        self.spin_takt.setValue(10.0)
        top_bar.addWidget(self.spin_takt)
        
        top_bar.addWidget(QLabel("|"))
        top_bar.addWidget(QLabel("<b>ROI de Início do Ciclo:</b>"))
        self.combo_cycle_roi = QComboBox()
        self.combo_cycle_roi.addItem("(Nenhuma)")
        self.combo_cycle_roi.setToolTip("Selecione a ROI que marca o início de cada ciclo")
        top_bar.addWidget(self.combo_cycle_roi)

        btn_analyze_cycle = QPushButton("📊 Analisar Ciclos")
        btn_analyze_cycle.clicked.connect(self.analyze_cycles)
        btn_analyze_cycle.setStyleSheet("color: white; padding: 8px; font-weight: bold; border-radius: 4px;")
        top_bar.addWidget(btn_analyze_cycle)
        
        btn_config_sequence = QPushButton("⚙️ Configurar Sequência")
        btn_config_sequence.clicked.connect(self.config_sequence)
        btn_config_sequence.setStyleSheet("color: white; padding: 8px; font-weight: bold; border-radius: 4px;")
        btn_config_sequence.setToolTip("Define a sequência padrão de operações do ciclo")
        top_bar.addWidget(btn_config_sequence)
        
        top_bar.addStretch()
        
        layout.addLayout(top_bar)
        
        # === CORPO PRINCIPAL ===
        splitter = QSplitter(Qt.Orientation.Horizontal)
        
        # --- ESQUERDA: CONTROLES E DADOS ---
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        
        self.tabs = QTabWidget()
        
        # TAB 1: ROIs
        tab_roi = QWidget()
        roi_layout = QVBoxLayout(tab_roi)
        
        grp_roi = QGroupBox("Gestão de ROIs Poligonais")
        roi_ctrl = QVBoxLayout(grp_roi)
        
        # ===================================================
        # BOTÃO DESENHAR NOVA ROI
        # ===================================================
        btn_draw = QPushButton("✏️ Desenhar Nova ROI")
        btn_draw.clicked.connect(self.enable_drawing)
        # Dica: Adicione background-color e border-radius ao QSS para melhor visual
        btn_draw.setStyleSheet("color: white; padding: 6px; border-radius: 4px; border: 1px solid #C7C7C7") 
        
        # Aplicar Sombra
        shadow_effect_draw = QGraphicsDropShadowEffect(btn_draw)
        shadow_effect_draw.setBlurRadius(SHADOW_RADIUS)
        shadow_effect_draw.setOffset(SHADOW_OFFSET_X, SHADOW_OFFSET_Y)
        shadow_effect_draw.setColor(SHADOW_COLOR) 
        btn_draw.setGraphicsEffect(shadow_effect_draw)
        
        roi_ctrl.addWidget(btn_draw)
        
        # ===================================================
        # BOTÕES DE GERENCIAMENTO (SALVAR/CARREGAR/LIMPAR)
        # ===================================================
        h_roi = QHBoxLayout()
        
        # --- Salvar ROIs ---
        btn_save_roi = QPushButton("💾 Salvar ROIs")
        btn_save_roi.clicked.connect(self.save_rois)
        # Dica: Adicione background-color e border-radius ao QSS
        btn_save_roi.setStyleSheet("color: white; padding: 6px; border-radius: 4px; border: 1px solid #C7C7C7")
        
        # Aplicar Sombra
        shadow_effect_save = QGraphicsDropShadowEffect(btn_save_roi)
        shadow_effect_save.setBlurRadius(SHADOW_RADIUS)
        shadow_effect_save.setOffset(SHADOW_OFFSET_X, SHADOW_OFFSET_Y)
        shadow_effect_save.setColor(SHADOW_COLOR) 
        btn_save_roi.setGraphicsEffect(shadow_effect_save)
        
        h_roi.addWidget(btn_save_roi)
        
        # --- Carregar ROIs ---
        btn_load_roi = QPushButton("📂 Carregar ROIs")
        btn_load_roi.clicked.connect(self.load_rois)
        btn_load_roi.setStyleSheet("color: white; padding: 6px; border-radius: 4px; border: 1px solid #C7C7C7")
        
        # Aplicar Sombra
        shadow_effect_load = QGraphicsDropShadowEffect(btn_load_roi)
        shadow_effect_load.setBlurRadius(SHADOW_RADIUS)
        shadow_effect_load.setOffset(SHADOW_OFFSET_X, SHADOW_OFFSET_Y)
        shadow_effect_load.setColor(SHADOW_COLOR) 
        btn_load_roi.setGraphicsEffect(shadow_effect_load)
        
        h_roi.addWidget(btn_load_roi)
        
        # --- Limpar Todas ---
        btn_clear_roi = QPushButton("🗑️ Limpar Todas")
        btn_clear_roi.clicked.connect(self.clear_rois)
        btn_clear_roi.setStyleSheet("color: white; padding: 6px; border-radius: 4px; border: 1px solid #C7C7C7")
        
        # Aplicar Sombra
        shadow_effect_clear = QGraphicsDropShadowEffect(btn_clear_roi)
        shadow_effect_clear.setBlurRadius(SHADOW_RADIUS)
        shadow_effect_clear.setOffset(SHADOW_OFFSET_X, SHADOW_OFFSET_Y)
        shadow_effect_clear.setColor(SHADOW_COLOR) 
        btn_clear_roi.setGraphicsEffect(shadow_effect_clear)
        
        h_roi.addWidget(btn_clear_roi)
        roi_ctrl.addLayout(h_roi)
        
        self.lbl_roi_info = QLabel("ROIs: 0")
        self.lbl_roi_info.setStyleSheet("color: #666; font-style: italic;")
        roi_ctrl.addWidget(self.lbl_roi_info)
        
        roi_layout.addWidget(grp_roi)
        
        # Instruções
        instructions = QLabel("""
        <b>📖 Instruções de Desenho:</b><br>
        • <b>Click Esquerdo:</b> Adicionar vértice<br>
        • <b>Click Direito:</b> Finalizar polígono (mín. 3 pontos)<br>
        """)
        instructions.setStyleSheet("padding: 10px; border-radius: 5px;")
        roi_layout.addWidget(instructions)
        
        roi_layout.addStretch()
        self.tabs.addTab(tab_roi, "1️⃣ ROIs")
        
        # TAB 2: EVENTOS E TABELA
        tab_events = QWidget()
        events_layout = QVBoxLayout(tab_events)
        
        evt_ctrl = QHBoxLayout()
        btn_add_evt = QPushButton("➕ Adicionar Manual")
        btn_add_evt.clicked.connect(self.add_manual_event)
        evt_ctrl.addWidget(btn_add_evt)
        
        btn_del_evt = QPushButton("➖ Remover")
        btn_del_evt.clicked.connect(self.delete_event)
        evt_ctrl.addWidget(btn_del_evt)
        
        btn_clear_evt = QPushButton("🗑️ Limpar Todos")
        btn_clear_evt.clicked.connect(self.clear_events)
        evt_ctrl.addWidget(btn_clear_evt)
        
        events_layout.addLayout(evt_ctrl)
        
        # Tabela
        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels([
            "Nome/ROI", "Início (F)", "Fim (F)", "Duração (s)", 
            "Categoria", "Mão", "Recurso"
        ])
        header = self.table.horizontalHeader()
        
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)  # Início (F)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)  # Fim (F)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)  # Duração (s)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Fixed)             # Categoria (botões)
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)  # Mão
        header.setSectionResizeMode(6, QHeaderView.ResizeMode.ResizeToContents)  # Recurso
        
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        
        self.table.setColumnWidth(4, 106)
        
        self.table.cellChanged.connect(self.on_table_changed)
        self.table.verticalHeader().sectionClicked.connect(self.play_event_loop)
        events_layout.addWidget(self.table)
        
        self.tabs.addTab(tab_events, "2️⃣ Eventos")
        
        # TAB 3: DASHBOARD
        tab_dash = QWidget()
        dash_layout = QVBoxLayout(tab_dash)
        
        btn_refresh = QPushButton("🔄 ATUALIZAR DASHBOARD")
        btn_refresh.clicked.connect(self.refresh_dashboard)
        btn_refresh.setStyleSheet("background: #16a085; color: white; padding: 10px; font-weight: bold; font-size: 14px;")
        dash_layout.addWidget(btn_refresh)
        
        self.dashboard = DashboardWidget()
        dash_layout.addWidget(self.dashboard)
        
        self.tabs.addTab(tab_dash, "3️⃣ Dashboard")
        
        left_layout.addWidget(self.tabs)
        
        # Player Controls (para modo vídeo)
        self.player_group = QGroupBox("🎮 Controles de Vídeo")
        player_layout = QVBoxLayout(self.player_group)
        
        # === LINHA 1: SLIDER ===
        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.sliderMoved.connect(self.on_slider_moved)  # ALTERADO
        self.slider.setMouseTracking(True)
        player_layout.addWidget(self.slider)
        
        # === LINHA 2: CONTROLES PRINCIPAIS ===
        h_player_main = QHBoxLayout()
        
        self.btn_play_pause = QPushButton("▶️ Play")
        self.btn_play_pause.clicked.connect(self.toggle_play_pause)
        self.btn_play_pause.setFixedWidth(80)
        h_player_main.addWidget(self.btn_play_pause)
        
        # Botões Frame-by-Frame (NOVO)
        btn_prev_frame = QPushButton("⏮ -1F")
        btn_prev_frame.clicked.connect(self.prev_frame)
        btn_prev_frame.setFixedWidth(70)
        h_player_main.addWidget(btn_prev_frame)
        
        btn_next_frame = QPushButton("+1F ⏭")
        btn_next_frame.clicked.connect(self.next_frame)
        btn_next_frame.setFixedWidth(70)
        h_player_main.addWidget(btn_next_frame)
        
        h_player_main.addWidget(QLabel("|"))
        
        # Label de tempo
        self.lbl_time = QLabel("00:00 / 00:00")
        self.lbl_time.setFixedWidth(120)
        h_player_main.addWidget(self.lbl_time)
        
        h_player_main.addWidget(QLabel("|"))
        
        # Campo de pulo de frame (NOVO)
        h_player_main.addWidget(QLabel("Pular para Frame:"))
        self.spin_goto_frame = QDoubleSpinBox()
        self.spin_goto_frame.setRange(0, 10000)
        self.spin_goto_frame.setValue(0)
        self.spin_goto_frame.setDecimals(0)
        self.spin_goto_frame.setFixedWidth(80)
        h_player_main.addWidget(self.spin_goto_frame)
        
        btn_goto = QPushButton("✓ Ir")
        btn_goto.clicked.connect(self.goto_frame)
        btn_goto.setFixedWidth(50)
        h_player_main.addWidget(btn_goto)
        
        h_player_main.addStretch()
        
        player_layout.addLayout(h_player_main)
        
        # === LINHA 3: CONTROLES DE VELOCIDADE ===
        h_speed = QHBoxLayout()
        
        h_speed.addWidget(QLabel("<b>Velocidade:</b>"))
        
        # Botões de velocidade predefinida (NOVO)
        speeds = [0.2, 0.5, 1.0, 1.5, 2.0, 5.0]
        self.speed_buttons = {}
        
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
        
        h_speed.addWidget(QLabel("|"))
        
        # Slider de velocidade customizada (NOVO)
        h_speed.addWidget(QLabel("Custom:"))
        self.slider_speed = QSlider(Qt.Orientation.Horizontal)
        self.slider_speed.setRange(10, 500)  # 0.1x a 5x
        self.slider_speed.setValue(100)      # 1x
        self.slider_speed.setFixedWidth(150)
        self.slider_speed.setToolTip("Velocidade customizada (0.1x a 5x)")
        self.slider_speed.valueChanged.connect(self.on_speed_slider_changed)
        h_speed.addWidget(self.slider_speed)
        
        self.lbl_custom_speed = QLabel("1.00x")
        self.lbl_custom_speed.setFixedWidth(50)
        h_speed.addWidget(self.lbl_custom_speed)
        
        h_speed.addStretch()
        
        player_layout.addLayout(h_speed)
        
        left_layout.addWidget(self.player_group)
        self.player_group.setVisible(False)
        
        # Info
        self.lbl_status = QLabel("💡 Status: Aguardando fonte de vídeo...")
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
        
    # ========== CONTROLE DE VÍDEO ==========
    
    def start_camera(self):
        """Inicia captura da câmera"""
        self.close_session() # Limpa sessão anterior
        
        self.cap = cv2.VideoCapture(0)
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, FRAME_WIDTH)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, FRAME_HEIGHT)
        
        if not self.cap.isOpened():
            QMessageBox.critical(self, "Erro", "❌ Não foi possível abrir a câmera!")
            return
        
        self.video_mode = 'camera'
        self.fps = 30
        self.processor.reset_tracking()
        self.player_group.setVisible(False)
        
        # Ativa o botão de ação
        self.btn_action.setEnabled(True)
        self.btn_action.setText("⏸️ Pausar")
        self.btn_action.setStyleSheet("background: #e74c3c; color: white; padding: 8px; font-weight: bold;")
        
        self.process_timer.start(1000 // FPS_TARGET)
        self.lbl_status.setText("🟢 Status: Câmera ativa")
        
    def load_video(self):
        """Carrega arquivo de vídeo"""
        path, _ = QFileDialog.getOpenFileName(self, "Selecionar Vídeo", "", "Vídeos (*.mp4 *.avi *.mov *.mkv)")
        
        if not path:
            return
        
        self.close_session() # Limpa sessão anterior
        
        # Verificar se existe cache salvo
        cache_path = path + ".hands_cache.json"
        use_existing_cache = False
        
        if Path(cache_path).exists():
            reply = QMessageBox.question(
                self,
                "Cache Encontrado",
                f"📦 Foi encontrado um cache de detecções de mãos anterior para este vídeo.\n\n"
                f"Deseja usar o cache existente?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.Yes
            )
            
            if reply == QMessageBox.StandardButton.Yes:
                use_existing_cache = True
        
        # Carregar ou criar cache
        if use_existing_cache:
            cache = MediaPipeCache()
            if cache.load_from_file(cache_path):
                self.processor.set_detection_cache(cache)
                QMessageBox.information(self, "Cache Carregado", "✅ Cache carregado com sucesso!")
            else:
                QMessageBox.warning(self, "Erro", "❌ Erro ao carregar cache. Processando novamente...")
                use_existing_cache = False
        
        if not use_existing_cache:
            # Processar vídeo com dialog de progresso
            dialog = MediaPipePreprocessDialog(self, path)
            dialog.start_processing()
            
            if dialog.exec() == QDialog.DialogCode.Accepted:
                cache = dialog.cache
                self.processor.set_detection_cache(cache)
                
                # Salvar cache
                cache.save_to_file(cache_path)
                QMessageBox.information(self, "Cache Salvo", f"✅ Cache salvo em:\n{cache_path}")
            else:
                # Usuário cancelou
                return
        
        # Abrir vídeo normalmente
        self.cap = cv2.VideoCapture(path)
        if not self.cap.isOpened():
            QMessageBox.critical(self, "Erro", f"❌ Não foi possível abrir: {path}")
            return
        
        self.video_mode = 'file'
        self.video_path = path
        
        self.fps = self.cap.get(cv2.CAP_PROP_FPS)
        if self.fps <= 0:
            self.fps = 30
            
        self.total_frames = int(self.cap.get(cv2.CAP_PROP_FRAME_COUNT))
        self.current_frame = 0
        
        self.slider.setMaximum(self.total_frames)
        self.spin_goto_frame.setMaximum(self.total_frames)
        self.slider.setValue(0)
        self.processor.reset_tracking()
        self.player_group.setVisible(True)
        
        # Iniciar pausado
        self.is_paused = True
        self.is_video_processed = False
        
        self.btn_action.setEnabled(True)
        self.btn_action.setText("▶️ Continuar")
        self.btn_action.setStyleSheet("background: #27ae60; color: white; padding: 8px; font-weight: bold;")
        
        self.btn_play_pause.setText("▶️ Play")
        
        self.lbl_status.setText(f"⏸️ Vídeo Carregado (Pré-processado): {Path(path).name}")
        
        # Carregar primeiro frame
        ret, first_frame = self.cap.read()
        if ret:
            h, w = first_frame.shape[:2]
            
            for idx, roi_data in enumerate(self.canvas.final_rois):
                poly_points = roi_data['points']
                roi_name = roi_data.get('name', f"ROI {idx}")
                if len(poly_points) < 3: continue
                
                color = ROI_COLORS[idx % len(ROI_COLORS)]
                points_px = [(int(x*w), int(y*h)) for x, y in poly_points]
                poly_array = np.array(points_px, dtype=np.int32)
                cv2.polylines(first_frame, [poly_array], True, color, 3)
                cv2.putText(first_frame, roi_name, points_px[0], 
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
            
            rgb = cv2.cvtColor(first_frame, cv2.COLOR_BGR2RGB)
            qimg = QImage(rgb.data, w, h, rgb.strides[0], QImage.Format.Format_RGB888).copy()
            self.canvas.update_frame(qimg)
            
            self.lbl_time.setText(f"00:00 / {int(self.total_frames/self.fps//60):02d}:{int(self.total_frames/self.fps%60):02d}")
        
        self.loop_range = None
        
    def stop_processing(self):
        """Para processamento"""
        self.process_timer.stop()
        
        self.lbl_status.setText("⏹️ Status: Parado")
        
    def toggle_play_pause(self):
        """Play/Pause do player inferior (redireciona para o controle principal)"""
        self.toggle_pause()

    def set_playback_speed(self, speed):
        """Define velocidade de reprodução (0.2x, 0.5x, 1x, 1.5x, 2x, 5x)"""
        self.playback_speed = speed
        
        # Atualizar UI dos botões
        for btn_speed, btn in self.speed_buttons.items():
            if btn_speed == speed:
                btn.setChecked(True)
                btn.setStyleSheet("background: #27ae60; color: white; font-weight: bold;")
            else:
                btn.setChecked(False)
                btn.setStyleSheet("")
        
        # Desmarcar slider customizado
        self.slider_speed.blockSignals(True)
        self.slider_speed.setValue(int(speed * 100))
        self.slider_speed.blockSignals(False)
        self.lbl_custom_speed.setText(f"{speed:.2f}x")
        
        # Restart timer com nova velocidade
        if not self.is_paused and self.cap:
            self.process_timer.stop()
            fps_delay = int(1000 // (int(self.fps) * self.playback_speed))
            self.process_timer.start(fps_delay)
    
    def on_speed_slider_changed(self, value):
        """Callback do slider de velocidade customizada"""
        speed = value / 100.0  # Converter para 0.1x a 5x
        self.playback_speed = speed
        self.lbl_custom_speed.setText(f"{speed:.2f}x")
        
        # Desmarcar todos os botões predefinidos
        for btn in self.speed_buttons.values():
            btn.setChecked(False)
            btn.setStyleSheet("")
        
        # Restart timer
        if not self.is_paused and self.cap:
            self.process_timer.stop()
            fps_delay = int(1000 // (int(self.fps) * self.playback_speed))
            self.process_timer.start(fps_delay)
    
    def prev_frame(self):
        """Retrocede um frame"""
        if not self.cap or self.video_mode != 'file':
            return
        
        # Pausar se estiver tocando
        if not self.is_paused:
            self.toggle_pause()
        
        # Retroceder 1 frame
        new_frame = max(0, self.current_frame - 1)
        self.seek_video(new_frame)
    
    def next_frame(self):
        """Avança um frame"""
        if not self.cap or self.video_mode != 'file':
            return
        
        # Pausar se estiver tocando
        if not self.is_paused:
            self.toggle_pause()
        
        # Avançar 1 frame
        new_frame = min(self.total_frames - 1, self.current_frame + 1)
        self.seek_video(new_frame)
    
    def goto_frame(self):
        """Pula para um frame específico"""
        if not self.cap or self.video_mode != 'file':
            return
        
        target_frame = int(self.spin_goto_frame.value())
        target_frame = max(0, min(self.total_frames - 1, target_frame))
        
        # Pausar se estiver tocando
        if not self.is_paused:
            self.toggle_pause()
        
        self.seek_video(target_frame)
    
    def on_slider_moved(self, value):
        """Slot para quando o slider é movido pelo usuário"""
        if not self.cap or self.video_mode != 'file':
            return
        
        self.is_seeking = True
        self.seek_video(value)
        self.is_seeking = False
  
    def seek_video(self, frame):
        """Busca frame específico no vídeo"""
        if self.video_mode != 'file' or not self.cap:
            return
        
        # Definir posição
        self.cap.set(cv2.CAP_PROP_POS_FRAMES, frame)
        
        # Ler frame
        ret, img = self.cap.read()
        if ret:
            self.current_frame = frame
            h, w = img.shape[:2]
            
            # Desenhar ROIs visualmente
            for roi_data in self.canvas.final_rois:
                poly_points = roi_data['points']
                roi_name = roi_data['name']
                if len(poly_points) < 3:
                    continue
                
                points_px = [(int(x*w), int(y*h)) for x, y in poly_points]
                poly_array = np.array(points_px, dtype=np.int32)
                
                cv2.polylines(img, [poly_array], True, (200, 200, 200), 2)
                cv2.putText(img, roi_name, (points_px[0][0], points_px[0][1]), 
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (200, 200, 200), 1)
            
            # Exibir
            rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
            qimg = QImage(rgb.data, w, h, rgb.strides[0], QImage.Format.Format_RGB888).copy()
            self.canvas.update_frame(qimg)
            
            # Atualizar label de tempo
            current_time = self.current_frame / self.fps
            total_time = self.total_frames / self.fps
            self.lbl_time.setText(
                f"{int(current_time//60):02d}:{int(current_time%60):02d} / "
                f"{int(total_time//60):02d}:{int(total_time%60):02d}"
            ) 
        
    def process_frame(self):
        """Processa frame com suporte a loop"""
        if not self.cap or not self.cap.isOpened():
            return
        
        # ============================================
        # PASSO 1: VERIFICAR SE PRECISA VOLTAR
        # ============================================
        if self.video_mode == 'file' and self.loop_range:
            loop_start, loop_end = self.loop_range
            current_pos = int(self.cap.get(cv2.CAP_PROP_POS_FRAMES))
            
            # ✅ Se PASSOU do fim, volta ANTES de ler
            if current_pos >= loop_end:
                self.cap.set(cv2.CAP_PROP_POS_FRAMES, loop_start)
                current_pos = loop_start
        
        # ============================================
        # PASSO 2: LER FRAME
        # ============================================
        ret, frame = self.cap.read()
        
        if not ret:
            if self.video_mode == 'file':
                self.stop_processing()
                self.is_paused = False
                self.is_video_processed = True
                QMessageBox.information(self, "Fim", "✅ Vídeo finalizado! Recursos mantidos para análise de eventos.")
                self.lbl_status.setText("▶️ Play")
                return
        
        # ✅ CORREÇÃO: Sempre habilitar detecção quando usando cache
        run_detection = True  # Sempre processar, mesmo com cache
        
        if self.video_mode == 'file':
            current_frame_num = int(self.cap.get(cv2.CAP_PROP_POS_FRAMES))
            self.processor.set_current_frame(current_frame_num, self.fps)
        
        # Processar com IA APENAS se NÃO estiver em loop
        if self.video_mode == 'file' and self.loop_range:
            loop_start, loop_end = self.loop_range
            current_pos = int(self.cap.get(cv2.CAP_PROP_POS_FRAMES))
            
            # ✅ Se está dentro do range de loop, pular processamento IA
            if loop_start <= current_pos < loop_end:
                # Apenas exibir frame sem processar IA
                h, w = frame.shape[:2]
                
                # Apenas desenhar ROIs visuais
                for idx, roi_data in enumerate(self.canvas.final_rois):
                    poly_points = roi_data['points']
                    roi_name = roi_data.get('name', f"ROI {idx}")
                    if len(poly_points) < 3: 
                        continue
                    
                    color = ROI_COLORS[idx % len(ROI_COLORS)]
                    points_px = [(int(x*w), int(y*h)) for x, y in poly_points]
                    poly_array = np.array(points_px, dtype=np.int32)
                    cv2.polylines(frame, [poly_array], True, color, 3)
                
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                qimg = QImage(rgb.data, w, h, rgb.strides[0], QImage.Format.Format_RGB888).copy()
                self.canvas.update_frame(qimg)
                
                # Atualizar UI
                self.current_frame = current_pos
                self.slider.blockSignals(True)
                self.slider.setValue(self.current_frame)
                self.slider.blockSignals(False)
                
                current_time = self.current_frame / self.fps
                total_time = self.total_frames / self.fps
                self.lbl_time.setText(
                    f"{int(current_time//60):02d}:{int(current_time%60):02d} / "
                    f"{int(total_time//60):02d}:{int(total_time%60):02d}"
                )
                
                return  # ✅ SAIR SEM PROCESSAMENTO IA
        
        # ============================================
        # PASSO 3: PROCESSAMENTO NORMAL COM IA
        # ============================================
        
        processed_frame, new_events = self.processor.process_frame(
            frame, 
            self.canvas.final_rois,
            self.canvas.grid_map,
            run_detection=run_detection
        )
        
        # ✅ CORREÇÃO: Adicionar eventos à tabela (funciona com cache)
        for event in new_events:
            if event['type'] in ['SAIDA', 'SAIDA_PERDA']:
                # Usar frame atual do processador
                event['frame_time'] = self.processor.current_frame
                self.add_event_to_table(event)
        
        # Exibir frame processado
        h, w = processed_frame.shape[:2]
        rgb = cv2.cvtColor(processed_frame, cv2.COLOR_BGR2RGB)
        qimg = QImage(rgb.data, w, h, rgb.strides[0], QImage.Format.Format_RGB888).copy()
        self.canvas.update_frame(qimg)
        
        # Atualizar controles
        if self.video_mode == 'file':
            self.current_frame = int(self.cap.get(cv2.CAP_PROP_POS_FRAMES))
            
            self.slider.blockSignals(True)
            self.slider.setValue(self.current_frame)
            self.slider.blockSignals(False)
            
            current_time = self.current_frame / self.fps
            total_time = self.total_frames / self.fps
            self.lbl_time.setText(
                f"{int(current_time//60):02d}:{int(current_time%60):02d} / "
                f"{int(total_time//60):02d}:{int(total_time%60):02d}"
            )
    
    # ========== GESTÃO DE ROIs ==========
    
    def enable_drawing(self):
        """Ativa desenho de ROI"""
        self.canvas.enable_drawing()
        self.update_roi_info()
        self.update_cycle_roi_combo()
        
    def save_rois(self):
        """Salva ROIs em arquivo"""
        self.canvas.save_rois()
        QMessageBox.information(self, "Sucesso", "✅ ROIs salvas em 'rois_config.json'")
        
    def load_rois(self):
        """Carrega ROIs de arquivo"""
        if self.canvas.load_rois():
            self.update_roi_info()
            self.update_cycle_roi_combo()
            QMessageBox.information(self, "Sucesso", "✅ ROIs carregadas!")
        else:
            QMessageBox.warning(self, "Aviso", "⚠️ Arquivo de ROIs não encontrado")
    
    def clear_rois(self):
        """Limpa todas as ROIs"""
        reply = QMessageBox.question(
            self, "Confirmar", 
            "🗑️ Tem certeza que deseja limpar todas as ROIs?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            self.canvas.clear_rois()
            self.update_roi_info()
            self.update_cycle_roi_combo()
    
    def update_roi_info(self):
        """Atualiza informação de ROIs"""
        count = len(self.canvas.final_rois)
        self.lbl_roi_info.setText(f"ROIs definidas: {count}")
    
    # ========== GESTÃO DE EVENTOS ==========
    
    def add_event_to_table(self, event):
        """Adiciona evento à tabela"""
        row = self.table.rowCount()
        self.table.insertRow(row)
        
        roi_display_name = event.get('roi_name', f"ROI {event['roi']}")
        self.table.setItem(row, 0, QTableWidgetItem(roi_display_name))
        
        # USAR FRAMES DIRETOS DO EVENTO
        start_frame = event.get('start_frame', event.get('entry_frame', 0))
        end_frame = event.get('end_frame', event.get('frame_time', 0))
        
        # Verificar consistência
        if start_frame > end_frame:
            # Se frame de início > frame de fim, ajustar
            if 'duration' in event and self.fps > 0:
                start_frame = max(0, end_frame - int(round(event['duration'] * self.fps)))
            else:
                start_frame = max(0, end_frame - 1)
        
        self.table.setItem(row, 1, QTableWidgetItem(str(start_frame)))
        self.table.setItem(row, 2, QTableWidgetItem(str(end_frame)))
        
        # Calcular duração baseada nos frames
        if end_frame > start_frame and self.fps > 0:
            duration = (end_frame - start_frame) / self.fps
        else:
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
            btn.setToolTip("Trabalho que agrega valor." if cat == 'TAV' else 
                        "Trabalho necessário, mas não agrega valor" if cat == 'NNVA' else 
                        "Não agrega valor / desperdício")
            
            cat_layout.addWidget(btn)

        self.table.setCellWidget(row, 4, cat_widget)
        
        # Mão (Esq/Dir)
        hand_text = "Esq" if event['hand'] == 'Left' else "Dir"
        self.table.setItem(row, 5, QTableWidgetItem(hand_text))
        
        # Recurso
        self.table.setItem(row, 6, QTableWidgetItem("Mão"))
        
        self.events.append({})
        self.update_event_data(row)
              
    def add_manual_event(self):
        """Adiciona evento manual"""
        event = {
            'roi': 0,
            'hand': 'Left',
            'duration': 0,
            'frame_time': self.current_frame
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
            self.processor.reset_tracking()
    
    def on_category_click(self, row, category):
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
                    # Volta ao estilo padrão original (só font-size)
                    btn.setStyleSheet("font-size: 9px;")
            else:
                # Desmarca os outros botões
                btn.setChecked(False)
                btn.setStyleSheet("font-size: 9px;")
        
        self.update_event_data(row)
    
    def on_table_changed(self, row, col):
        """Atualiza dados quando célula muda"""
        if col in [1, 2]:  # Frames mudaram
            try:
                start = int(self.table.item(row, 1).text())
                end = int(self.table.item(row, 2).text())
                dur = (end - start) / self.fps if self.fps > 0 else 0
                self.table.item(row, 3).setText(f"{dur:.2f}")
            except:
                pass
        
        self.update_event_data(row)
    
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
                'roi_name': self.table.item(row, 0).text(),
                'start_frame': int(self.table.item(row, 1).text()),
                'end_frame': int(self.table.item(row, 2).text()),
                'duration': float(self.table.item(row, 3).text()),
                'category': category,
                'hand': self.table.item(row, 5).text(),
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
        
        self.dashboard.load_data(self.events, self.spin_takt.value())
        QMessageBox.information(self, "Sucesso", "✅ Dashboard atualizado!")
        
    def analyze_cycles(self):
        """Analisa os ciclos baseados na ROI de início selecionada"""
        cycle_roi_name = self.combo_cycle_roi.currentText()
        
        if cycle_roi_name == "(Nenhuma)":
            QMessageBox.warning(self, "Aviso", "⚠️ Selecione uma ROI de início de ciclo primeiro!")
            return
        
        if not self.events:
            QMessageBox.warning(self, "Aviso", "⚠️ Não há eventos para analisar!")
            return
        
        # Filtrar eventos da ROI de ciclo (apenas eventos com end_frame)
        cycle_events = [e for e in self.events 
                    if e.get('roi_name') == cycle_roi_name and e.get('end_frame', 0) > 0]
        
        if len(cycle_events) < 2:
            QMessageBox.warning(self, "Aviso", 
                f"⚠️ Poucos eventos na ROI '{cycle_roi_name}'.\nSão necessários pelo menos 2 eventos para calcular ciclos.")
            return
        
        # Ordenar por frame de fim
        cycle_events.sort(key=lambda e: e.get('end_frame', 0))
        
        # Calcular tempos entre ciclos E validar sequência
        takt_time = self.spin_takt.value()
        cycles = []
        
        for i in range(1, len(cycle_events)):
            prev_event = cycle_events[i-1]
            curr_event = cycle_events[i]
            
            prev_frame = prev_event.get('end_frame', 0)
            curr_frame = curr_event.get('end_frame', 0)
            
            cycle_time = (curr_frame - prev_frame) / self.fps if self.fps > 0 else 0
            deviation = cycle_time - takt_time
            deviation_pct = (deviation / takt_time * 100) if takt_time > 0 else 0
            
            # Validar sequência de operações (se configurada)
            sequence_status = "N/A"
            sequence_details = ""
            operations_in_cycle = []
            
            if self.operation_sequence:
                # Pegar todos os eventos entre prev_frame e curr_frame
                events_in_cycle = [e for e in self.events 
                                if prev_frame <= e.get('end_frame', 0) < curr_frame]
                events_in_cycle.sort(key=lambda e: e.get('end_frame', 0))
                
                # Extrair sequência real executada
                operations_in_cycle = [e.get('roi_name', '') for e in events_in_cycle]
                
                # Comparar com sequência esperada (incluindo ROI inicial no começo)
                expected_sequence = [cycle_roi_name] + self.operation_sequence
                
                # Verificar se a sequência está correta
                if operations_in_cycle == expected_sequence:
                    sequence_status = "✅ CORRETO"
                else:
                    sequence_status = "❌ INCORRETO"
                    sequence_details = f"Esperado: {' → '.join(expected_sequence)}<br>Real: {' → '.join(operations_in_cycle)}"
            
            cycles.append({
                'cycle_num': i,
                'start_frame': prev_frame,
                'end_frame': curr_frame,
                'cycle_time': cycle_time,
                'takt_time': takt_time,
                'deviation': deviation,
                'deviation_pct': deviation_pct,
                'status': '✅ OK' if abs(deviation_pct) <= 2 else '⚠️ FORA',
                'sequence_status': sequence_status,
                'sequence_details': sequence_details,
                'operations': operations_in_cycle
            })
        
        # Mostrar relatório
        self.show_cycle_report(cycles, cycle_roi_name)
        
    def show_cycle_report(self, cycles, roi_name):
        """Exibe relatório de análise de ciclos com validação de sequência"""
        if not cycles:
            return
        
        # Estatísticas
        cycle_times = [c['cycle_time'] for c in cycles]
        avg_cycle = np.mean(cycle_times)
        std_cycle = np.std(cycle_times)
        min_cycle = min(cycle_times)
        max_cycle = max(cycle_times)
        
        takt = cycles[0]['takt_time']
        cycles_ok = sum(1 for c in cycles if c['status'] == '✅ OK')
        cycles_nok = len(cycles) - cycles_ok
        
        # Estatísticas de sequência
        has_sequence = self.operation_sequence and len(self.operation_sequence) > 0
        if has_sequence:
            seq_correct = sum(1 for c in cycles if c['sequence_status'] == '✅ CORRETO')
            seq_incorrect = sum(1 for c in cycles if c['sequence_status'] == '❌ INCORRETO')
        
        # Criar DataFrame para gráfico
        df_cycles = pd.DataFrame(cycles)
        
        # Gráfico de linha com Takt Time
        fig = go.Figure()
        
        # Linha de ciclos reais
        fig.add_trace(go.Scatter(
            x=df_cycles['cycle_num'],
            y=df_cycles['cycle_time'],
            mode='lines+markers',
            name='Tempo de Ciclo Real',
            line=dict(color='#3498db', width=3),
            marker=dict(size=8)
        ))
        
        # Linha do Takt Time
        fig.add_trace(go.Scatter(
            x=df_cycles['cycle_num'],
            y=[takt] * len(df_cycles),
            mode='lines',
            name=f'Takt Time ({takt}s)',
            line=dict(color='#e74c3c', width=2, dash='dash')
        ))
        
        # Zona de tolerância (±10%)
        fig.add_trace(go.Scatter(
            x=df_cycles['cycle_num'],
            y=[takt * 1.02] * len(df_cycles),
            mode='lines',
            name='Limite Superior (+2%)',
            line=dict(color='#f39c12', width=1, dash='dot'),
            showlegend=False
        ))
        
        fig.add_trace(go.Scatter(
            x=df_cycles['cycle_num'],
            y=[takt * 0.98] * len(df_cycles),
            mode='lines',
            name='Limite Inferior (-2%)',
            line=dict(color='#f39c12', width=1, dash='dot'),
            fill='tonexty',
            fillcolor='rgba(243, 156, 18, 0.1)',
            showlegend=False
        ))
        
        fig.update_layout(
            title=f"📊 Análise de Ciclos - ROI: {roi_name}",
            xaxis_title="Número do Ciclo",
            yaxis_title="Tempo (segundos)",
            hovermode='x unified',
            template='plotly_white',
            height=500
        )
        
        # KPIs de Sequência (se configurada)
        sequence_kpis = ""
        if has_sequence:
            sequence_kpis = f"""
            <div class="kpi">
                <h2 style="color: #27ae60;">{seq_correct}</h2>
                <p>Seq. Corretas</p>
            </div>
            <div class="kpi">
                <h2 style="color: #e74c3c;">{seq_incorrect}</h2>
                <p>Seq. Incorretas</p>
            </div>
            """
        
        # Informação da sequência esperada
        sequence_info = ""
        if has_sequence:
            expected_full = [roi_name] + self.operation_sequence + [roi_name]
            sequence_info = f"""
            <div style="background: #fff3cd; padding: 15px; border-radius: 8px; margin: 20px 0; border-left: 4px solid #ffc107;">
                <h3 style="margin: 0 0 10px 0; color: #856404;">📋 Sequência Esperada:</h3>
                <p style="font-size: 18px; font-weight: bold; color: #333; margin: 0;">
                    {' → '.join(expected_full)}
                </p>
            </div>
            """
        
        # HTML do relatório
        html_report = f"""
        <html>
        <head>
            <meta charset="utf-8">
            <style>
                body {{ font-family: Arial, sans-serif; padding: 20px; background: #f5f5f5; }}
                .header {{ background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); 
                        color: white; padding: 20px; border-radius: 10px; margin-bottom: 20px; }}
                .kpi-container {{ display: flex; justify-content: space-around; margin: 20px 0; flex-wrap: wrap; }}
                .kpi {{ text-align: center; padding: 15px; background: white; border-radius: 8px; 
                        box-shadow: 0 2px 4px rgba(0,0,0,0.1); min-width: 120px; margin: 5px; }}
                .kpi h2 {{ margin: 0; font-size: 32px; color: #2c3e50; }}
                .kpi p {{ margin: 5px 0 0 0; color: #7f8c8d; font-size: 14px; }}
                table {{ width: 100%; border-collapse: collapse; background: white; 
                        border-radius: 8px; overflow: hidden; margin-top: 20px; }}
                th {{ background: #34495e; color: white; padding: 12px; text-align: left; }}
                td {{ padding: 10px; border-bottom: 1px solid #ecf0f1; }}
                tr:hover {{ background: #f8f9fa; }}
                .ok {{ color: #27ae60; font-weight: bold; }}
                .nok {{ color: #e74c3c; font-weight: bold; }}
                .seq-details {{ font-size: 11px; color: #666; margin-top: 5px; }}
            </style>
        </head>
        <body>
            <div class="header">
                <h1>📊 Relatório de Análise de Ciclos</h1>
                <p>ROI de Referência: <b>{roi_name}</b></p>
                <p>Takt Time Alvo: <b>{takt:.2f}s</b></p>
            </div>
            
            {sequence_info}
            
            <div class="kpi-container">
                <div class="kpi">
                    <h2>{len(cycles)}</h2>
                    <p>Total de Ciclos</p>
                </div>
                <div class="kpi">
                    <h2>{avg_cycle:.2f}s</h2>
                    <p>Tempo Médio</p>
                </div>
                <div class="kpi">
                    <h2>{std_cycle:.2f}s</h2>
                    <p>Desvio Padrão</p>
                </div>
                <div class="kpi">
                    <h2 class="ok">{cycles_ok}</h2>
                    <p>Ciclos OK</p>
                </div>
                <div class="kpi">
                    <h2 class="nok">{cycles_nok}</h2>
                    <p>Ciclos Fora</p>
                </div>
                {sequence_kpis}
            </div>
            
            {fig.to_html(full_html=False, include_plotlyjs='cdn')}
            
            <h2 style="margin-top: 30px;">📋 Detalhamento dos Ciclos</h2>
            <table>
                <thead>
                    <tr>
                        <th>Ciclo</th>
                        <th>Frame Início</th>
                        <th>Frame Fim</th>
                        <th>Tempo (s)</th>
                        <th>Desvio (%)</th>
                        <th>Status Tempo</th>
                        {'<th>Status Sequência</th>' if has_sequence else ''}
                    </tr>
                </thead>
                <tbody>
        """
        
        for c in cycles:
            status_class = 'ok' if c['status'] == '✅ OK' else 'nok'
            seq_class = 'ok' if c['sequence_status'] == '✅ CORRETO' else 'nok'
            
            seq_col = f"<td class='{seq_class}'>{c['sequence_status']}" if has_sequence else ""
            if has_sequence and c['sequence_details']:
                seq_col += f"<div class='seq-details'>{c['sequence_details']}</div>"
            if has_sequence:
                seq_col += "</td>"
            
            html_report += f"""
                    <tr>
                        <td><b>Ciclo {c['cycle_num']}</b></td>
                        <td>{c['start_frame']}</td>
                        <td>{c['end_frame']}</td>
                        <td>{c['cycle_time']:.2f}</td>
                        <td>{c['deviation_pct']:+.1f}%</td>
                        <td class="{status_class}">{c['status']}</td>
                        {seq_col}
                    </tr>
            """
        
        html_report += """
                </tbody>
            </table>
        </body>
        </html>
        """
        
        # Criar janela de visualização
        dialog = QDialog(self)
        dialog.setWindowTitle(f"Análise de Ciclos - {roi_name}")
        dialog.setGeometry(200, 100, 1400, 800)
        
        layout = QVBoxLayout(dialog)
        
        # Botão de exportar
        btn_export = QPushButton("💾 Exportar Relatório HTML")
        btn_export.clicked.connect(lambda: self.export_cycle_report(html_report, roi_name))
        layout.addWidget(btn_export)
        
        # Browser
        browser = QWebEngineView()
        browser.setHtml(html_report)
        layout.addWidget(browser)
        
        dialog.exec()
        
    def export_cycle_report(self, html_content, roi_name):
        """Exporta relatório de ciclos para arquivo HTML"""
        default_name = f"relatorio_ciclos_{roi_name.replace(' ', '_')}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
        path, _ = QFileDialog.getSaveFileName(self, "Salvar Relatório de Ciclos", 
                                            default_name, "HTML (*.html)")
        if path:
            with open(path, 'w', encoding='utf-8') as f:
                f.write(html_content)
            
            QMessageBox.information(self, "Sucesso", f"✅ Relatório exportado:\n{path}")
            
    def config_sequence(self):
        """Abre dialog para configurar sequência de operações"""
        if not self.canvas.final_rois:
            QMessageBox.warning(self, "Aviso", "⚠️ Defina as ROIs primeiro!")
            return
        
        roi_names = [roi['name'] for roi in self.canvas.final_rois]
        
        dialog = SequenceConfigDialog(self, roi_names)
        
        # Pré-carregar sequência existente
        for roi_name in self.operation_sequence:
            row = dialog.list_sequence.rowCount()
            dialog.list_sequence.insertRow(row)
            dialog.list_sequence.setItem(row, 0, QTableWidgetItem(str(row + 1)))
            dialog.list_sequence.setItem(row, 1, QTableWidgetItem(roi_name))
        
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.operation_sequence = dialog.get_sequence()
            
            if self.operation_sequence:
                QMessageBox.information(self, "Sucesso", 
                    f"✅ Sequência configurada com {len(self.operation_sequence)} operações:\n" +
                    " → ".join(self.operation_sequence))
            else:
                QMessageBox.warning(self, "Aviso", "⚠️ Nenhuma sequência foi definida!")


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
    
    window = TMAnalyzerApp()
    window.show()
    
    sys.exit(app.exec())
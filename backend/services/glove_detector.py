# -*- coding: utf-8 -*-
"""
glove_detector.py

Deteccao auxiliar por cor para mãos com luvas (ex.: luva verde), usada como
apoio ao MediaPipe Hands quando o detector de palma falha por causa da luva
cobrir a textura/tom de pele que o modelo espera.

Estrategia:
  1. Segmenta a(s) regiao(oes) da cor da luva via threshold em HSV.
  2. Encontra o(s) maior(es) blob(s) por contorno.
  3. Devolve uma bounding box "esticada" (com margem) em volta de cada blob.

Essa bounding box pode ser usada para:
  a) Recortar (crop) a regiao antes de passar pro MediaPipe -> a mao ocupa
     uma fracao maior do frame, o que aumenta MUITO a chance do detector de
     palma funcionar, mesmo com a luva.
  b) Servir de fallback (centroide) quando nem o crop resolve.

Calibracao:
  Ajuste GLOVE_HSV_RANGES para a cor exata da sua luva. Para calibrar
  rapidamente, use a funcao `sample_hsv_from_frame()` abaixo apontando pra
  um frame onde a luva aparece claramente.
"""

from __future__ import annotations

import cv2
import numpy as np
from dataclasses import dataclass


# ─────────────────────────────────────────────────────────────────────────
# Calibração de cor
# ─────────────────────────────────────────────────────────────────────────
# Faixas HSV (OpenCV: H 0-179, S 0-255, V 0-255).
# Verde "seguranca"/EPI tende a ser mais saturado que verde-folha natural,
# mas ajuste conforme a luva real. Pode ter mais de uma faixa (ex.: luva
# com reflexo que clareia o tom).
GLOVE_HSV_RANGES = [
    (np.array([82, 164, 27]), np.array([101, 255, 189])),
]

MIN_BLOB_AREA = 800          # pixels^2 — ignora ruido pequeno
CROP_MARGIN_RATIO = 0.6      # margem extra ao redor do blob (60% do tamanho do blob)
MORPH_KERNEL_SIZE = 5        # limpeza morfologica (fechar buracos, remover ruido)


@dataclass
class GloveBlob:
    x: int
    y: int
    w: int
    h: int
    area: float
    cx: float  # centroide x (pixels, frame original)
    cy: float  # centroide y (pixels, frame original)

    @property
    def bbox(self) -> tuple[int, int, int, int]:
        return (self.x, self.y, self.w, self.h)


def _build_mask(hsv_frame: np.ndarray) -> np.ndarray:
    mask = None
    for lo, hi in GLOVE_HSV_RANGES:
        m = cv2.inRange(hsv_frame, lo, hi)
        mask = m if mask is None else cv2.bitwise_or(mask, m)

    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (MORPH_KERNEL_SIZE, MORPH_KERNEL_SIZE))
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)   # remove ruido pequeno
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)  # fecha buracos internos
    return mask


def detect_glove_blobs(frame_bgr: np.ndarray, max_blobs: int = 2) -> list[GloveBlob]:
    """
    Detecta ate `max_blobs` regioes da cor da luva no frame (BGR, como o
    OpenCV le por padrao). Retorna as maiores por area, ja ordenadas
    (maior primeiro).
    """
    hsv = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2HSV)
    mask = _build_mask(hsv)

    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    blobs: list[GloveBlob] = []
    for c in contours:
        area = cv2.contourArea(c)
        if area < MIN_BLOB_AREA:
            continue
        x, y, w, h = cv2.boundingRect(c)
        M = cv2.moments(c)
        cx = M["m10"] / M["m00"] if M["m00"] != 0 else x + w / 2
        cy = M["m01"] / M["m00"] if M["m00"] != 0 else y + h / 2
        blobs.append(GloveBlob(x=x, y=y, w=w, h=h, area=area, cx=cx, cy=cy))

    blobs.sort(key=lambda b: b.area, reverse=True)
    return blobs[:max_blobs]


def crop_with_margin(
    frame_bgr: np.ndarray,
    blob: GloveBlob,
    margin_ratio: float = CROP_MARGIN_RATIO,
) -> tuple[np.ndarray, tuple[int, int]]:
    """
    Recorta o frame em volta do blob, com margem extra (a mao geralmente
    ultrapassa um pouco a area colorida detectada — punho, dedos na sombra).

    Retorna (crop, (offset_x, offset_y)) — o offset serve para converter
    coordenadas de landmarks detectados no crop de volta para o frame
    original: x_original = x_crop * crop_w + offset_x  (se x_crop for 0..1)
    """
    H, W = frame_bgr.shape[:2]
    mx = int(blob.w * margin_ratio)
    my = int(blob.h * margin_ratio)

    x0 = max(0, blob.x - mx)
    y0 = max(0, blob.y - my)
    x1 = min(W, blob.x + blob.w + mx)
    y1 = min(H, blob.y + blob.h + my)

    crop = frame_bgr[y0:y1, x0:x1]
    return crop, (x0, y0)


def remap_landmark_to_original(
    lm_x_norm: float,
    lm_y_norm: float,
    crop_shape: tuple[int, int],   # (crop_h, crop_w)
    offset: tuple[int, int],       # (offset_x, offset_y)
    original_shape: tuple[int, int],  # (H, W) do frame original
) -> tuple[float, float]:
    """
    Converte um landmark normalizado (0..1) detectado DENTRO do crop para
    coordenadas normalizadas (0..1) no frame ORIGINAL — assim o resto do
    seu pipeline (ROIs, eventos etc.) continua funcionando sem alteracao,
    pois ainda recebe coordenadas 0..1 relativas ao video inteiro.
    """
    crop_h, crop_w = crop_shape
    offset_x, offset_y = offset
    H, W = original_shape

    px = lm_x_norm * crop_w + offset_x
    py = lm_y_norm * crop_h + offset_y

    return px / W, py / H


def sample_hsv_from_frame(frame_bgr: np.ndarray, x: int, y: int, radius: int = 5) -> tuple[int, int, int]:
    """
    Util de calibracao: amostra a media HSV numa pequena regiao (x, y) do
    frame — aponte para um pixel bem no meio da luva num frame de teste
    para descobrir os valores certos para GLOVE_HSV_RANGES.
    """
    hsv = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2HSV)
    H, W = hsv.shape[:2]
    x0, x1 = max(0, x - radius), min(W, x + radius)
    y0, y1 = max(0, y - radius), min(H, y + radius)
    region = hsv[y0:y1, x0:x1].reshape(-1, 3)
    h, s, v = region.mean(axis=0)
    return int(h), int(s), int(v)

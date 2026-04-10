# -*- coding: utf-8 -*-
"""
process_video.py  --  processa video com MediaPipe e salva resultado

Uso:
    python process_video.py "entrada.mp4"
    python process_video.py "entrada.mp4" "saida.mp4"

Se o caminho de saida nao for informado, salva como "entrada_tracked.mp4"
na mesma pasta do arquivo de entrada.
"""

import sys
import cv2
import mediapipe as mp
from pathlib import Path

# ── Argumentos ───────────────────────────────────────────────────────────────
if len(sys.argv) < 2:
    print("Uso: python process_video.py <entrada.mp4> [saida.mp4]")
    sys.exit(1)

input_path  = Path(sys.argv[1])
output_path = Path(sys.argv[2]) if len(sys.argv) > 2 else input_path.with_name(input_path.stem + "_tracked.mp4")

if not input_path.exists():
    print(f"ERRO: arquivo nao encontrado: {input_path}")
    sys.exit(1)

# ── Abrir video de entrada ────────────────────────────────────────────────────
cap = cv2.VideoCapture(str(input_path))
if not cap.isOpened():
    print(f"ERRO: nao foi possivel abrir: {input_path}")
    sys.exit(1)

fps          = cap.get(cv2.CAP_PROP_FPS) or 30
width        = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
height       = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

print(f"Entrada : {input_path}")
print(f"Saida   : {output_path}")
print(f"FPS     : {fps:.2f}")
print(f"Resolucao: {width}x{height}")
print(f"Frames  : {total_frames}")

# ── Criar video de saida ──────────────────────────────────────────────────────
fourcc = cv2.VideoWriter_fourcc(*"mp4v")
out    = cv2.VideoWriter(str(output_path), fourcc, fps, (width, height))

# ── Inicializar MediaPipe ─────────────────────────────────────────────────────
mp_hands = mp.solutions.hands
mp_draw  = mp.solutions.drawing_utils

hands = mp_hands.Hands(
    static_image_mode        = False,
    max_num_hands            = 2,
    min_detection_confidence = 0.5,
    min_tracking_confidence  = 0.5,
)

# ── Processar frames ──────────────────────────────────────────────────────────
frame_number = 0

while True:
    ret, frame = cap.read()
    if not ret:
        break

    frame_number += 1

    # Detectar maos
    rgb    = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    result = hands.process(rgb)

    # Desenhar esqueleto
    if result.multi_hand_landmarks:
        for i, hand_landmarks in enumerate(result.multi_hand_landmarks):
            label     = result.multi_handedness[i].classification[0].label
            real_side = "Direita" if label == "Left" else "Esquerda"
            color     = (0, 255, 0) if label == "Left" else (255, 100, 100)

            mp_draw.draw_landmarks(
                frame,
                hand_landmarks,
                mp_hands.HAND_CONNECTIONS,
                mp_draw.DrawingSpec(color=color,            thickness=2, circle_radius=3),
                mp_draw.DrawingSpec(color=(255, 255, 255),  thickness=2),
            )

            tip   = hand_landmarks.landmark[mp_hands.HandLandmark.INDEX_FINGER_TIP]
            tip_x = int(tip.x * width)
            tip_y = int(tip.y * height)
            cv2.putText(frame, real_side, (tip_x + 12, tip_y),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, color, 2)

    # HUD com progresso
    n_hands = len(result.multi_hand_landmarks) if result.multi_hand_landmarks else 0
    pct     = frame_number / total_frames * 100 if total_frames > 0 else 0
    hud     = f"frame {frame_number}/{total_frames} ({pct:.1f}%)  |  {n_hands} mao(s)"
    cv2.putText(frame, hud, (10, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (200, 200, 0), 2)

    out.write(frame)

    # Progresso no terminal a cada 30 frames
    if frame_number % 30 == 0 or frame_number == total_frames:
        print(f"  {pct:5.1f}%  frame {frame_number}/{total_frames}", end="\r")

# ── Limpeza ───────────────────────────────────────────────────────────────────
cap.release()
out.release()
hands.close()

print(f"\nConcluido! Video salvo em: {output_path}")

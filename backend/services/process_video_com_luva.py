# -*- coding: utf-8 -*-
"""
process_video_com_luva.py

Mesma logica do process_video.py original, mas com fallback por cor
(glove_detector.py) para maos com luva: quando o MediaPipe nao encontra
nada no frame inteiro, usa o centroide do blob de cor da luva como
posicao da mao (mesma estrategia usada em _preprocess_worker.py).

Uso:
    python process_video_com_luva.py "entrada.mp4"
"""

import sys
import cv2
import mediapipe as mp
from pathlib import Path

from glove_detector import detect_glove_blobs

if len(sys.argv) < 2:
    print("Uso: python process_video_com_luva.py <entrada.mp4> [saida.mp4]")
    sys.exit(1)

input_path  = Path(sys.argv[1])
output_path = Path(sys.argv[2]) if len(sys.argv) > 2 else input_path.with_name(input_path.stem + "_tracked_luva.mp4")

cap = cv2.VideoCapture(str(input_path))
if not cap.isOpened():
    print(f"ERRO: nao foi possivel abrir: {input_path}")
    sys.exit(1)

fps          = cap.get(cv2.CAP_PROP_FPS) or 30
width        = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
height       = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

fourcc = cv2.VideoWriter_fourcc(*"mp4v")
out    = cv2.VideoWriter(str(output_path), fourcc, fps, (width, height))

mp_hands = mp.solutions.hands
mp_draw  = mp.solutions.drawing_utils

hands = mp_hands.Hands(
    static_image_mode=False,
    max_num_hands=2,
    min_detection_confidence=0.5,
    min_tracking_confidence=0.5,
)

frame_number  = 0
n_direct      = 0
n_fallback    = 0
n_missed      = 0

while True:
    ret, frame = cap.read()
    if not ret:
        break
    frame_number += 1

    rgb    = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    result = hands.process(rgb)

    if result.multi_hand_landmarks:
        n_direct += 1
        for i, hand_landmarks in enumerate(result.multi_hand_landmarks):
            label = result.multi_handedness[i].classification[0].label
            color = (0, 255, 0) if label == "Left" else (255, 100, 100)
            mp_draw.draw_landmarks(
                frame, hand_landmarks, mp_hands.HAND_CONNECTIONS,
                mp_draw.DrawingSpec(color=color, thickness=2, circle_radius=3),
                mp_draw.DrawingSpec(color=(255, 255, 255), thickness=2),
            )
    else:
        # Fallback: blob(s) de cor de luva -> centroide como posicao da mao
        blobs = detect_glove_blobs(frame, max_blobs=2)
        if blobs:
            n_fallback += 1
            for blob in blobs:
                cx, cy = int(blob.cx), int(blob.cy)
                # Marcador visual do "pseudo-landmark": circulo cheio no
                # centroide + caixa do blob detectado, em ciano para
                # distinguir visualmente de uma deteccao direta do MediaPipe.
                cv2.circle(frame, (cx, cy), 10, (0, 255, 255), -1)
                cv2.rectangle(
                    frame,
                    (blob.x, blob.y),
                    (blob.x + blob.w, blob.y + blob.h),
                    (0, 255, 255), 2,
                )
                cv2.putText(
                    frame, "luva (fallback: centroide)",
                    (blob.x, blob.y - 8),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 255, 255), 2,
                )
        else:
            n_missed += 1

    pct = frame_number / total_frames * 100 if total_frames > 0 else 0
    hud = f"frame {frame_number}/{total_frames} ({pct:.1f}%)"
    cv2.putText(frame, hud, (10, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (200, 200, 0), 2)

    out.write(frame)
    if frame_number % 30 == 0 or frame_number == total_frames:
        print(f"  {pct:5.1f}%  frame {frame_number}/{total_frames}", end="\r")

cap.release()
out.release()
hands.close()

print(f"\nConcluido! Video salvo em: {output_path}")
print(f"Frames com deteccao direta   : {n_direct}")
print(f"Frames resolvidos via blob   : {n_fallback}")
print(f"Frames sem nenhuma deteccao  : {n_missed}")
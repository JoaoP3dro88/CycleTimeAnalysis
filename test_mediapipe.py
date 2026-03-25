# -*- coding: utf-8 -*-
"""
test_mediapipe.py  —  testa mp.solutions.hands (mesma API do legado)

Uso:
    python test_mediapipe.py                          # webcam
    python test_mediapipe.py "caminho/do/video.mp4"   # arquivo de video

Controles:
    ESPACO  — pausar / retomar
    Q       — sair
"""

import sys
import cv2
import mediapipe as mp

# Inicializar MediaPipe (igual ao legado ProcessTracer_Hands.py)
mp_hands = mp.solutions.hands
mp_draw  = mp.solutions.drawing_utils

hands = mp_hands.Hands(
    static_image_mode        = False,
    max_num_hands            = 2,
    min_detection_confidence = 0.5,
    min_tracking_confidence  = 0.5,
)

# Abrir fonte de video
source = sys.argv[1] if len(sys.argv) > 1 else 0
cap    = cv2.VideoCapture(source)

if not cap.isOpened():
    print(f"ERRO: Nao foi possivel abrir: {source}")
    sys.exit(1)

fps          = cap.get(cv2.CAP_PROP_FPS) or 30
total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
delay        = max(1, int(1000 / fps))

print(f"Fonte  : {source}")
print(f"FPS    : {fps:.2f}")
print(f"Frames : {total_frames if total_frames > 0 else 'desconhecido'}")
print("Controles: ESPACO = pausar/retomar  |  Q = sair")

paused       = False
frame_number = 0
frame        = None

while True:
    if not paused:
        ret, frame = cap.read()
        if not ret:
            print("Fim do video.")
            break
        frame_number += 1

    if frame is None:
        continue

    # Detectar maos
    rgb    = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    result = hands.process(rgb)

    # Desenhar esqueleto
    if result.multi_hand_landmarks:
        for i, hand_landmarks in enumerate(result.multi_hand_landmarks):
            # "Left" do MediaPipe = mao direita real (camera espelhada)
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

            # Label na ponta do indicador (landmark 8)
            tip   = hand_landmarks.landmark[mp_hands.HandLandmark.INDEX_FINGER_TIP]
            h, w  = frame.shape[:2]
            tip_x = int(tip.x * w)
            tip_y = int(tip.y * h)
            cv2.putText(frame, real_side, (tip_x + 12, tip_y),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, color, 2)

    # HUD
    n_hands = len(result.multi_hand_landmarks) if result.multi_hand_landmarks else 0
    status  = f"PAUSADO | frame {frame_number}" if paused else f"frame {frame_number} | {n_hands} mao(s)"
    cv2.putText(frame, status, (10, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (200, 200, 0), 2)

    cv2.imshow("MediaPipe Hands -- teste", frame)

    key = cv2.waitKey(1 if paused else delay) & 0xFF
    if key == ord("q"):
        break
    elif key == ord(" "):
        paused = not paused

# Limpeza
cap.release()
cv2.destroyAllWindows()
hands.close()
print("Encerrado.")

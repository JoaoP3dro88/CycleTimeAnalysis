# -*- coding: utf-8 -*-
"""
_preprocess_worker.py

Chamado pelo preprocess_service.py como subprocess usando o Python global
(que tem mediapipe 0.10.21 com mp.solutions.hands).

Recebe o caminho do vídeo como argv[1] e imprime o resultado JSON no stdout.
"""
import sys
import json
import cv2
import mediapipe as mp

def main():
    if len(sys.argv) < 2:
        print(json.dumps({"error": "Caminho do video nao informado"}))
        sys.exit(1)

    video_path = sys.argv[1]
    mp_hands   = mp.solutions.hands

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        print(json.dumps({"error": f"Nao foi possivel abrir: {video_path}"}))
        sys.exit(1)

    fps          = cap.get(cv2.CAP_PROP_FPS) or 30.0
    frames       = {}
    frame_index  = 0

    with mp_hands.Hands(
        static_image_mode        = False,
        max_num_hands            = 2,
        min_detection_confidence = 0.5,
        min_tracking_confidence  = 0.5,
    ) as hands:
        while True:
            ret, frame = cap.read()
            if not ret:
                break

            rgb    = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            result = hands.process(rgb)

            if result.multi_hand_landmarks:
                landmarks_out  = []
                handedness_out = []
                for i, hand_lm in enumerate(result.multi_hand_landmarks):
                    landmarks_out.append(
                        [[lm.x, lm.y, lm.z] for lm in hand_lm.landmark]
                    )
                    cls = result.multi_handedness[i].classification[0]
                    handedness_out.append([cls.label, round(cls.score, 4)])

                frames[str(frame_index)] = {
                    "landmarks":  landmarks_out,
                    "handedness": handedness_out,
                }
            else:
                frames[str(frame_index)] = None

            frame_index += 1

    cap.release()

    output = {
        "fps":          fps,
        "total_frames": frame_index,
        "frames":       frames,
    }

    # Gravar em arquivo temporário (evita o limite de buffer do pipe no subprocess)
    # O caminho do arquivo de saída é passado como argv[2]
    out_path = sys.argv[2] if len(sys.argv) > 2 else None
    if out_path:
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(output, f, separators=(',', ':'))
        # Confirmar sucesso no stdout (pequeno, sem risco de buffer overflow)
        print("OK")
    else:
        # Fallback: imprimir no stdout (só funciona para vídeos pequenos)
        print(json.dumps(output, separators=(',', ':')))

if __name__ == '__main__':
    main()

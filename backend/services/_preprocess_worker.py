# -*- coding: utf-8 -*-
"""
_preprocess_worker.py

Pode ser usado de duas formas:
  1. Como subprocess (modo dev): python _preprocess_worker.py video.mp4 out.json
  2. Como módulo importado (modo frozen/PyInstaller): run_worker(video_path, out_path)

Nota: no modo frozen, o runtime hook pyi_hooks/rthook_mediapipe.py já adiciona
os diretórios de DLL ao search path antes de qualquer import acontecer.
"""
import sys
import json


def run_worker(video_path: str, out_path: str) -> None:
    """Processa o vídeo e grava o resultado em out_path (JSON)."""
    import cv2
    import mediapipe as mp

    mp_hands = mp.solutions.hands

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise RuntimeError(f"Nao foi possivel abrir: {video_path}")

    fps         = cap.get(cv2.CAP_PROP_FPS) or 30.0
    frames      = {}
    frame_index = 0

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

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(output, f, separators=(',', ':'))


def main():
    if len(sys.argv) < 3:
        print(json.dumps({"error": "Uso: worker.py <video> <out.json>"}))
        sys.exit(1)
    try:
        run_worker(sys.argv[1], sys.argv[2])
        print("OK")
    except Exception as e:
        print(json.dumps({"error": str(e)}))
        sys.exit(1)


if __name__ == '__main__':
    main()

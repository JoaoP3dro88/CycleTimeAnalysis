"""
visualize_pose.py
------------------
Abre uma janela para selecionar um vídeo e roda o modelo YOLOv8-pose ONNX
frame a frame, mostrando os keypoints do braço robótico em tempo real.

Uso:
    python tools/visualize_pose.py

Dependências:
    pip install opencv-python numpy onnxruntime
"""

import argparse
import cv2
import numpy as np
import onnxruntime as ort
from pathlib import Path

# ── Configurações ────────────────────────────────────────────────────────────

MODEL_PATH = "tools/model/robot_arm_pose.onnx"
CONF_THR   = 0.35
IOU_THR    = 0.45
IMGSZ      = 640

KPT_COLORS = [
    (0,   255,   0),   # base     → verde
    (0,   200, 255),   # eixo1    → amarelo
    (0,   140, 255),   # eixo2    → laranja
    (0,    80, 255),   # eixo3    → vermelho-laranja
    (0,     0, 255),   # ponta    → vermelho
]
KPT_NAMES  = ["base", "eixo1", "eixo2", "eixo3", "ponta"]
SKELETON   = [(0, 1), (1, 2), (2, 3), (3, 4)]

# ── Pré/Pós-processamento (igual ao validate_onnx.py) ───────────────────────

def letterbox(img, new_shape=640):
    h, w = img.shape[:2]
    r = new_shape / max(h, w)
    new_w, new_h = int(round(w * r)), int(round(h * r))
    img = cv2.resize(img, (new_w, new_h), interpolation=cv2.INTER_LINEAR)
    pad_h = new_shape - new_h
    pad_w = new_shape - new_w
    top, bottom = pad_h // 2, pad_h - pad_h // 2
    left, right = pad_w // 2, pad_w - pad_w // 2
    img = cv2.copyMakeBorder(img, top, bottom, left, right,
                             cv2.BORDER_CONSTANT, value=(114, 114, 114))
    return img, r, (left, top)


def preprocess(img_bgr):
    img, ratio, pad = letterbox(img_bgr, IMGSZ)
    blob = cv2.cvtColor(img, cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0
    blob = np.transpose(blob, (2, 0, 1))[np.newaxis]
    return blob, ratio, pad


def xywh2xyxy(x):
    y = x.copy()
    y[..., 0] = x[..., 0] - x[..., 2] / 2
    y[..., 1] = x[..., 1] - x[..., 3] / 2
    y[..., 2] = x[..., 0] + x[..., 2] / 2
    y[..., 3] = x[..., 1] + x[..., 3] / 2
    return y


def nms(boxes, scores, iou_thr):
    idxs = np.argsort(scores)[::-1]
    keep = []
    while len(idxs):
        i = idxs[0]
        keep.append(i)
        if len(idxs) == 1:
            break
        xx1 = np.maximum(boxes[i, 0], boxes[idxs[1:], 0])
        yy1 = np.maximum(boxes[i, 1], boxes[idxs[1:], 1])
        xx2 = np.minimum(boxes[i, 2], boxes[idxs[1:], 2])
        yy2 = np.minimum(boxes[i, 3], boxes[idxs[1:], 3])
        inter = np.maximum(0, xx2 - xx1) * np.maximum(0, yy2 - yy1)
        area_i = (boxes[i, 2] - boxes[i, 0]) * (boxes[i, 3] - boxes[i, 1])
        area_j = (boxes[idxs[1:], 2] - boxes[idxs[1:], 0]) * \
                 (boxes[idxs[1:], 3] - boxes[idxs[1:], 1])
        iou = inter / (area_i + area_j - inter + 1e-6)
        idxs = idxs[1:][iou < iou_thr]
    return keep


def postprocess(output, ratio, pad, orig_h, orig_w):
    pred = output[0].T                        # (anchors, channels)
    num_kpts = (pred.shape[1] - 5) // 3

    scores = pred[:, 4]
    mask   = scores > CONF_THR
    if not mask.any():
        return []

    pred   = pred[mask]
    scores = scores[mask]
    boxes  = xywh2xyxy(pred[:, :4])
    kpts   = pred[:, 5:]

    keep = nms(boxes, scores, IOU_THR)

    results = []
    for i in keep:
        x1, y1, x2, y2 = boxes[i]
        x1 = max(0, (x1 - pad[0]) / ratio)
        y1 = max(0, (y1 - pad[1]) / ratio)
        x2 = min(orig_w, (x2 - pad[0]) / ratio)
        y2 = min(orig_h, (y2 - pad[1]) / ratio)

        kpt_list = []
        for k in range(num_kpts):
            kx = (kpts[i, k * 3]     - pad[0]) / ratio
            ky = (kpts[i, k * 3 + 1] - pad[1]) / ratio
            kv =  kpts[i, k * 3 + 2]
            kpt_list.append((float(kx), float(ky), float(kv)))

        results.append({
            "box":   (int(x1), int(y1), int(x2), int(y2)),
            "score": float(scores[i]),
            "kpts":  kpt_list,
        })
    return results


def draw(img, detections):
    for det in detections:
        x1, y1, x2, y2 = det["box"]
        cv2.rectangle(img, (x1, y1), (x2, y2), (255, 255, 0), 2)
        cv2.putText(img, f"{det['score']:.2f}", (x1, y1 - 6),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 0), 2)

        kpts = det["kpts"]

        for a, b in SKELETON:
            if a < len(kpts) and b < len(kpts):
                ka, kb = kpts[a], kpts[b]
                if ka[2] > CONF_THR and kb[2] > CONF_THR:
                    cv2.line(img,
                             (int(ka[0]), int(ka[1])),
                             (int(kb[0]), int(kb[1])),
                             (200, 200, 200), 2)

        for k, (kx, ky, kv) in enumerate(kpts):
            if kv > CONF_THR:
                color = KPT_COLORS[k] if k < len(KPT_COLORS) else (255, 255, 255)
                name  = KPT_NAMES[k]  if k < len(KPT_NAMES)  else f"kpt{k}"
                cv2.circle(img, (int(kx), int(ky)), 7, color, -1)
                cv2.circle(img, (int(kx), int(ky)), 7, (0, 0, 0), 1)  # borda preta
                cv2.putText(img, name, (int(kx) + 10, int(ky) - 4),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)
    return img


# ── Seleciona arquivo via tkinter ────────────────────────────────────────────

def pick_file(path_arg=None):
    if path_arg:
        return path_arg
    # Tenta tkinter, com fallback para input manual
    try:
        import tkinter as tk
        from tkinter import filedialog
        root = tk.Tk()
        root.withdraw()
        root.wm_attributes("-topmost", 1)
        path = filedialog.askopenfilename(
            title="Seleciona o vídeo",
            filetypes=[("Vídeos", "*.mp4 *.avi *.mov *.mkv"), ("Todos", "*.*")]
        )
        root.destroy()
        return path
    except Exception:
        return input("Caminho do vídeo: ").strip().strip('"')


# ── Loop principal ───────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--video", default=None, help="Caminho direto para o vídeo (opcional)")
    parser.add_argument('--model', type=str, default='tools/model/robot_arm_pose.onnx')
    args = parser.parse_args()

    print(f"Carregando modelo: {args.model}")
    if not Path(args.model).exists():
        print(f"❌ Modelo não encontrado: {args.model}")
        return

    sess = ort.InferenceSession(args.model, providers=["CPUExecutionProvider"])
    input_name  = sess.get_inputs()[0].name
    output_name = sess.get_outputs()[0].name
    print(f"✅ Modelo carregado — output shape: {sess.get_outputs()[0].shape}")

    video_path = pick_file(args.video)
    if not video_path:
        print("Nenhum vídeo selecionado.")
        return

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        print(f"❌ Não conseguiu abrir o vídeo: {video_path}")
        return

    fps    = cap.get(cv2.CAP_PROP_FPS) or 30
    total  = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    w      = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h      = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    print(f"✅ Vídeo: {Path(video_path).name} | {w}x{h} | {fps:.1f} fps | {total} frames")
    print()
    print("Controles:")
    print("  ESPAÇO  → pausar / continuar")
    print("  ← →     → recuar / avançar 30 frames")
    print("  +  -    → aumentar / diminuir velocidade")
    print("  ESC     → sair")

    paused    = False
    speed     = 1.0        # multiplicador de velocidade
    frame_idx = 0

    cv2.namedWindow("YOLOv8-pose | Robot Arm", cv2.WINDOW_NORMAL)

    while True:
        if not paused:
            ret, frame = cap.read()
            if not ret:
                cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                frame_idx = 0
                continue
            frame_idx = int(cap.get(cv2.CAP_PROP_POS_FRAMES))

            blob, ratio, pad = preprocess(frame)
            raw  = sess.run([output_name], {input_name: blob})[0]
            fh, fw = frame.shape[:2]          # dimensões reais do frame
            dets = postprocess(raw, ratio, pad, fh, fw)
            vis  = draw(frame.copy(), dets)

            # HUD
            cv2.putText(vis, f"Frame {frame_idx}/{total}", (10, 28),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
            cv2.putText(vis, f"Dets: {len(dets)}  Speed: {speed:.1f}x", (10, 56),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
            cv2.putText(vis, "ESPACO=pause  ESC=sair  +/-=vel  <>=frames",
                        (10, h - 12),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (180, 180, 180), 1)

            cv2.imshow("YOLOv8-pose | Robot Arm", vis)

        wait_ms = max(1, int(1000 / fps / speed))
        key = cv2.waitKey(wait_ms) & 0xFF

        if key == 27:          # ESC → sair
            break
        elif key == 32:        # ESPAÇO → pausar
            paused = not paused
        elif key == 83 or key == ord('d'):   # → avançar 30 frames
            new_pos = min(total - 1, frame_idx + 30)
            cap.set(cv2.CAP_PROP_POS_FRAMES, new_pos)
        elif key == 81 or key == ord('a'):   # ← recuar 30 frames
            new_pos = max(0, frame_idx - 30)
            cap.set(cv2.CAP_PROP_POS_FRAMES, new_pos)
        elif key == ord('+') or key == ord('='):
            speed = min(8.0, speed + 0.5)
        elif key == ord('-'):
            speed = max(0.25, speed - 0.25)

    cap.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()

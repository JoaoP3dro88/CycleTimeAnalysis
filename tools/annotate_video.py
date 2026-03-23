"""
annotate_video.py
------------------
Roda o modelo YOLOv8-pose num vídeo e gera um novo vídeo anotado com
os keypoints do braço robótico desenhados.

Uso:
    python tools/annotate_video.py --video C:/caminho/video.mp4

Opções:
    --output   Caminho do vídeo de saída  (default: tools/results/video_annotated.mp4)
    --conf     Limiar de confiança        (default: 0.35)
    --skip     Processa 1 a cada N frames (default: 1 = todos)
    --max      Máximo de frames           (default: 0 = todos)

Dependências:
    pip install opencv-python numpy onnxruntime
"""

import argparse
import cv2
import numpy as np
import onnxruntime as ort
from pathlib import Path

MODEL_PATH = "tools/model/robot_arm_pose.onnx"
CONF_THR   = 0.35
IOU_THR    = 0.45
IMGSZ      = 640

KPT_COLORS = [
    (0,   255,   0),
    (0,   200, 255),
    (0,   140, 255),
    (0,    80, 255),
    (0,     0, 255),
]
KPT_NAMES = ["base", "eixo1", "eixo2", "eixo3", "ponta"]
SKELETON  = [(0, 1), (1, 2), (2, 3), (3, 4)]


# ── Pre/Post (idêntico ao validate_onnx.py que funciona) ────────────────────

def letterbox(img, new_shape=640):
    h, w = img.shape[:2]
    r = new_shape / max(h, w)
    new_w, new_h = int(round(w * r)), int(round(h * r))
    img = cv2.resize(img, (new_w, new_h), interpolation=cv2.INTER_LINEAR)
    pad_h = new_shape - new_h
    pad_w = new_shape - new_w
    top,  bottom = pad_h // 2, pad_h - pad_h // 2
    left, right  = pad_w // 2, pad_w - pad_w // 2
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
        area_i = (boxes[i,2]-boxes[i,0]) * (boxes[i,3]-boxes[i,1])
        area_j = (boxes[idxs[1:],2]-boxes[idxs[1:],0]) * (boxes[idxs[1:],3]-boxes[idxs[1:],1])
        iou = inter / (area_i + area_j - inter + 1e-6)
        idxs = idxs[1:][iou < iou_thr]
    return keep


def postprocess(output, ratio, pad, orig_h, orig_w):
    pred     = output[0].T
    num_kpts = (pred.shape[1] - 5) // 3
    scores   = pred[:, 4]
    mask     = scores > CONF_THR
    if not mask.any():
        return []
    pred   = pred[mask]
    scores = scores[mask]
    boxes  = xywh2xyxy(pred[:, :4])
    kpts   = pred[:, 5:]
    keep   = nms(boxes, scores, IOU_THR)

    results = []
    for i in keep:
        x1, y1, x2, y2 = boxes[i]
        x1 = float(max(0,      (x1 - pad[0]) / ratio))
        y1 = float(max(0,      (y1 - pad[1]) / ratio))
        x2 = float(min(orig_w, (x2 - pad[0]) / ratio))
        y2 = float(min(orig_h, (y2 - pad[1]) / ratio))

        kpt_list = []
        for k in range(num_kpts):
            kx = (kpts[i, k*3]     - pad[0]) / ratio
            ky = (kpts[i, k*3 + 1] - pad[1]) / ratio
            kv =  kpts[i, k*3 + 2]
            kpt_list.append((float(kx), float(ky), float(kv)))

        results.append({"box": (int(x1),int(y1),int(x2),int(y2)),
                        "score": float(scores[i]), "kpts": kpt_list})
    return results


def draw(img, detections):
    for det in detections:
        x1, y1, x2, y2 = det["box"]
        cv2.rectangle(img, (x1,y1), (x2,y2), (255,255,0), 2)
        cv2.putText(img, f"{det['score']:.2f}", (x1, y1-6),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255,255,0), 2)
        kpts = det["kpts"]
        for a, b in SKELETON:
            if a < len(kpts) and b < len(kpts):
                ka, kb = kpts[a], kpts[b]
                if ka[2] > CONF_THR and kb[2] > CONF_THR:
                    cv2.line(img, (int(ka[0]),int(ka[1])),
                             (int(kb[0]),int(kb[1])), (200,200,200), 2)
        for k, (kx, ky, kv) in enumerate(kpts):
            if kv > CONF_THR:
                color = KPT_COLORS[k] if k < len(KPT_COLORS) else (255,255,255)
                name  = KPT_NAMES[k]  if k < len(KPT_NAMES)  else f"kpt{k}"
                cv2.circle(img, (int(kx),int(ky)), 7, color, -1)
                cv2.circle(img, (int(kx),int(ky)), 7, (0,0,0), 1)
                cv2.putText(img, name, (int(kx)+10, int(ky)-4),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)
    return img


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--video",  required=True)
    ap.add_argument("--model",  default="tools/model/robot_arm_pose.onnx")
    ap.add_argument("--output", default="tools/results/video_annotated.mp4")
    ap.add_argument("--conf",   type=float, default=0.35)
    ap.add_argument("--skip",   type=int,   default=1)
    ap.add_argument("--max",    type=int,   default=0)
    args = ap.parse_args()

    global CONF_THR
    CONF_THR = args.conf

    sess = ort.InferenceSession(args.model, providers=["CPUExecutionProvider"])
    iname = sess.get_inputs()[0].name
    oname = sess.get_outputs()[0].name
    print(f"✅ Modelo carregado")

    # Abre com bytes para suportar caminhos com acentos/unicode
    video_bytes = Path(args.video).read_bytes()
    tmp = Path("tools/_tmp_input.mp4")
    tmp.write_bytes(video_bytes)

    cap = cv2.VideoCapture(str(tmp))
    if not cap.isOpened():
        print(f"❌ Não conseguiu abrir: {args.video}")
        return

    fps   = cap.get(cv2.CAP_PROP_FPS) or 30
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    w     = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h     = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    print(f"✅ Vídeo: {Path(args.video).name} | {w}x{h} | {fps:.0f}fps | {total} frames")

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(str(out_path), fourcc, fps, (w, h))

    frame_n   = 0
    processed = 0
    limit     = args.max if args.max > 0 else total

    print(f"Processando {min(limit, total)} frames (skip={args.skip})...")

    while True:
        ret, frame = cap.read()
        if not ret or processed >= limit:
            break

        frame_n += 1
        if frame_n % args.skip != 0:
            writer.write(frame)   # copia frame sem anotar
            continue

        blob, ratio, pad = preprocess(frame)
        raw  = sess.run([oname], {iname: blob})[0]
        fh, fw = frame.shape[:2]
        dets = postprocess(raw, ratio, pad, fh, fw)
        vis  = draw(frame.copy(), dets)

        # HUD
        cv2.putText(vis, f"Frame {frame_n}/{total} | Dets: {len(dets)}",
                    (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255,255,255), 2)

        writer.write(vis)
        processed += 1

        if processed % 50 == 0:
            print(f"  {processed}/{min(limit,total)} frames processados...")

    cap.release()
    writer.release()
    tmp.unlink(missing_ok=True)

    print(f"\n✅ Vídeo anotado salvo em: {out_path.resolve()}")
    print(f"   Frames processados: {processed}")


if __name__ == "__main__":
    main()

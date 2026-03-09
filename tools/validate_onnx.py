"""
validate_onnx.py
-----------------
Valida um modelo YOLOv8-pose exportado em ONNX rodando inferência local
sobre uma pasta de imagens. Desenha bounding boxes + keypoints e salva
os resultados em --output.

Uso:
    python tools/validate_onnx.py \
        --model  tools/model/robot_arm_pose.onnx \
        --source tools/frames \
        --output tools/results \
        --conf   0.35

Dependências:
    pip install opencv-python numpy onnxruntime
"""

import argparse
import os
from pathlib import Path

import cv2
import numpy as np

# Cores para cada keypoint (BGR) — base, eixo1, eixo2, eixo3, ponta
KPT_COLORS = [
    (0,   255, 0),    # base     → verde
    (0,   200, 255),  # eixo1    → amarelo
    (0,   140, 255),  # eixo2    → laranja
    (0,    80, 255),  # eixo3    → vermelho-laranja
    (0,    0,  255),  # ponta    → vermelho
]
KPT_NAMES = ["base", "eixo1", "eixo2", "eixo3", "ponta"]

# Skeleton: pares de keypoints a conectar
SKELETON = [(0, 1), (1, 2), (2, 3), (3, 4)]


def parse_args():
    p = argparse.ArgumentParser(description="Valida modelo YOLOv8-pose ONNX")
    p.add_argument("--model",  required=True, help="Caminho para o .onnx")
    p.add_argument("--source", required=True, help="Pasta com imagens de teste")
    p.add_argument("--output", default="tools/results", help="Pasta de saída")
    p.add_argument("--conf",   type=float, default=0.35, help="Limiar de confiança")
    p.add_argument("--iou",    type=float, default=0.45, help="Limiar de IoU para NMS")
    p.add_argument("--max",    type=int,   default=20,   help="Máx de imagens a processar")
    p.add_argument("--show",   action="store_true",      help="Mostra janela com resultado")
    return p.parse_args()


# ── pré-processamento ────────────────────────────────────────────────────────

def letterbox(img, new_shape=640):
    """Redimensiona mantendo aspect ratio com padding cinza."""
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


def preprocess(img_bgr, imgsz=640):
    img, ratio, pad = letterbox(img_bgr, imgsz)
    img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    blob = img_rgb.astype(np.float32) / 255.0
    blob = np.transpose(blob, (2, 0, 1))[np.newaxis]  # (1,3,H,W)
    return blob, ratio, pad


# ── pós-processamento ────────────────────────────────────────────────────────

def xywh2xyxy(x):
    y = x.copy()
    y[..., 0] = x[..., 0] - x[..., 2] / 2
    y[..., 1] = x[..., 1] - x[..., 3] / 2
    y[..., 2] = x[..., 0] + x[..., 2] / 2
    y[..., 3] = x[..., 1] + x[..., 3] / 2
    return y


def nms(boxes, scores, iou_thr):
    """NMS simples."""
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


def postprocess(output, conf_thr, iou_thr, ratio, pad, orig_h, orig_w):
    """
    output shape: (1, 4 + num_cls + num_kpts*3, anchors)
    Para YOLOv8-pose com 1 classe e 5 kpts: (1, 4+1+15, 8400) = (1,20,8400)
    """
    pred = output[0]          # (channels, anchors)
    pred = pred.T             # (anchors, channels)

    num_kpts = (pred.shape[1] - 5) // 3   # 5 = cx,cy,w,h,conf_cls

    boxes_xywh = pred[:, :4]
    scores     = pred[:, 4]               # objectness × class (1 classe)
    kpts_raw   = pred[:, 5:]              # (anchors, num_kpts*3)

    mask = scores > conf_thr
    if not mask.any():
        return []

    boxes_xywh = boxes_xywh[mask]
    scores     = scores[mask]
    kpts_raw   = kpts_raw[mask]

    boxes_xyxy = xywh2xyxy(boxes_xywh)
    keep = nms(boxes_xyxy, scores, iou_thr)

    results = []
    for i in keep:
        x1, y1, x2, y2 = boxes_xyxy[i]

        # Desfaz letterbox → coordenadas originais
        x1 = (x1 - pad[0]) / ratio
        y1 = (y1 - pad[1]) / ratio
        x2 = (x2 - pad[0]) / ratio
        y2 = (y2 - pad[1]) / ratio
        x1, y1 = max(0, x1), max(0, y1)
        x2, y2 = min(orig_w, x2), min(orig_h, y2)

        kpts = []
        for k in range(num_kpts):
            kx = (kpts_raw[i, k * 3]     - pad[0]) / ratio
            ky = (kpts_raw[i, k * 3 + 1] - pad[1]) / ratio
            kv =  kpts_raw[i, k * 3 + 2]           # visibility score
            kpts.append((float(kx), float(ky), float(kv)))

        results.append({
            "box":   (int(x1), int(y1), int(x2), int(y2)),
            "score": float(scores[i]),
            "kpts":  kpts,
        })
    return results


# ── desenho ──────────────────────────────────────────────────────────────────

def draw(img, detections, conf_thr=0.35):
    for det in detections:
        x1, y1, x2, y2 = det["box"]
        cv2.rectangle(img, (x1, y1), (x2, y2), (255, 255, 0), 2)
        cv2.putText(img, f"{det['score']:.2f}", (x1, y1 - 6),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 0), 1)

        kpts = det["kpts"]

        # Skeleton
        for a, b in SKELETON:
            if a < len(kpts) and b < len(kpts):
                ka, kb = kpts[a], kpts[b]
                if ka[2] > conf_thr and kb[2] > conf_thr:
                    cv2.line(img,
                             (int(ka[0]), int(ka[1])),
                             (int(kb[0]), int(kb[1])),
                             (180, 180, 180), 2)

        # Pontos
        for k, (kx, ky, kv) in enumerate(kpts):
            if kv > conf_thr:
                color = KPT_COLORS[k] if k < len(KPT_COLORS) else (255, 255, 255)
                name  = KPT_NAMES[k]  if k < len(KPT_NAMES)  else f"kpt{k}"
                cv2.circle(img, (int(kx), int(ky)), 6, color, -1)
                cv2.putText(img, name, (int(kx) + 8, int(ky) - 4),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.45, color, 1)
    return img


# ── main ─────────────────────────────────────────────────────────────────────

def main():
    args = parse_args()

    try:
        import onnxruntime as ort
    except ImportError:
        raise ImportError("Instala: pip install onnxruntime")

    model_path = Path(args.model)
    if not model_path.exists():
        raise FileNotFoundError(f"Modelo não encontrado: {model_path}")

    print(f"✅ Carregando modelo: {model_path}")
    sess = ort.InferenceSession(str(model_path),
                                providers=["CPUExecutionProvider"])
    input_name  = sess.get_inputs()[0].name
    output_name = sess.get_outputs()[0].name
    print(f"   Input : {input_name}  {sess.get_inputs()[0].shape}")
    print(f"   Output: {output_name} {sess.get_outputs()[0].shape}")

    source = Path(args.source)
    exts   = {".jpg", ".jpeg", ".png", ".bmp"}
    images = sorted([p for p in source.iterdir() if p.suffix.lower() in exts])
    images = images[:args.max]
    print(f"✅ {len(images)} imagens encontradas em {source}")

    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    total_dets = 0
    for img_path in images:
        img_bgr = cv2.imread(str(img_path))
        if img_bgr is None:
            continue
        orig_h, orig_w = img_bgr.shape[:2]

        blob, ratio, pad = preprocess(img_bgr)
        raw = sess.run([output_name], {input_name: blob})[0]

        detections = postprocess(raw, args.conf, args.iou,
                                 ratio, pad, orig_h, orig_w)
        total_dets += len(detections)

        vis = draw(img_bgr.copy(), detections, args.conf)

        out_path = output_dir / img_path.name
        cv2.imwrite(str(out_path), vis)

        if args.show:
            cv2.imshow("YOLOv8-pose", vis)
            key = cv2.waitKey(300)
            if key == 27:  # ESC
                break

        print(f"  {img_path.name}: {len(detections)} detecção(ões)")

    if args.show:
        cv2.destroyAllWindows()

    print(f"\n✅ Concluído — {total_dets} detecções em {len(images)} imagens")
    print(f"   Resultados salvos em: {output_dir.resolve()}")


if __name__ == "__main__":
    main()

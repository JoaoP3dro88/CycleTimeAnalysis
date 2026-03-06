"""
validate_onnx.py
────────────────
Valida o modelo YOLO exportado (.onnx) rodando inferência em frames
estáticos e desenhando as bounding boxes detectadas.

Uso:
    python tools/validate_onnx.py --model tools/model/robot_gripper.onnx --source tools/frames --conf 0.35

Argumentos:
    --model   Caminho para o arquivo .onnx exportado do Roboflow/YOLOv8
    --source  Pasta com imagens OU caminho de um único arquivo de imagem
    --conf    Threshold de confiança mínima (padrão: 0.35)
    --output  Pasta para salvar imagens com as detecções desenhadas (opcional)
    --show    Exibir janela com cada frame detectado (requer GUI)
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def load_onnx_session(model_path: Path):
    try:
        import onnxruntime as ort  # type: ignore
    except ImportError:
        print("[ERRO] onnxruntime não está instalado.")
        print("       Execute:  pip install onnxruntime")
        sys.exit(1)

    providers = ["CUDAExecutionProvider", "CPUExecutionProvider"]
    session = ort.InferenceSession(str(model_path), providers=providers)
    print(f"[ONNX] Modelo carregado: {model_path.name}")
    print(f"[ONNX] Provider ativo:   {session.get_providers()[0]}")

    inp = session.get_inputs()[0]
    print(f"[ONNX] Input  name={inp.name}  shape={inp.shape}  dtype={inp.type}")
    return session


def preprocess(frame, input_size: int = 640):
    import cv2
    import numpy as np

    h, w = frame.shape[:2]
    scale = input_size / max(h, w)
    new_w, new_h = int(w * scale), int(h * scale)
    resized = cv2.resize(frame, (new_w, new_h))

    # Pad to square
    padded = np.zeros((input_size, input_size, 3), dtype=np.uint8)
    padded[:new_h, :new_w] = resized

    # HWC → CHW, normalize 0–1, add batch dim
    tensor = padded.astype("float32") / 255.0
    tensor = tensor.transpose(2, 0, 1)[None]  # (1, 3, H, W)
    return tensor, scale, (new_w, new_h)


def postprocess(output, scale, padded_wh, orig_shape, conf_threshold: float, input_size: int = 640):
    """
    YOLOv8 ONNX output shape: (1, num_classes+4, num_anchors)
    Each column: [cx, cy, w, h, cls0_conf, cls1_conf, ...]
    """
    import numpy as np

    pred = output[0][0]  # (num_classes+4, num_anchors)
    pred = pred.T        # (num_anchors, num_classes+4)

    boxes_xywh = pred[:, :4]
    scores     = pred[:, 4:]
    class_ids  = scores.argmax(axis=1)
    confidences = scores.max(axis=1)

    mask = confidences >= conf_threshold
    boxes_xywh  = boxes_xywh[mask]
    confidences = confidences[mask]
    class_ids   = class_ids[mask]

    orig_h, orig_w = orig_shape[:2]
    pw, ph = padded_wh

    results = []
    for (cx, cy, bw, bh), conf, cls in zip(boxes_xywh, confidences, class_ids):
        # Coords are relative to the padded input_size square
        x1 = (cx - bw / 2) / input_size * (input_size / scale)
        y1 = (cy - bh / 2) / input_size * (input_size / scale)
        x2 = (cx + bw / 2) / input_size * (input_size / scale)
        y2 = (cy + bh / 2) / input_size * (input_size / scale)

        # Clamp to original image
        x1 = max(0, min(orig_w, int(x1)))
        y1 = max(0, min(orig_h, int(y1)))
        x2 = max(0, min(orig_w, int(x2)))
        y2 = max(0, min(orig_h, int(y2)))

        results.append({"bbox": (x1, y1, x2, y2), "conf": float(conf), "class_id": int(cls)})

    return results


def draw_detections(frame, detections, class_names: list[str]):
    import cv2

    colors = [
        (0, 255, 0), (255, 0, 255), (0, 255, 255),
        (255, 165, 0), (255, 0, 0), (0, 0, 255),
    ]

    for det in detections:
        x1, y1, x2, y2 = det["bbox"]
        cls  = det["class_id"]
        conf = det["conf"]
        name = class_names[cls] if cls < len(class_names) else f"cls{cls}"
        color = colors[cls % len(colors)]

        cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
        label = f"{name} {conf:.2f}"
        (lw, lh), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.55, 1)
        cv2.rectangle(frame, (x1, y1 - lh - 6), (x1 + lw + 4, y1), color, -1)
        cv2.putText(frame, label, (x1 + 2, y1 - 3),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 0, 0), 1, cv2.LINE_AA)

    return frame


def run(model_path: Path, source: Path, conf: float, output_dir: Path | None, show: bool) -> None:
    try:
        import cv2
    except ImportError:
        print("[ERRO] opencv-python não está instalado.  pip install opencv-python")
        sys.exit(1)

    session = load_onnx_session(model_path)
    inp_name = session.get_inputs()[0].name

    # Try to read class names from a classes.txt next to the model
    classes_file = model_path.parent / "classes.txt"
    if classes_file.exists():
        class_names = [l.strip() for l in classes_file.read_text().splitlines() if l.strip()]
        print(f"[INFO] Classes: {class_names}")
    else:
        class_names = [f"cls{i}" for i in range(100)]
        print("[WARN] classes.txt não encontrado — usando cls0, cls1, …")
        print(f"       Crie {classes_file} com uma classe por linha.")

    # Collect image paths
    img_exts = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
    if source.is_dir():
        paths = sorted(p for p in source.iterdir() if p.suffix.lower() in img_exts)
    else:
        paths = [source]

    print(f"[INFO] {len(paths)} imagem(ns) para processar\n")

    if output_dir:
        output_dir.mkdir(parents=True, exist_ok=True)

    total_detections = 0

    for i, img_path in enumerate(paths):
        frame = cv2.imread(str(img_path))
        if frame is None:
            print(f"  [SKIP] Não foi possível ler: {img_path.name}")
            continue

        tensor, scale, padded_wh = preprocess(frame)
        raw = session.run(None, {inp_name: tensor})
        dets = postprocess(raw, scale, padded_wh, frame.shape, conf)

        total_detections += len(dets)
        status = f"{len(dets)} det." if dets else "nenhuma detecção"
        print(f"  [{i+1:>4}/{len(paths)}] {img_path.name:<40} → {status}")

        annotated = draw_detections(frame.copy(), dets, class_names)

        if output_dir:
            cv2.imwrite(str(output_dir / img_path.name), annotated)

        if show:
            cv2.imshow("Validação ONNX — pressione qualquer tecla para avançar, ESC para sair", annotated)
            key = cv2.waitKey(0)
            if key == 27:  # ESC
                break

    if show:
        cv2.destroyAllWindows()

    print(f"\n✅ Concluído! Total de detecções: {total_detections} em {len(paths)} imagens")
    if output_dir:
        print(f"   Imagens anotadas salvas em: {output_dir.resolve()}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Valida modelo YOLO ONNX com bounding boxes")
    parser.add_argument("--model",  required=True,              help="Caminho para .onnx")
    parser.add_argument("--source", required=True,              help="Imagem ou pasta de imagens")
    parser.add_argument("--conf",   type=float, default=0.35,   help="Threshold de confiança (0–1)")
    parser.add_argument("--output", default=None,               help="Pasta para salvar resultados")
    parser.add_argument("--show",   action="store_true",        help="Exibir janela com detecções")
    args = parser.parse_args()

    run(
        model_path=Path(args.model),
        source=Path(args.source),
        conf=args.conf,
        output_dir=Path(args.output) if args.output else None,
        show=args.show,
    )


if __name__ == "__main__":
    main()

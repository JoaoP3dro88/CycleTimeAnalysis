"""
test_roboflow_models.py
───────────────────────
Testa modelos hospedados no Roboflow (hosted API) diretamente nos frames
extraídos, sem precisar exportar ONNX. Ideal para comparar rapidamente
3+ modelos antes de decidir qual treinar/exportar.

Uso:
    python tools/test_roboflow_models.py --help

Exemplo com 1 modelo:
    python tools/test_roboflow_models.py ^
        --api-key  SUA_API_KEY ^
        --models   "workspace1/projeto1/1" ^
        --source   tools/frames ^
        --conf     0.35 ^
        --output   tools/results

Exemplo comparando 3 modelos de uma vez:
    python tools/test_roboflow_models.py ^
        --api-key  SUA_API_KEY ^
        --models   "ws/model-a/1" "ws/model-b/2" "ws/model-c/1" ^
        --source   tools/frames ^
        --conf     0.35 ^
        --output   tools/results ^
        --max      20

Formato de --models:  "workspace/project/version"
  (encontrado na URL do Roboflow: roboflow.com/<workspace>/<project>/<version>)
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path


def install_check():
    missing = []
    try:
        import cv2  # noqa: F401
    except ImportError:
        missing.append("opencv-python")
    try:
        import requests  # noqa: F401
    except ImportError:
        missing.append("requests")
    if missing:
        print(f"[ERRO] Pacotes ausentes: {', '.join(missing)}")
        print(f"       Execute:  pip install {' '.join(missing)}")
        sys.exit(1)


def load_image_b64(path: Path) -> str:
    import base64
    return base64.b64encode(path.read_bytes()).decode("utf-8")


def predict_roboflow(api_key: str, workspace: str, project: str, version: str,
                     image_path: Path, conf: float) -> dict:
    """Chama a Roboflow Hosted Inference API e retorna o resultado bruto."""
    import requests

    url = f"https://detect.roboflow.com/{project}/{version}"
    params = {
        "api_key": api_key,
        "confidence": int(conf * 100),
        "overlap": 30,
        "format": "json",
    }

    with open(image_path, "rb") as f:
        response = requests.post(url, params=params, files={"file": f}, timeout=15)

    response.raise_for_status()
    return response.json()


def draw_predictions(frame, predictions: list[dict], model_label: str, color: tuple):
    import cv2

    for pred in predictions:
        cx = int(pred["x"])
        cy = int(pred["y"])
        w  = int(pred["width"])
        h  = int(pred["height"])
        x1, y1 = cx - w // 2, cy - h // 2
        x2, y2 = cx + w // 2, cy + h // 2

        cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)

        label = f"{pred.get('class','?')} {pred.get('confidence', 0):.2f}"
        (lw, lh), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
        cv2.rectangle(frame, (x1, y1 - lh - 6), (x1 + lw + 4, y1), color, -1)
        cv2.putText(frame, label, (x1 + 2, y1 - 3),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 1, cv2.LINE_AA)

    # Model name watermark
    cv2.putText(frame, model_label, (8, frame.shape[0] - 8),
                cv2.FONT_HERSHEY_SIMPLEX, 0.45, color, 1, cv2.LINE_AA)
    return frame


def compare_side_by_side(frames_preds: list[tuple], orig_frame, img_name: str):
    """Monta uma imagem com todos os modelos lado a lado para comparação visual."""
    import cv2
    import numpy as np

    n = len(frames_preds)
    h, w = orig_frame.shape[:2]
    target_w = min(w, 480)
    target_h = int(h * target_w / w)

    panels = []
    for annotated, _ in frames_preds:
        panel = cv2.resize(annotated, (target_w, target_h))
        panels.append(panel)

    combined = np.hstack(panels)

    # Header bar
    header = np.zeros((28, combined.shape[1], 3), dtype=np.uint8)
    cv2.putText(header, img_name, (6, 20),
                cv2.FONT_HERSHEY_SIMPLEX, 0.55, (200, 200, 200), 1, cv2.LINE_AA)

    return np.vstack([header, combined])


def run(api_key: str, models: list[str], source: Path, conf: float,
        output_dir: Path | None, max_images: int | None, delay: float) -> None:
    install_check()
    import cv2

    # Parse model strings "workspace/project/version"
    parsed_models = []
    for m in models:
        parts = m.strip("/").split("/")
        if len(parts) != 3:
            print(f"[ERRO] Formato inválido: '{m}'  →  use 'workspace/project/version'")
            sys.exit(1)
        parsed_models.append({"workspace": parts[0], "project": parts[1], "version": parts[2], "label": m})

    # Colors per model (BGR)
    palette = [(0, 255, 0), (255, 0, 255), (0, 200, 255), (255, 165, 0), (0, 0, 255)]
    for i, m in enumerate(parsed_models):
        m["color"] = palette[i % len(palette)]

    # Collect images
    img_exts = {".jpg", ".jpeg", ".png", ".bmp"}
    if source.is_dir():
        paths = sorted(p for p in source.iterdir() if p.suffix.lower() in img_exts)
    else:
        paths = [source]

    if max_images:
        paths = paths[:max_images]

    print(f"\n{'─'*60}")
    print(f"  Modelos  : {len(parsed_models)}")
    print(f"  Imagens  : {len(paths)}")
    print(f"  Conf min : {conf}")
    print(f"{'─'*60}\n")

    if output_dir:
        output_dir.mkdir(parents=True, exist_ok=True)
        # Subpasta por modelo
        for m in parsed_models:
            (output_dir / m["project"]).mkdir(exist_ok=True)
        compare_dir = output_dir / "_comparacao"
        compare_dir.mkdir(exist_ok=True)

    # Stats accumulator
    stats = {m["label"]: {"detections": 0, "images_with_det": 0, "errors": 0} for m in parsed_models}

    for img_idx, img_path in enumerate(paths):
        print(f"[{img_idx+1:>3}/{len(paths)}] {img_path.name}")
        frame = cv2.imread(str(img_path))
        if frame is None:
            print(f"         ⚠ Não foi possível ler, ignorando.")
            continue

        frames_preds = []

        for m in parsed_models:
            try:
                result = predict_roboflow(
                    api_key, m["workspace"], m["project"], m["version"],
                    img_path, conf
                )
                preds = result.get("predictions", [])
                n_det = len(preds)
                stats[m["label"]]["detections"] += n_det
                if n_det > 0:
                    stats[m["label"]]["images_with_det"] += 1

                annotated = draw_predictions(frame.copy(), preds, m["project"], m["color"])
                frames_preds.append((annotated, preds))

                det_str = f"{n_det} det." if n_det else "nenhuma"
                print(f"         {m['project']:<35} → {det_str}")

                if output_dir:
                    cv2.imwrite(str(output_dir / m["project"] / img_path.name), annotated)

                # Respeitar rate limit da API
                time.sleep(delay)

            except Exception as e:
                stats[m["label"]]["errors"] += 1
                print(f"         {m['project']:<35} → ERRO: {e}")
                frames_preds.append((frame.copy(), []))

        # Imagem de comparação lado a lado
        if output_dir and len(frames_preds) > 1:
            comparison = compare_side_by_side(frames_preds, frame, img_path.name)
            cv2.imwrite(str(compare_dir / img_path.name), comparison)

    # ── Resumo final ──────────────────────────────────────────────────────────
    print(f"\n{'═'*60}")
    print("  RESUMO DE DESEMPENHO")
    print(f"{'═'*60}")
    for m in parsed_models:
        s = stats[m["label"]]
        det_rate = s["images_with_det"] / len(paths) * 100 if paths else 0
        print(f"\n  📦 {m['label']}")
        print(f"     Total de detecções : {s['detections']}")
        print(f"     Imagens c/ detecção: {s['images_with_det']}/{len(paths)} ({det_rate:.0f}%)")
        if s["errors"]:
            print(f"     ⚠ Erros de API     : {s['errors']}")

    print(f"\n{'─'*60}")
    if output_dir:
        print(f"  Resultados salvos em : {output_dir.resolve()}")
        print(f"  Comparações (side-by-side): {compare_dir.resolve()}")

    # Salvar stats em JSON para análise posterior
    if output_dir:
        stats_path = output_dir / "stats.json"
        stats_path.write_text(json.dumps(stats, indent=2, ensure_ascii=False))
        print(f"  Stats JSON           : {stats_path}")

    print()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Compara modelos do Roboflow nos frames extraídos",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--api-key",  required=True,
                        help="API key do Roboflow (Settings → Roboflow API)")
    parser.add_argument("--models",   nargs="+", required=True,
                        help="Modelos no formato 'workspace/project/version'")
    parser.add_argument("--source",   required=True,
                        help="Pasta com imagens ou imagem única")
    parser.add_argument("--conf",     type=float, default=0.35,
                        help="Threshold de confiança mínima (padrão: 0.35)")
    parser.add_argument("--output",   default="tools/results",
                        help="Pasta de saída para imagens anotadas (padrão: tools/results)")
    parser.add_argument("--max",      type=int, default=None,
                        help="Testar apenas os primeiros N frames")
    parser.add_argument("--delay",    type=float, default=0.15,
                        help="Segundos entre chamadas de API (padrão: 0.15)")
    args = parser.parse_args()

    run(
        api_key=args.api_key,
        models=args.models,
        source=Path(args.source),
        conf=args.conf,
        output_dir=Path(args.output),
        max_images=args.max,
        delay=args.delay,
    )


if __name__ == "__main__":
    main()

"""
extract_frames.py
─────────────────
Extrai frames de um vídeo em intervalos regulares para compor
o dataset de treinamento do YOLOv8.

Uso:
    python tools/extract_frames.py --video data/videos/meu_video.mp4 --output tools/frames --interval 15

Argumentos:
    --video     Caminho para o vídeo fonte
    --output    Pasta de destino dos frames (criada automaticamente)
    --interval  Extrair 1 frame a cada N frames  (padrão: 15  ≈ 2 fps em 30fps)
    --max       Número máximo de frames a extrair (padrão: sem limite)
    --resize    Redimensionar para NxN pixels para upload mais rápido (padrão: 640)
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def extract(video_path: Path, output_dir: Path, interval: int, max_frames: int | None, resize: int) -> None:
    try:
        import cv2  # type: ignore
    except ImportError:
        print("[ERRO] opencv-python não está instalado.")
        print("       Execute:  pip install opencv-python")
        sys.exit(1)

    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        print(f"[ERRO] Não foi possível abrir: {video_path}")
        sys.exit(1)

    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    fps          = cap.get(cv2.CAP_PROP_FPS) or 30
    duration_s   = total_frames / fps

    print(f"Vídeo  : {video_path.name}")
    print(f"Frames : {total_frames}  |  FPS: {fps:.1f}  |  Duração: {duration_s:.1f}s")
    print(f"Intervalo de extração: 1 a cada {interval} frames")

    estimated = total_frames // interval
    if max_frames:
        estimated = min(estimated, max_frames)
    print(f"Frames a extrair (estimativa): {estimated}")

    output_dir.mkdir(parents=True, exist_ok=True)

    frame_idx   = 0
    saved_count = 0

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        if frame_idx % interval == 0:
            # Redimensionar mantendo aspect ratio
            h, w = frame.shape[:2]
            if max(h, w) > resize:
                scale = resize / max(h, w)
                frame = cv2.resize(frame, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)

            stem = video_path.stem
            out_path = output_dir / f"{stem}_f{frame_idx:06d}.jpg"
            cv2.imwrite(str(out_path), frame, [cv2.IMWRITE_JPEG_QUALITY, 92])
            saved_count += 1

            if saved_count % 20 == 0:
                pct = (frame_idx / total_frames) * 100
                print(f"  [{pct:5.1f}%] {saved_count} frames salvos…")

            if max_frames and saved_count >= max_frames:
                break

        frame_idx += 1

    cap.release()
    print(f"\n✅ Concluído! {saved_count} frames salvos em: {output_dir.resolve()}")
    print(f"   Próximo passo: faça upload desta pasta no Roboflow para anotar.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Extrai frames de vídeo para dataset YOLO")
    parser.add_argument("--video",    required=True,       help="Caminho para o vídeo")
    parser.add_argument("--output",   default="tools/frames", help="Pasta de saída")
    parser.add_argument("--interval", type=int, default=15,   help="1 frame a cada N frames")
    parser.add_argument("--max",      type=int, default=None,  help="Máximo de frames a extrair")
    parser.add_argument("--resize",   type=int, default=640,   help="Tamanho máximo do lado maior (px)")
    args = parser.parse_args()

    extract(
        video_path=Path(args.video),
        output_dir=Path(args.output),
        interval=args.interval,
        max_frames=args.max,
        resize=args.resize,
    )


if __name__ == "__main__":
    main()

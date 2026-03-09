"""
coco_keypoints_to_yolo_pose.py
-------------------------------
Converte um JSON COCO Keypoints (exportado pelo CVAT) para o formato
de labels YOLOv8-pose (.txt por imagem) e gera data.yaml + classes.txt.

Uso:
    python tools/coco_keypoints_to_yolo_pose.py \
        --coco   tools/annotations/person_keypoints_Train.json \
        --images tools/frames \
        --output tools/dataset_pose

Estrutura gerada:
    tools/dataset_pose/
        images/train/  images/val/  images/test/
        labels/train/  labels/val/  labels/test/
        data.yaml
        classes.txt
"""

import argparse
import json
import os
import random
import shutil
from pathlib import Path


def parse_args():
    p = argparse.ArgumentParser(description="COCO Keypoints → YOLOv8-pose")
    p.add_argument("--coco",   required=True,  help="Caminho para o JSON COCO Keypoints")
    p.add_argument("--images", required=True,  help="Pasta com as imagens originais")
    p.add_argument("--output", required=True,  help="Pasta de saída do dataset")
    p.add_argument("--train",  type=float, default=0.75, help="Fração treino (default 0.75)")
    p.add_argument("--val",    type=float, default=0.15, help="Fração validação (default 0.15)")
    p.add_argument("--seed",   type=int,   default=42,   help="Seed aleatória (default 42)")
    return p.parse_args()


def load_coco(coco_path: str) -> dict:
    with open(coco_path, "r", encoding="utf-8") as f:
        return json.load(f)


def build_image_map(coco: dict) -> dict:
    """image_id → {file_name, width, height}"""
    return {img["id"]: img for img in coco["images"]}


def build_category_map(coco: dict) -> dict:
    """category_id → {name, keypoints, skeleton}"""
    return {cat["id"]: cat for cat in coco.get("categories", [])}


def group_annotations_by_image(coco: dict) -> dict:
    """image_id → [annotation, ...]"""
    groups: dict = {}
    for ann in coco.get("annotations", []):
        groups.setdefault(ann["image_id"], []).append(ann)
    return groups


def bbox_to_yolo(bbox: list, img_w: int, img_h: int) -> tuple:
    """COCO bbox [x,y,w,h] → YOLO [cx,cy,w,h] normalizado."""
    x, y, w, h = bbox
    cx = (x + w / 2) / img_w
    cy = (y + h / 2) / img_h
    nw = w / img_w
    nh = h / img_h
    return cx, cy, nw, nh


def keypoints_to_yolo(keypoints: list, img_w: int, img_h: int) -> str:
    """
    COCO keypoints flat list [x, y, v, x, y, v, ...] →
    YOLOv8-pose string  "nx ny v  nx ny v ..."
    v: 0=não anotado, 1=ocluído, 2=visível
    """
    parts = []
    for i in range(0, len(keypoints), 3):
        x, y, v = keypoints[i], keypoints[i + 1], keypoints[i + 2]
        nx = x / img_w
        ny = y / img_h
        parts.append(f"{nx:.6f} {ny:.6f} {int(v)}")
    return " ".join(parts)


def convert(coco: dict, images_dir: Path, output_dir: Path,
            train_frac: float, val_frac: float, seed: int):

    image_map   = build_image_map(coco)
    cat_map     = build_category_map(coco)
    ann_by_img  = group_annotations_by_image(coco)

    # IDs de imagens que têm pelo menos uma anotação
    image_ids = [iid for iid in image_map if iid in ann_by_img]

    if not image_ids:
        print("⚠  Nenhuma anotação encontrada no JSON.")
        return

    # Detecta número de keypoints a partir da primeira anotação
    first_ann = next(iter(ann_by_img.values()))[0]
    num_kpts  = len(first_ann.get("keypoints", [])) // 3
    print(f"✅ {len(image_ids)} imagens com anotações | {num_kpts} keypoints por instância")

    # Split train / val / test
    random.seed(seed)
    random.shuffle(image_ids)
    n       = len(image_ids)
    n_train = int(n * train_frac)
    n_val   = int(n * val_frac)
    splits  = {
        "train": image_ids[:n_train],
        "val":   image_ids[n_train : n_train + n_val],
        "test":  image_ids[n_train + n_val :],
    }
    for split, ids in splits.items():
        print(f"   {split:5s}: {len(ids)} imagens")

    # Cria pastas de saída
    for split in splits:
        (output_dir / "images" / split).mkdir(parents=True, exist_ok=True)
        (output_dir / "labels" / split).mkdir(parents=True, exist_ok=True)

    # Mapeia category_id → índice de classe YOLO (0-based)
    cat_ids    = sorted(cat_map.keys())
    cat_to_idx = {cid: idx for idx, cid in enumerate(cat_ids)}
    class_names = [cat_map[cid]["name"] for cid in cat_ids]

    # Converte
    for split, ids in splits.items():
        for img_id in ids:
            img_info   = image_map[img_id]
            file_name  = img_info["file_name"]
            img_w      = img_info["width"]
            img_h      = img_info["height"]

            src_img = images_dir / file_name
            # Tenta encontrar só pelo basename se o caminho completo não existir
            if not src_img.exists():
                src_img = images_dir / Path(file_name).name

            dst_img = output_dir / "images" / split / Path(file_name).name
            dst_lbl = output_dir / "labels" / split / (Path(file_name).stem + ".txt")

            # Copia imagem
            if src_img.exists():
                shutil.copy2(src_img, dst_img)
            else:
                print(f"   ⚠  Imagem não encontrada: {src_img}")

            # Gera label
            lines = []
            for ann in ann_by_img[img_id]:
                cls_idx = cat_to_idx[ann["category_id"]]
                cx, cy, bw, bh = bbox_to_yolo(ann["bbox"], img_w, img_h)
                kpts_str = keypoints_to_yolo(ann.get("keypoints", []), img_w, img_h)
                lines.append(f"{cls_idx} {cx:.6f} {cy:.6f} {bw:.6f} {bh:.6f} {kpts_str}")

            dst_lbl.write_text("\n".join(lines), encoding="utf-8")

    # data.yaml
    yaml_path = output_dir / "data.yaml"
    yaml_lines = [
        f"path: {output_dir.resolve().as_posix()}",
        "train: images/train",
        "val:   images/val",
        "test:  images/test",
        "",
        f"nc: {len(class_names)}",
        f"names: {class_names}",
        "",
        f"kpt_shape: [{num_kpts}, 3]  # [num_keypoints, dim(x,y,visibility)]",
        f"# keypoints: " + ", ".join(f"{i}={name}" for i, name in enumerate(
            cat_map[cat_ids[0]].get("keypoints", [f"kpt{i}" for i in range(num_kpts)])
        )),
    ]
    yaml_path.write_text("\n".join(yaml_lines), encoding="utf-8")

    # classes.txt
    (output_dir / "classes.txt").write_text("\n".join(class_names), encoding="utf-8")

    print(f"\n✅ Dataset gerado em: {output_dir.resolve()}")
    print(f"   data.yaml  → {yaml_path}")
    print(f"   classes    → {class_names}")
    print(f"   kpt_shape  → [{num_kpts}, 3]")


def main():
    args = parse_args()
    coco      = load_coco(args.coco)
    images_dir = Path(args.images)
    output_dir = Path(args.output)

    if not images_dir.exists():
        raise FileNotFoundError(f"Pasta de imagens não encontrada: {images_dir}")

    convert(coco, images_dir, output_dir, args.train, args.val, args.seed)


if __name__ == "__main__":
    main()

# -*- coding: utf-8 -*-
"""
_preprocess_worker.py

Pode ser usado de duas formas:
  1. Como subprocess (modo dev): python _preprocess_worker.py video.mp4 out.json
  2. Como módulo importado (modo frozen/PyInstaller): run_worker(video_path, out_path)

Nota: no modo frozen, o runtime hook pyi_hooks/rthook_mediapipe.py já adiciona
os diretórios de DLL ao search path antes de qualquer import acontecer.

── Deteccao auxiliar de maos com luva (glove_detector) ──────────────────────
Quando o MediaPipe Hands nao encontra nenhuma mao no frame inteiro (comum
quando o operador usa luvas, pois o detector de palma foi treinado
majoritariamente em pele), usamos um fallback simples e confiavel:

  1. Procurar blob(s) da cor da luva (HSV threshold) no frame.
  2. Usar o CENTROIDE do blob como posicao da mao.
  3. Preencher os 21 "landmarks" esperados pelo formato de saida com essa
     mesma posicao (todos os pontos iguais ao centroide, z=0.0).

(Testamos antes tentar rodar o MediaPipe de novo dentro de um crop ao
redor do blob, mas a taxa de sucesso foi muito baixa — o modelo de
deteccao de palma nao reconhece a forma da luva mesmo com a mao ocupando
mais espaco no frame. O centroide do blob e' muito mais confiavel para
este caso de uso.)

Isso NAO reproduz o esqueleto real da mao (nao temos os 21 pontos reais),
mas garante que qualquer logica que consuma esses landmarks — por exemplo,
checar se algum ponto da mao esta dentro de uma ROI — funcione
corretamente independente de qual indice de landmark ela consulta, ja que
todos apontam para o mesmo lugar: a posicao real da luva no frame.

O handedness (Left/Right) nao pode ser determinado com certeza so' pela
cor do blob. Para evitar que as duas maos (quando ambas usam luva) caiam
no mesmo "balde" de rotulo — o que atrapalharia ROIs com categorias
diferentes por mao — usamos uma heuristica simples: quando ha' 2 blobs no
mesmo frame, o mais a esquerda vira "Left" e o mais a direita vira
"Right" (mesma convencao bruta que o MediaPipe usa, que o frontend depois
inverte). Isso pode errar se as maos se cruzarem no frame, mas evita a
colisao total de rotulo.

IMPORTANTE — formato dos 21 landmarks no fallback:
O frontend (VideoAnalyzer.jsx) rejeita silenciosamente qualquer deteccao
cuja "caixa" dos 21 pontos seja menor que um limiar minimo (funcao
isValidHand) — o que aconteceria se todos os 21 pontos fossem identicos
ao centroide. Por isso, distribuimos os pontos num formato de mao
aproximado (sintetico, nao e' o esqueleto real) escalado ao tamanho do
blob detectado, o suficiente para passar nesse limiar e desenhar um
overlay coerente. O landmark 8 (ponta do dedo indicador — usado pelo
frontend como "probe" para decidir se a mao esta dentro de uma ROI) e' a
UNICA excecao: fica exatamente no centroide do blob, preservando a
precisao de posicao que foi validada nos testes.
"""
import sys
import os
import json

# Import do glove_detector: funciona tanto quando este arquivo e' carregado
# como parte do pacote `backend.services` (modo frozen, worker_entry.py faz
# `from backend.services._preprocess_worker import run_worker`) quanto
# quando e' executado standalone como script (modo dev, subprocess direto).
try:
    from .glove_detector import detect_glove_blobs
except ImportError:
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from glove_detector import detect_glove_blobs


# Quantas maos tentar recuperar via fallback quando a deteccao direta falha.
# Alinhado com max_num_hands da instancia principal.
_MAX_GLOVE_BLOBS = 2

# Numero de landmarks que o MediaPipe Hands normalmente retorna por mao
# (0=pulso ... 20=ponta do mindinho).
_NUM_HAND_LANDMARKS = 21

# Indice do "probe" usado pelo VideoAnalyzer.jsx para checar ROI —
# INDEX_FINGER_TIP. Este landmark SEMPRE fica exatamente no centroide do
# blob no fallback (nao segue o template abaixo).
_PROBE_LANDMARK_IDX = 8

# Formato sintetico de mao (offsets normalizados, nao e' o esqueleto real)
# usado so' para: (a) passar no limiar isValidHand do frontend, e (b)
# desenhar um overlay com aparencia razoavel. dx/dy sao multiplicados pela
# metade da largura/altura do blob detectado. y negativo = "para cima"
# (dedos), y positivo = "para baixo" (pulso). Ordem = indices padrao do
# MediaPipe Hands (0=pulso, 1-4=polegar, 5-8=indicador, 9-12=medio,
# 13-16=anelar, 17-20=mindinho).
_HAND_SHAPE_TEMPLATE = [
    (0.00,  0.95),   # 0  wrist
    (-0.55, 0.55),   # 1  thumb_cmc
    (-0.85, 0.15),   # 2  thumb_mcp
    (-1.00, -0.20),  # 3  thumb_ip
    (-1.05, -0.55),  # 4  thumb_tip
    (-0.30, 0.05),   # 5  index_mcp
    (-0.33, -0.45),  # 6  index_pip
    (-0.34, -0.80),  # 7  index_dip
    (0.00, 0.00),    # 8  index_tip -> SOBRESCRITO com centroide exato (ver abaixo)
    (0.00, 0.05),    # 9  middle_mcp
    (0.02, -0.55),   # 10 middle_pip
    (0.02, -0.95),   # 11 middle_dip
    (0.02, -1.25),   # 12 middle_tip
    (0.30, 0.05),    # 13 ring_mcp
    (0.33, -0.40),   # 14 ring_pip
    (0.35, -0.75),   # 15 ring_dip
    (0.37, -1.00),   # 16 ring_tip
    (0.55, 0.15),    # 17 pinky_mcp
    (0.60, -0.25),   # 18 pinky_pip
    (0.63, -0.55),   # 19 pinky_dip
    (0.65, -0.80),   # 20 pinky_tip
]


def _pseudo_landmarks_from_blobs(blobs, frame_w: int, frame_h: int):
    """
    Constroi landmarks/handedness "falsos" a partir dos blobs de cor
    detectados. Cada mao recebe um formato sintetico de mao (ver
    _HAND_SHAPE_TEMPLATE) escalado ao tamanho do blob e centrado no
    centroide — suficiente para passar no filtro isValidHand do frontend
    e desenhar um overlay coerente. O landmark 8 (probe de ROI) fica
    exatamente no centroide, preservando a precisao de posicao.

    Handedness: quando ha' 2 blobs, o mais a esquerda no frame vira
    "Left" e o mais a direita vira "Right" (heuristica por posicao —
    nao e' deteccao real de lateralidade). Com 1 blob so', assume "Left".
    """
    landmarks_out  = []
    handedness_out = []

    # Ordenar por posicao X para dar rotulos consistentes entre frames
    # (evita que as duas maos colidam no mesmo rotulo).
    blobs_sorted = sorted(blobs, key=lambda b: b.cx)

    for i, blob in enumerate(blobs_sorted):
        cx_norm = blob.cx / frame_w
        cy_norm = blob.cy / frame_h
        half_w_norm = (blob.w / 2) / frame_w
        half_h_norm = (blob.h / 2) / frame_h

        pts = []
        for idx, (dx, dy) in enumerate(_HAND_SHAPE_TEMPLATE):
            if idx == _PROBE_LANDMARK_IDX:
                pts.append([cx_norm, cy_norm, 0.0])
            else:
                pts.append([
                    cx_norm + dx * half_w_norm,
                    cy_norm + dy * half_h_norm,
                    0.0,
                ])
        landmarks_out.append(pts)

        raw_label = "Left" if i == 0 else "Right"
        handedness_out.append([raw_label, 0.5])  # 0.5 = "estimado via cor", nao e' confianca real de ML

    return landmarks_out, handedness_out


def _max_video_seconds() -> float:
    """Limite de duração (s). Vem da env CTA_MAX_VIDEO_SECONDS; 0 = sem limite."""
    try:
        return float(os.environ.get("CTA_MAX_VIDEO_SECONDS", "600"))
    except ValueError:
        return 600.0


def probe_video(video_path: str, out_path: str) -> None:
    """Lê só os metadados (sem MediaPipe) e grava {fps, total_frames, duration_s}.

    duration_s = None quando o container não informa o nº de frames.
    """
    import cv2

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise RuntimeError("Nao foi possivel abrir o video (formato/codec nao suportado).")
    fps    = cap.get(cv2.CAP_PROP_FPS) or 0.0
    frames = cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0.0
    cap.release()

    duration = (frames / fps) if (fps > 0 and frames > 0) else None
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({"fps": fps, "total_frames": int(frames), "duration_s": duration}, f)


def run_worker(video_path: str, out_path: str) -> None:
    """Processa o vídeo e grava o resultado em out_path (JSON)."""
    import cv2
    import mediapipe as mp

    mp_hands = mp.solutions.hands

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise RuntimeError(f"Nao foi possivel abrir: {video_path}")

    fps         = cap.get(cv2.CAP_PROP_FPS) or 30.0
    max_frames  = int(_max_video_seconds() * fps) if _max_video_seconds() > 0 else None
    frame_w     = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    frame_h     = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    frames      = {}
    frame_index = 0

    # Contadores para diagnostico (impressos no final — uteis pra calibrar
    # GLOVE_HSV_RANGES em glove_detector.py se a taxa de fallback estiver alta)
    n_direct   = 0
    n_fallback = 0
    n_missed   = 0

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

            # Guarda extra: vídeos cujo container não informa a duração
            # só são detectados aqui.
            if max_frames is not None and frame_index >= max_frames:
                raise RuntimeError(
                    f"VIDEO_TOO_LONG: o video passa de {_max_video_seconds():.0f} s."
                )

            rgb    = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            result = hands.process(rgb)

            if result.multi_hand_landmarks:
                n_direct += 1
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
                # Fallback: detectar blob(s) de cor de luva e usar o
                # centroide de cada um como posicao da mao (ver nota no
                # topo do arquivo sobre por que nao tentamos mais o
                # MediaPipe dentro de um crop).
                blobs = detect_glove_blobs(frame, max_blobs=_MAX_GLOVE_BLOBS)

                if blobs:
                    n_fallback += 1
                    landmarks_out, handedness_out = _pseudo_landmarks_from_blobs(
                        blobs, frame_w=frame_w, frame_h=frame_h
                    )
                    frames[str(frame_index)] = {
                        "landmarks":  landmarks_out,
                        "handedness": handedness_out,
                    }
                else:
                    n_missed += 1
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

    print(
        f"[worker] frames: {frame_index} | diretos: {n_direct} | "
        f"via fallback (luva): {n_fallback} | sem deteccao: {n_missed}",
        flush=True,
    )


def main():
    args = sys.argv[1:]
    probe = bool(args) and args[0] == "--probe"
    if probe:
        args = args[1:]
    if len(args) < 2:
        print(json.dumps({"error": "Uso: worker.py [--probe] <video> <out.json>"}))
        sys.exit(1)
    try:
        (probe_video if probe else run_worker)(args[0], args[1])
        print("OK")
    except Exception as e:
        print(json.dumps({"error": str(e)}))
        sys.exit(1)


if __name__ == '__main__':
    main()
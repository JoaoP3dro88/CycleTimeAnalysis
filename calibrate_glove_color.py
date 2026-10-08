# -*- coding: utf-8 -*-
"""
calibrate_glove_color.py

Ferramenta interativa para calibrar GLOVE_HSV_RANGES (glove_detector.py).

Como usar:
    python calibrate_glove_color.py "video.mp4"
    python calibrate_glove_color.py "video.mp4" --frame 120

O que fazer na janela que abre:
    - Clique com o botao ESQUERDO em varios pontos DA LUVA (pele coberta
      pela luva verde), incluindo partes mais claras/escuras (sombra,
      reflexo) — quanto mais pontos representativos, melhor a faixa.
    - Pressione [N] para ir pro proximo frame (util se a luva aparece
      melhor em outro momento do video).
    - Pressione [C] para calcular e imprimir a faixa HSV sugerida.
    - Pressione [R] para limpar os pontos marcados e recomecar.
    - Pressione [Q] ou [ESC] para sair.

No final (tecla C ou ao sair com pontos marcados), o script imprime um
bloco pronto para colar em glove_detector.py, substituindo
GLOVE_HSV_RANGES.
"""

import sys
import argparse
import cv2
import numpy as np

WINDOW_NAME = "Calibracao de cor da luva  |  clique nos pixels da luva  |  [C] calcular  [R] limpar  [N] prox frame  [Q] sair"

samples_hsv = []       # lista de tuplas (h, s, v) amostradas
samples_xy  = []        # posicoes clicadas (para desenhar marcadores)
current_frame_bgr = None
current_frame_hsv = None


def sample_at(x: int, y: int, radius: int = 4):
    """Amostra a media HSV numa pequena regiao ao redor do clique — mais
    robusto que pegar um unico pixel (evita ruido de compressao do video)."""
    h_img, w_img = current_frame_hsv.shape[:2]
    x0, x1 = max(0, x - radius), min(w_img, x + radius)
    y0, y1 = max(0, y - radius), min(h_img, y + radius)
    region = current_frame_hsv[y0:y1, x0:x1].reshape(-1, 3)
    h, s, v = region.mean(axis=0)
    return int(h), int(s), int(v)


def mouse_callback(event, x, y, flags, param):
    if event == cv2.EVENT_LBUTTONDOWN:
        hsv = sample_at(x, y)
        samples_hsv.append(hsv)
        samples_xy.append((x, y))
        print(f"  ponto ({x},{y})  ->  HSV = {hsv}")
        redraw()


def redraw():
    display = current_frame_bgr.copy()
    for (x, y) in samples_xy:
        cv2.circle(display, (x, y), 6, (0, 0, 255), 2)
        cv2.circle(display, (x, y), 2, (0, 0, 255), -1)
    cv2.putText(
        display, f"{len(samples_hsv)} ponto(s) marcado(s)  |  [C]alcular  [R]limpar  [N]prox frame  [Q]sair",
        (10, 26), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2,
    )
    cv2.imshow(WINDOW_NAME, display)


def compute_range():
    if not samples_hsv:
        print("\nNenhum ponto marcado ainda — clique na luva antes de calcular.\n")
        return

    arr = np.array(samples_hsv)  # shape (N, 3)
    h, s, v = arr[:, 0], arr[:, 1], arr[:, 2]

    # Margem de seguranca: um pouco alem do min/max observado, pra cobrir
    # variacao de iluminacao que voce nao capturou nos cliques.
    H_MARGIN, S_MARGIN, V_MARGIN = 8, 35, 35

    h_min = max(0,   int(h.min()) - H_MARGIN)
    h_max = min(179, int(h.max()) + H_MARGIN)
    s_min = max(0,   int(s.min()) - S_MARGIN)
    s_max = min(255, int(s.max()) + S_MARGIN)
    v_min = max(0,   int(v.min()) - V_MARGIN)
    v_max = min(255, int(v.max()) + V_MARGIN)

    print("\n" + "=" * 70)
    print(f"Amostras: {len(samples_hsv)} ponto(s)")
    print(f"  H: min={h.min():.0f} max={h.max():.0f} media={h.mean():.1f}")
    print(f"  S: min={s.min():.0f} max={s.max():.0f} media={s.mean():.1f}")
    print(f"  V: min={v.min():.0f} max={v.max():.0f} media={v.mean():.1f}")
    print()
    print("Cole isto em glove_detector.py, substituindo GLOVE_HSV_RANGES:\n")
    print("GLOVE_HSV_RANGES = [")
    print(f"    (np.array([{h_min}, {s_min}, {v_min}]), np.array([{h_max}, {s_max}, {v_max}])),")
    print("]")
    print("=" * 70 + "\n")


def main():
    global current_frame_bgr, current_frame_hsv

    parser = argparse.ArgumentParser()
    parser.add_argument("video", help="caminho do video")
    parser.add_argument("--frame", type=int, default=0, help="numero do frame inicial")
    args = parser.parse_args()

    cap = cv2.VideoCapture(args.video)
    if not cap.isOpened():
        print(f"ERRO: nao foi possivel abrir: {args.video}")
        sys.exit(1)

    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    frame_idx = max(0, min(args.frame, total_frames - 1))

    def load_frame(idx):
        global current_frame_bgr, current_frame_hsv
        cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
        ok, frame = cap.read()
        if not ok:
            print(f"Nao foi possivel ler o frame {idx}")
            return False
        current_frame_bgr = frame
        current_frame_hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        return True

    if not load_frame(frame_idx):
        sys.exit(1)

    cv2.namedWindow(WINDOW_NAME)
    cv2.setMouseCallback(WINDOW_NAME, mouse_callback)
    redraw()

    print(f"Total de frames no video: {total_frames}")
    print(f"Frame atual: {frame_idx}")
    print("Clique nos pixels da luva na janela. Pressione C para calcular a faixa.\n")

    while True:
        key = cv2.waitKey(50) & 0xFF
        if key in (ord('q'), ord('Q'), 27):  # Q ou ESC
            break
        elif key in (ord('c'), ord('C')):
            compute_range()
        elif key in (ord('r'), ord('R')):
            samples_hsv.clear()
            samples_xy.clear()
            redraw()
            print("Pontos limpos.\n")
        elif key in (ord('n'), ord('N')):
            frame_idx = min(frame_idx + 30, total_frames - 1)  # pula ~1s (assumindo ~30fps)
            if load_frame(frame_idx):
                redraw()
                print(f"Frame atual: {frame_idx}")

    cap.release()
    cv2.destroyAllWindows()

    # Se saiu sem apertar C mas tinha pontos marcados, calcula mesmo assim
    if samples_hsv:
        compute_range()


if __name__ == "__main__":
    main()

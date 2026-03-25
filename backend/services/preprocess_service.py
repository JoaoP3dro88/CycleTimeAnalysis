from __future__ import annotations

"""
preprocess_service.py

Runs MediaPipe mp.solutions.hands on every frame of a video file and
returns the results as a plain dict that can be JSON-serialised directly.

Because the FastAPI venv has mediapipe 0.10.33 (no mp.solutions), we
delegate the actual processing to the system Python (Python 3.12 global)
which has mediapipe 0.10.21 with mp.solutions.hands available.

Result format:
  {
    "fps": 30.0,
    "total_frames": 3778,
    "frames": {
      "0":  null,
      "1":  {
        "landmarks": [[[x,y,z], ...21 pts], ...],
        "handedness": [["Left", 0.95], ...]
      },
      ...
    }
  }
"""

import json
import subprocess
import sys
import tempfile
from pathlib import Path

# Python global com mediapipe 0.10.21 (mp.solutions.hands disponível)
_GLOBAL_PYTHON = r"C:\Users\klj1ct\AppData\Local\Programs\Python\Python312\python.exe"

# Script auxiliar que faz o processamento real (chamado como subprocess)
_WORKER_SCRIPT = str(Path(__file__).parent / "_preprocess_worker.py")


def preprocess_video(video_path: str) -> dict:
    """
    Chama o worker Python externo e devolve o resultado como dict.
    Raises RuntimeError em caso de falha.
    """
    # Usar arquivo temporário para o resultado (evita limite de buffer do pipe)
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tmp:
        tmp_path = tmp.name

    try:
        result = subprocess.run(
            [_GLOBAL_PYTHON, _WORKER_SCRIPT, video_path, tmp_path],
            capture_output=True,
            text=True,
            encoding="utf-8",
        )

        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip() or "Falha no pré-processamento")

        # Ler resultado do arquivo temporário
        tmp_file = Path(tmp_path)
        if not tmp_file.exists() or tmp_file.stat().st_size == 0:
            raise RuntimeError("Worker não gerou arquivo de resultado")

        with open(tmp_path, "r", encoding="utf-8") as f:
            return json.load(f)

    finally:
        # Limpar arquivo temporário
        Path(tmp_path).unlink(missing_ok=True)

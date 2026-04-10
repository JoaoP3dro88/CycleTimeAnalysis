from __future__ import annotations

"""
preprocess_service.py

Runs MediaPipe mp.solutions.hands on every frame of a video file and
returns the results as a plain dict that can be JSON-serialised directly.

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
import os
import subprocess
import sys
import tempfile
from pathlib import Path

# Flag: True quando rodando dentro de um bundle PyInstaller
_IS_FROZEN = getattr(sys, "frozen", False)

# Caminho do site-packages do venv — onde mediapipe/cv2 estão instalados
# Funciona tanto em dev quanto no exe (embutido em _internal/venv_site_packages/)
_VENV_SITE: str | None = None
if _IS_FROZEN:
    _internal = Path(getattr(sys, "_MEIPASS", ""))
    _candidate = _internal / "venv_site_packages"
    if _candidate.exists():
        _VENV_SITE = str(_candidate)


def _get_python_and_worker() -> tuple[str, str]:
    """
    Retorna (caminho_python, caminho_worker_script).

    Frozen: lê o pyvenv.cfg embutido para descobrir o Python base do sistema
            e passa o venv_site_packages via PYTHONPATH no preprocess_video().
    Dev:    usa sys.executable (já tem mediapipe via venv).
    """
    if _IS_FROZEN:
        _internal = Path(getattr(sys, "_MEIPASS", ""))
        # Lê o python.exe base do pyvenv.cfg embutido
        cfg = _internal / "pyvenv.cfg"
        python_exe = None
        if cfg.exists():
            for line in cfg.read_text(encoding="utf-8").splitlines():
                if line.startswith("executable"):
                    python_exe = line.split("=", 1)[1].strip()
                    break
        # Fallback: usa python do PATH
        if not python_exe or not Path(python_exe).exists():
            import shutil
            python_exe = shutil.which("python") or shutil.which("python3") or "python"
        worker_script = _internal / "worker" / "_preprocess_worker.py"
        return str(python_exe), str(worker_script)
    else:
        return sys.executable, str(Path(__file__).parent / "_preprocess_worker.py")


def preprocess_video(video_path: str) -> dict:
    """
    Processa o vídeo com MediaPipe e devolve o resultado como dict.
    Sempre usa subprocess:
    - Frozen: usa o python.exe do venv embutido em _internal/venv_python/
              com PYTHONPATH apontando para o site-packages do venv embutido
    - Dev: usa sys.executable diretamente
    """
    python_exe, worker_script = _get_python_and_worker()

    env = None
    if _IS_FROZEN:
        _internal = Path(getattr(sys, "_MEIPASS", ""))
        venv_site = _internal / "venv_site_packages"
        if venv_site.exists():
            env = os.environ.copy()
            env["PYTHONPATH"] = str(venv_site)
            # Limpar VIRTUAL_ENV para evitar conflitos
            env.pop("VIRTUAL_ENV", None)

    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tmp:
        tmp_path = tmp.name

    try:
        result = subprocess.run(
            [python_exe, worker_script, video_path, tmp_path],
            capture_output=True,
            text=True,
            encoding="utf-8",
            env=env,
        )
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip() or "Falha no pré-processamento")

        tmp_file = Path(tmp_path)
        if not tmp_file.exists() or tmp_file.stat().st_size == 0:
            raise RuntimeError("Worker não gerou arquivo de resultado")

        with open(tmp_path, "r", encoding="utf-8") as f:
            return json.load(f)

    finally:
        Path(tmp_path).unlink(missing_ok=True)

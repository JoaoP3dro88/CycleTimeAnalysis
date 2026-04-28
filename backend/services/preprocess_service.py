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

Estratégia de execução:
  - Frozen (bundle PyInstaller pasta): chama run_worker() diretamente no
    processo principal — MediaPipe e seus DLLs estão em _internal/, acessíveis.
  - Dev: usa subprocess para isolar o processo (MediaPipe não polui o servidor).
"""

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

# Flag: True quando rodando dentro de um bundle PyInstaller
_IS_FROZEN = getattr(sys, "frozen", False)


def preprocess_video(video_path: str) -> dict:
    """
    Processa o vídeo com MediaPipe e devolve o resultado como dict.

    - Frozen: importa e chama run_worker() diretamente (MediaPipe bundled).
    - Dev:    usa subprocess para isolar o processo do servidor FastAPI.
    """
    if _IS_FROZEN:
        return _preprocess_direct(video_path)
    else:
        return _preprocess_subprocess(video_path)


def _preprocess_direct(video_path: str) -> dict:
    """Frozen: usa o python.exe portátil bundled em python_worker/.
    Esse Python tem mediapipe instalado e funciona nativamente — sem PyInstaller
    bundling de DLLs nativos que causam DLL init failures.
    """
    import tempfile as _tempfile
    import time

    _internal = Path(getattr(sys, "_MEIPASS", ""))
    # _internal = dist/CycleTimeAnalysis/_internal/
    # python_worker fica em  dist/CycleTimeAnalysis/python_worker/
    dist_dir      = _internal.parent
    worker_python = dist_dir / "python_worker" / "python.exe"
    worker_script = _internal / "worker" / "worker_entry.py"
    site_packages = dist_dir / "python_worker" / "Lib" / "site-packages"

    if not worker_python.exists():
        raise RuntimeError(f"python_worker/python.exe não encontrado em: {worker_python}")
    if not worker_script.exists():
        raise RuntimeError(f"worker_entry.py não encontrado em: {worker_script}")

    print(f"[preprocess] python worker: {worker_python}", flush=True)
    print(f"[preprocess] worker script: {worker_script}", flush=True)
    print(f"[preprocess] vídeo: {video_path}", flush=True)

    with _tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tmp:
        tmp_path = tmp.name

    t0 = time.time()
    try:
        env = {
            **os.environ,
            "PYTHONPATH": str(site_packages),
            "PYTHONIOENCODING": "utf-8",
            # Evitar que o python_worker use o venv errado
            "VIRTUAL_ENV": "",
            "PYTHONHOME": "",
        }
        result = subprocess.run(
            [str(worker_python), str(worker_script), video_path, tmp_path],
            capture_output=True,
            env=env,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        elapsed = time.time() - t0
        stdout = result.stdout.decode("utf-8", errors="replace") if result.stdout else ""
        stderr = result.stderr.decode("utf-8", errors="replace") if result.stderr else ""
        print(f"[preprocess] worker encerrou em {elapsed:.1f}s, returncode={result.returncode}", flush=True)
        if stdout: print(f"[preprocess] stdout:\n{stdout}", flush=True)
        if stderr: print(f"[preprocess] stderr:\n{stderr}", flush=True)

        if result.returncode != 0:
            detail = (stderr or stdout or "Sem saída do worker").strip()
            raise RuntimeError(f"Falha no pré-processamento (worker):\n{detail}")

        tmp_file = Path(tmp_path)
        if not tmp_file.exists() or tmp_file.stat().st_size == 0:
            raise RuntimeError("Worker não gerou arquivo de resultado")

        print(f"[preprocess] resultado: {tmp_file.stat().st_size / 1024:.0f} KB", flush=True)
        with open(tmp_path, "r", encoding="utf-8") as f:
            return json.load(f)
    finally:
        Path(tmp_path).unlink(missing_ok=True)


def _preprocess_subprocess(video_path: str) -> dict:
    """Dev: executa o worker como subprocess para isolar o processo."""
    python_exe = sys.executable
    worker_script = str(Path(__file__).parent / "_preprocess_worker.py")

    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tmp:
        tmp_path = tmp.name

    try:
        result = subprocess.run(
            [python_exe, worker_script, video_path, tmp_path],
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        if result.returncode != 0:
            detail = (result.stderr or result.stdout or "Sem saída do worker").strip()
            raise RuntimeError(
                f"Falha no pré-processamento\n"
                f"Python: {python_exe}\n"
                f"Worker: {worker_script}\n"
                f"Saída:\n{detail}"
            )

        tmp_file = Path(tmp_path)
        if not tmp_file.exists() or tmp_file.stat().st_size == 0:
            raise RuntimeError("Worker não gerou arquivo de resultado")

        with open(tmp_path, "r", encoding="utf-8") as f:
            return json.load(f)

    finally:
        Path(tmp_path).unlink(missing_ok=True)

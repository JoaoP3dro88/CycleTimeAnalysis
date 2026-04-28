"""Entry-point para rodar a aplicação (dev e produção/PyInstaller).

Uso:
    python -m backend.run                        # desenvolvimento
    CycleTimeAnalysis.exe                        # bundle PyInstaller (servidor)
    CycleTimeAnalysis.exe --worker <video> <out> # modo worker (subprocess interno)
"""

from __future__ import annotations

import os
import sys
import threading
import time
import webbrowser
from pathlib import Path

_PORT = 8000
_HOST = "127.0.0.1"
_LOCK_FILE = Path(os.environ.get("TEMP", os.environ.get("TMP", "."))) / "CycleTimeAnalysis.lock"


def _ensure_project_root_on_syspath() -> None:
	project_root = Path(__file__).resolve().parent.parent
	root_str = str(project_root)
	if root_str not in sys.path:
		sys.path.insert(0, root_str)


def _already_running() -> bool:
	"""Retorna True se outro processo já está escutando na porta."""
	import socket
	with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
		s.settimeout(0.5)
		return s.connect_ex((_HOST, _PORT)) == 0


def _open_browser():
	time.sleep(1.5)
	webbrowser.open(f"http://{_HOST}:{_PORT}")


def _setup_logging(is_frozen: bool) -> Path:
	"""Configura stdout/stderr e retorna o caminho do log file."""
	log_dir = Path(os.environ.get("TEMP", os.environ.get("TMP", ".")))
	log_file = log_dir / "CycleTimeAnalysis.log"

	if is_frozen:
		log_handle = open(log_file, "w", encoding="utf-8", buffering=1)
		sys.stdout = log_handle
		sys.stderr = log_handle
	return log_file


def main() -> None:
	_ensure_project_root_on_syspath()

	is_frozen = getattr(sys, "frozen", False)

	# ── Modo worker: o exe é chamado como subprocess para processar um vídeo ──
	# Desta forma o bootloader do PyInstaller configura todos os DLLs antes
	# de qualquer import (incluindo mediapipe/_framework_bindings.pyd).
	if len(sys.argv) >= 4 and sys.argv[1] == "--worker":
		video_path = sys.argv[2]
		out_path   = sys.argv[3]

		# Pré-carregar opencv_world com ctypes ANTES do import mediapipe.
		# _framework_bindings.pyd tenta LoadLibrary("opencv_world*.dll") dentro
		# do seu DllMain — se o DLL não estiver no espaço de endereços, falha.
		# ctypes.CDLL força o carregamento antecipado, colocando-o no processo.
		if is_frozen:
			import ctypes
			_internal = getattr(sys, "_MEIPASS", "")
			_mp_python = os.path.join(_internal, "mediapipe", "python")
			print(f"[worker] _MEIPASS={_internal}", flush=True)
			print(f"[worker] PATH={os.environ.get('PATH','')[:400]}", flush=True)
			print(f"[worker] mediapipe/python existe: {os.path.isdir(_mp_python)}", flush=True)
			if os.path.isdir(_mp_python):
				for _dll_name in os.listdir(_mp_python):
					if _dll_name.lower().endswith(".dll"):
						_dll_full = os.path.join(_mp_python, _dll_name)
						try:
							ctypes.CDLL(_dll_full)
							print(f"[worker] ctypes OK: {_dll_name}", flush=True)
						except OSError as e:
							print(f"[worker] ctypes FALHOU {_dll_name}: {e}", flush=True)

		from backend.services._preprocess_worker import run_worker
		run_worker(video_path, out_path)
		sys.exit(0)

	_setup_logging(is_frozen)

	# ── Single-instance: se já está rodando, só abre o browser ──────────────
	if _already_running():
		webbrowser.open(f"http://{_HOST}:{_PORT}")
		sys.exit(0)

	try:
		import uvicorn
	except Exception as exc:
		print(f"FATAL: falha ao importar uvicorn: {exc}", flush=True)
		raise

	# Abre o browser em background após o servidor iniciar
	threading.Thread(target=_open_browser, daemon=True).start()

	try:
		uvicorn.run(
			"backend.main:app",
			host=_HOST,
			port=_PORT,
			reload=False,
			log_level="info",
		)
	except Exception as exc:
		import traceback
		print(f"FATAL uvicorn: {exc}", flush=True)
		traceback.print_exc()
		raise


if __name__ == "__main__":
	main()


"""Entry-point para rodar a aplicação (dev e produção/PyInstaller).

Uso:
    python -m backend.run          # desenvolvimento
    CycleTimeAnalysis.exe          # bundle PyInstaller
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


def main() -> None:
	_ensure_project_root_on_syspath()

	is_frozen = getattr(sys, "frozen", False)

	# ── Single-instance: se já está rodando, só abre o browser ──────────────
	if _already_running():
		webbrowser.open(f"http://{_HOST}:{_PORT}")
		sys.exit(0)

	import uvicorn

	# Quando empacotado sem console, sys.stdout/stderr são None.
	if is_frozen:
		devnull = open(os.devnull, 'w')
		if sys.stdout is None:
			sys.stdout = devnull
		if sys.stderr is None:
			sys.stderr = devnull

	# Abre o browser em background após o servidor iniciar
	threading.Thread(target=_open_browser, daemon=True).start()

	uvicorn.run(
		"backend.main:app",
		host=_HOST,
		port=_PORT,
		reload=not is_frozen,
		log_config=None if is_frozen else uvicorn.config.LOGGING_CONFIG,
	)


if __name__ == "__main__":
	main()


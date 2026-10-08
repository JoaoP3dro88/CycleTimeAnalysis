"""Entry-point da API (dev e produção/PyInstaller).

Uso:
    python -m backend.run                                   # desenvolvimento (127.0.0.1:8000)
    cycletime_api.exe --host 0.0.0.0 --port 48001 ^
        --ssl-certfile cert.pem --ssl-keyfile key.pem ^
        --cors-origins https://ct0devtefsrv01.br.bosch.com  # servidor
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path


def _ensure_project_root_on_syspath() -> None:
	project_root = Path(__file__).resolve().parent.parent
	root_str = str(project_root)
	if root_str not in sys.path:
		sys.path.insert(0, root_str)


def _app_dir() -> Path:
	"""Pasta do .exe (frozen) ou raiz do projeto (dev)."""
	if getattr(sys, "frozen", False):
		return Path(sys.executable).parent
	return Path(__file__).resolve().parent.parent


def _abs(p: str | None) -> str | None:
	"""Caminhos relativos são resolvidos a partir da pasta do exe, não do cwd
	(um serviço Windows roda com cwd = System32)."""
	if not p:
		return None
	path = Path(p)
	return str(path if path.is_absolute() else _app_dir() / path)


def _parse_args() -> argparse.Namespace:
	ap = argparse.ArgumentParser(description="Cycle Time Analysis API")
	ap.add_argument("--host", default="127.0.0.1")
	ap.add_argument("--port", type=int, default=8000)
	ap.add_argument("--ssl-certfile", default=None)
	ap.add_argument("--ssl-keyfile", default=None)
	ap.add_argument("--data-dir", default=None,
	                help="Pasta persistente (padrão: <pasta do exe>/data)")
	ap.add_argument("--cors-origins", default=None,
	                help="Origens permitidas separadas por vírgula, ex.: https://ct0devtefsrv01.br.bosch.com")
	ap.add_argument("--log-file", default=None,
	                help="Se informado, redireciona stdout/stderr para este arquivo")
	return ap.parse_args()


def main() -> None:
	_ensure_project_root_on_syspath()
	args = _parse_args()

	if args.log_file:
		log_path = Path(_abs(args.log_file))
		log_path.parent.mkdir(parents=True, exist_ok=True)
		handle = open(log_path, "a", encoding="utf-8", buffering=1)
		sys.stdout = handle
		sys.stderr = handle

	# Precisa ser definido ANTES de importar backend.config / backend.main
	if args.data_dir:
		os.environ["CTA_DATA_DIR"] = _abs(args.data_dir)
	if args.cors_origins:
		os.environ["CTA_CORS_ORIGINS"] = args.cors_origins

	try:
		import uvicorn
	except Exception as exc:
		print(f"FATAL: falha ao importar uvicorn: {exc}", flush=True)
		raise

	try:
		uvicorn.run(
			"backend.main:app",
			host=args.host,
			port=args.port,
			ssl_certfile=_abs(args.ssl_certfile),
			ssl_keyfile=_abs(args.ssl_keyfile),
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
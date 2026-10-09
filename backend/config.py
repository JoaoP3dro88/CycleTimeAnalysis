from __future__ import annotations

import os
import sys
from pathlib import Path

from pydantic import BaseModel

_DEV_ORIGINS = [
	"http://localhost:5173",
	"http://127.0.0.1:5173",
	"http://localhost:5174",
	"http://127.0.0.1:5174",
]


def _default_data_dir() -> str:
	"""Pasta PERSISTENTE de dados (project.json, vídeos).

	Sempre caminho absoluto: quando roda como serviço o diretório de trabalho
	é C:\\Windows\\System32, então './data' gravaria no lugar errado.
	"""
	env = os.environ.get("CTA_DATA_DIR")
	if env:
		return env
	if getattr(sys, "frozen", False):
		# Ao lado do .exe (fora de _internal, que é substituído a cada deploy)
		return str(Path(sys.executable).parent / "data")
	# Dev: <raiz do projeto>/data
	return str(Path(__file__).resolve().parent.parent / "data")


def _default_cors_origins() -> list[str]:
	env = os.environ.get("CTA_CORS_ORIGINS")
	if env:
		return [o.strip() for o in env.split(",") if o.strip()]
	return list(_DEV_ORIGINS)


def _env_int(name: str, default: int) -> int:
	try:
		return int(os.environ.get(name, default))
	except (TypeError, ValueError):
		return default


class Settings(BaseModel):
	app_name: str = "Cycle Time Analysis API"
	api_prefix: str = "/api"
	cors_allow_origins: list[str] = _default_cors_origins()
	data_dir: str = _default_data_dir()
	videos_dirname: str = "videos"
	users_dirname: str = "users"

	# ── Limites de vídeo ────────────────────────────────────────────────────
	# Duração máxima (segundos). Padrão: 10 minutos.
	max_video_seconds: int = _env_int("CTA_MAX_VIDEO_SECONDS", 600)
	# Tamanho máximo do arquivo (MB) — proteção extra de disco/memória.
	max_video_mb: int = _env_int("CTA_MAX_VIDEO_MB", 2048)
	# Quantos pré-processamentos (MediaPipe) rodam ao mesmo tempo; os demais esperam na fila.
	max_concurrent_preprocess: int = _env_int("CTA_MAX_CONCURRENT_PREPROCESS", 2)


settings = Settings()
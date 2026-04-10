from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pathlib import Path
import os
import sys
import threading
import time

from .api.routers import analytics, projects, preprocess
from .config import settings

# Pasta onde o `npm run build` deposita os arquivos do React
_FRONTEND_DIST = Path(__file__).parent / "frontend_dist"

# Heartbeat: timestamp do último ping recebido do frontend
_last_heartbeat: float = time.time()
_HEARTBEAT_TIMEOUT = 20  # segundos sem ping → encerrar


def _watchdog():
	"""Encerra o processo se o frontend sumir por mais de HEARTBEAT_TIMEOUT segundos."""
	# Aguarda o servidor subir completamente
	time.sleep(8)
	while True:
		time.sleep(5)
		if time.time() - _last_heartbeat > _HEARTBEAT_TIMEOUT:
			os._exit(0)


def create_app() -> FastAPI:
	app = FastAPI(title=settings.app_name)

	app.add_middleware(
		CORSMiddleware,
		allow_origins=settings.cors_allow_origins,
		allow_credentials=True,
		allow_methods=["*"],
		allow_headers=["*"]
	)

	app.include_router(projects.router,    prefix=settings.api_prefix)
	app.include_router(analytics.router,   prefix=settings.api_prefix)
	app.include_router(preprocess.router,  prefix=settings.api_prefix)

	# Static mount for uploaded videos
	Path(settings.data_dir, settings.videos_dirname).mkdir(parents=True, exist_ok=True)
	app.mount(
		f"{settings.api_prefix}/projects/videos-static",
		StaticFiles(directory=f"{settings.data_dir}/{settings.videos_dirname}"),
		name="videos",
	)

	@app.get("/health")
	def health() -> dict[str, str]:
		return {"status": "ok"}

	@app.post("/api/heartbeat", include_in_schema=False)
	def heartbeat() -> dict[str, str]:
		"""Recebe ping do frontend para saber que ainda está aberto."""
		global _last_heartbeat
		_last_heartbeat = time.time()
		return {"status": "ok"}

	@app.post("/api/shutdown", include_in_schema=False)
	def shutdown() -> dict[str, str]:
		"""Encerra o servidor graciosamente (chamado pelo frontend ao fechar)."""
		threading.Thread(target=lambda: (time.sleep(0.3), os._exit(0)), daemon=True).start()
		return {"status": "bye"}

	# Servir o frontend React em produção (quando o build existir)
	if _FRONTEND_DIST.exists():
		# Iniciar o watchdog apenas em produção (exe)
		if getattr(sys, "frozen", False):
			threading.Thread(target=_watchdog, daemon=True).start()

		app.mount(
			"/assets",
			StaticFiles(directory=str(_FRONTEND_DIST / "assets")),
			name="frontend-assets",
		)

		@app.get("/{full_path:path}", include_in_schema=False)
		def serve_frontend(full_path: str) -> FileResponse:
			index = _FRONTEND_DIST / "index.html"
			return FileResponse(str(index))

	return app


app = create_app()

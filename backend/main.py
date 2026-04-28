from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pathlib import Path
import os
import sys
import threading
import time
import mimetypes

from .api.routers import analytics, projects, preprocess
from .config import settings

# Garantir que .wasm e .js têm MIME types corretos (pode faltar no registry do Windows)
mimetypes.add_type('application/wasm', '.wasm')
mimetypes.add_type('text/javascript', '.js')
mimetypes.add_type('text/javascript', '.mjs')

# Pasta onde o `npm run build` deposita os arquivos do React
_FRONTEND_DIST = Path(__file__).parent / "frontend_dist"

# Heartbeat: timestamp do último ping recebido do frontend
_last_heartbeat: float = 0.0          # 0 = ainda não recebeu nenhum ping
_heartbeat_received: bool = False     # True após o primeiro ping
_HEARTBEAT_TIMEOUT = 60  # segundos sem ping → encerrar (deve cobrir o preprocess)


def _watchdog():
	"""Encerra o processo se o frontend sumir por mais de HEARTBEAT_TIMEOUT segundos."""
	global _heartbeat_received
	# Aguarda o PRIMEIRO heartbeat antes de começar a monitorar
	# (evita encerrar durante a inicialização ou se o browser demorar a abrir)
	while not _heartbeat_received:
		time.sleep(1)
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

	# NOTA: COOP/COEP headers removidos do middleware global — causavam crash
	# ao modificar FileResponse de streaming (JS bundle de 5 MB).
	# MediaPipe Tasks Vision não precisa de SharedArrayBuffer para funcionar.

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
		global _last_heartbeat, _heartbeat_received
		_last_heartbeat = time.time()
		_heartbeat_received = True
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

		# Servir arquivos WASM do MediaPipe com MIME types forçados.
		# NÃO usa StaticFiles — no Windows o registry pode mapear .js/.wasm para
		# text/plain, o que impede o browser de executar os arquivos.
		_wasm_dir = _FRONTEND_DIST / "mediapipe-wasm"
		if _wasm_dir.exists():
			_WASM_MIME: dict[str, str] = {
				".js":   "text/javascript; charset=utf-8",
				".mjs":  "text/javascript; charset=utf-8",
				".wasm": "application/wasm",
				".task": "application/octet-stream",
			}

			@app.api_route("/mediapipe-wasm/{filename:path}", methods=["GET", "HEAD"], include_in_schema=False)
			def serve_mediapipe_wasm(filename: str):
				file_path = (_wasm_dir / filename).resolve()
				# Evitar path traversal
				if not str(file_path).startswith(str(_wasm_dir.resolve())):
					from fastapi.responses import JSONResponse
					return JSONResponse({"error": "forbidden"}, status_code=403)
				if not file_path.exists():
					from fastapi.responses import JSONResponse
					return JSONResponse({"error": "not found"}, status_code=404)
				suffix = file_path.suffix.lower()
				media_type = _WASM_MIME.get(suffix, "application/octet-stream")
				# FileResponse com media_type explícito sobrescreve o MIME do sistema
				return FileResponse(
					path=str(file_path),
					media_type=media_type,
					headers={"Cache-Control": "public, max-age=86400"},
				)

		@app.get("/{full_path:path}", include_in_schema=False)
		def serve_frontend(full_path: str) -> FileResponse:
			index = _FRONTEND_DIST / "index.html"
			return FileResponse(str(index))

	return app


app = create_app()

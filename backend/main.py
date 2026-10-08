from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pathlib import Path
import mimetypes

from .api.routers import analytics, projects, preprocess
from .config import settings

# Garantir MIME types corretos para os vídeos (o registry do Windows pode falhar)
mimetypes.add_type("video/mp4", ".mp4")
mimetypes.add_type("video/webm", ".webm")


def create_app() -> FastAPI:
	app = FastAPI(title=settings.app_name)

	app.add_middleware(
		CORSMiddleware,
		allow_origins=settings.cors_allow_origins,
		allow_credentials=True,
		allow_methods=["*"],
		allow_headers=["*"],
	)

	app.include_router(projects.router,    prefix=settings.api_prefix)
	app.include_router(analytics.router,   prefix=settings.api_prefix)
	app.include_router(preprocess.router,  prefix=settings.api_prefix)

	# Static mount for uploaded videos
	videos_dir = Path(settings.data_dir, settings.videos_dirname)
	videos_dir.mkdir(parents=True, exist_ok=True)
	app.mount(
		f"{settings.api_prefix}/projects/videos-static",
		StaticFiles(directory=str(videos_dir)),
		name="videos",
	)

	@app.get("/health")
	@app.get(f"{settings.api_prefix}/health")
	def health() -> dict[str, str]:
		return {"status": "ok"}

	# ── Compatibilidade com o frontend antigo (modo desktop) ─────────────────
	# Em servidor NÃO pode encerrar o processo: um usuário fechando a aba
	# derrubaria a API para todos. Mantidos como no-op para o frontend não
	# receber erro enquanto as chamadas não forem removidas de lá.
	@app.post("/api/heartbeat", include_in_schema=False)
	def heartbeat() -> dict[str, str]:
		return {"status": "ok"}

	@app.post("/api/shutdown", include_in_schema=False)
	def shutdown() -> dict[str, str]:
		return {"status": "ignored"}

	# O frontend (React) é servido pelo IIS, não por esta API.
	return app


app = create_app()
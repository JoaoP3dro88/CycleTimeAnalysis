from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pathlib import Path

from .api.routers import analytics, projects
from .config import settings


def create_app() -> FastAPI:
	app = FastAPI(title=settings.app_name)

	app.add_middleware(
		CORSMiddleware,
		allow_origins=settings.cors_allow_origins,
		allow_credentials=True,
		allow_methods=["*"],
		allow_headers=["*"]
	)

	app.include_router(projects.router, prefix=settings.api_prefix)
	app.include_router(analytics.router, prefix=settings.api_prefix)

	# Static mount for uploaded videos (solution B).
	# This enables the frontend to reload the same video URL across sessions.
	Path(settings.data_dir, settings.videos_dirname).mkdir(parents=True, exist_ok=True)
	app.mount(
		f"{settings.api_prefix}/projects/videos-static",
		StaticFiles(directory=f"{settings.data_dir}/{settings.videos_dirname}"),
		name="videos",
	)

	@app.get("/health")
	def health() -> dict[str, str]:
		return {"status": "ok"}

	return app


app = create_app()

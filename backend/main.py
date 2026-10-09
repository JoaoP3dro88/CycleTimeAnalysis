from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import mimetypes

from .api.routers import analytics, projects, preprocess
from .config import settings

# Garantir MIME types corretos para os vídeos (o registry do Windows pode falhar)
mimetypes.add_type("video/mp4", ".mp4")
mimetypes.add_type("video/webm", ".webm")


def create_app() -> FastAPI:
	app = FastAPI(title=settings.app_name)

	# Rejeita uploads grandes ANTES de receber o corpo (o parse do multipart
	# gravaria o arquivo inteiro em disco antes de qualquer validação).
	@app.middleware("http")
	async def limit_upload_size(request: Request, call_next):
		if request.method == "POST" and request.url.path.endswith(("/videos/upload", "/preprocess")):
			length = request.headers.get("content-length")
			max_bytes = settings.max_video_mb * 1024 * 1024
			# pequena folga para o overhead do multipart
			if length and length.isdigit() and int(length) > max_bytes + 1024 * 1024:
				return JSONResponse(
					status_code=413,
					content={"detail": f"Arquivo maior que o limite de {settings.max_video_mb} MB."},
				)
		return await call_next(request)

	# CORS por último = camada mais externa (assim até as respostas 413 levam os headers CORS)
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

	@app.get("/health")
	@app.get(f"{settings.api_prefix}/health")
	def health() -> dict[str, str]:
		return {"status": "ok"}

	# O frontend (React) é servido pelo IIS, não por esta API.
	return app


app = create_app()
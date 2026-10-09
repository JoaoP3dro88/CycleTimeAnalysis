from __future__ import annotations

import asyncio
import os
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import FileResponse

from ...config import settings
from ...models.schemas import Project
from ...services.preprocess_service import (
    VideoTooLongError,
    VideoUnreadableError,
    probe_video,
)
from ...services.storage_service import load_project, save_project
from ...services.upload_service import save_upload_to_temp
from ...services.user_service import normalize_user_id, user_videos_dir

# Todas as rotas são escopadas por usuário: /api/users/{user_id}/projects/...
router = APIRouter(prefix="/users/{user_id}/projects", tags=["projects"])


def _video_url(user_id: str, name: str) -> str:
    return f"{settings.api_prefix}/users/{normalize_user_id(user_id)}/projects/videos/{name}"


@router.get("/current", response_model=Project)
def get_current_project(user_id: str) -> Project:
    return load_project(user_id)


@router.post("/reset", response_model=Project)
def reset_project(user_id: str) -> Project:
    """Volta o projeto do usuário ao estado vazio."""
    project = Project()
    save_project(user_id, project)
    return project


@router.post("/import", response_model=Project)
def import_project(user_id: str, project: Project) -> Project:
    save_project(user_id, project)
    return project


@router.get("/export", response_model=Project)
def export_project(user_id: str) -> Project:
    return load_project(user_id)


@router.get("/videos")
def list_videos(user_id: str) -> list[dict[str, str]]:
    return [
        {"name": p.name, "url": _video_url(user_id, p.name)}
        for p in sorted(user_videos_dir(user_id).glob("*"))
        if p.is_file() and not p.name.endswith(".tmp")
    ]


@router.get("/videos/{filename}")
def get_video(user_id: str, filename: str) -> FileResponse:
    videos_dir = user_videos_dir(user_id).resolve()
    path = (videos_dir / filename).resolve()

    # Guarda contra path traversal: o arquivo precisa estar dentro da pasta do usuário.
    if videos_dir not in path.parents:
        raise HTTPException(status_code=400, detail="Invalid filename")
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Video not found")

    return FileResponse(path)


@router.post("/videos/upload")
async def upload_video(user_id: str, file: UploadFile = File(...)) -> dict[str, str]:
    if not file.filename:
        raise HTTPException(status_code=400, detail="Missing filename")

    videos_dir = user_videos_dir(user_id)
    safe_name = Path(file.filename).name

    # 1) grava em streaming respeitando o limite de MB (413 se passar)
    tmp = await save_upload_to_temp(file, dest_dir=videos_dir)
    try:
        # 2) valida a duração (limite de 10 min por padrão)
        try:
            await asyncio.to_thread(probe_video, str(tmp))
        except VideoTooLongError as e:
            raise HTTPException(status_code=413, detail=str(e))
        except VideoUnreadableError as e:
            raise HTTPException(status_code=422, detail=str(e))

        # 3) aceita: troca atômica para o nome final
        os.replace(tmp, videos_dir / safe_name)
    finally:
        Path(tmp).unlink(missing_ok=True)

    return {"name": safe_name, "url": _video_url(user_id, safe_name)}

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import FileResponse

from ...config import settings
from ...models.schemas import Project
from ...services.storage_service import load_project, save_project

router = APIRouter(prefix="/projects", tags=["projects"])


def _videos_dir() -> Path:
    d = Path(settings.data_dir) / settings.videos_dirname
    d.mkdir(parents=True, exist_ok=True)
    return d


@router.get("/current", response_model=Project)
def get_current_project() -> Project:
    return load_project(settings.data_dir)


@router.post("/reset", response_model=Project)
def reset_project() -> Project:
    """Reset the persisted project back to an empty/default state."""
    project = Project()
    save_project(settings.data_dir, project)
    return project


@router.post("/import", response_model=Project)
def import_project(project: Project) -> Project:
    save_project(settings.data_dir, project)
    return project


@router.get("/export", response_model=Project)
def export_project() -> Project:
    return load_project(settings.data_dir)


@router.get("/videos")
def list_videos() -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    for p in sorted(_videos_dir().glob("*")):
        if p.is_file():
            out.append({"name": p.name, "url": f"{settings.api_prefix}/projects/videos/{p.name}"})
    return out


@router.get("/videos/{filename}")
def get_video(filename: str) -> FileResponse:
    path = (_videos_dir() / filename).resolve()
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail="Video not found")

    # Basic path traversal guard: ensure it's inside the videos dir.
    if _videos_dir().resolve() not in path.parents:
        raise HTTPException(status_code=400, detail="Invalid filename")

    return FileResponse(path)


@router.post("/videos/upload")
async def upload_video(file: UploadFile = File(...)) -> dict[str, str]:
    if not file.filename:
        raise HTTPException(status_code=400, detail="Missing filename")

    safe_name = Path(file.filename).name
    dest = _videos_dir() / safe_name

    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="Empty file")

    dest.write_bytes(data)
    return {"name": safe_name, "url": f"{settings.api_prefix}/projects/videos/{safe_name}"}

from __future__ import annotations

import mimetypes
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse

from ...config import settings
from ...models.schemas import Project
from ...services.storage_service import load_project, save_project

router = APIRouter(prefix="/projects", tags=["projects"])

# Video extensions considered safe to serve from arbitrary local paths
_VIDEO_SUFFIXES = {".mp4", ".mov", ".avi", ".mkv", ".webm", ".m4v", ".ts", ".mts"}


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


@router.get("/video-by-path")
def get_video_by_path(path: str = Query(..., description="Absolute path to the video file")) -> FileResponse:
    """Serve a video file from an arbitrary absolute path on the local machine.

    Security constraints:
    - Path must be absolute.
    - File must exist and be a regular file.
    - Extension must be in the allowed video suffixes set.
    - This endpoint is intentionally local-only (no auth needed because the
      backend only binds to 127.0.0.1).
    """
    p = Path(path)

    if not p.is_absolute():
        raise HTTPException(status_code=400, detail="Path must be absolute")
    if not p.exists() or not p.is_file():
        raise HTTPException(status_code=404, detail="File not found")
    if p.suffix.lower() not in _VIDEO_SUFFIXES:
        raise HTTPException(status_code=400, detail="Not a supported video file type")

    media_type = mimetypes.guess_type(str(p))[0] or "video/mp4"
    return FileResponse(str(p), media_type=media_type)


@router.post("/videos/upload")
async def upload_video(file: UploadFile = File(...)) -> dict[str, str]:
    if not file.filename:
        raise HTTPException(status_code=400, detail="Missing filename")

    safe_name = Path(file.filename).name
    dest = (_videos_dir() / safe_name).resolve()

    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="Empty file")

    dest.write_bytes(data)
    return {
        "name": safe_name,
        "url": f"{settings.api_prefix}/projects/videos/{safe_name}",
        "absolute_path": str(dest),
    }

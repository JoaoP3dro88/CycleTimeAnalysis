"""Recebe uploads em streaming, respeitando o limite de tamanho."""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

from fastapi import HTTPException, UploadFile

from ..config import settings

_CHUNK = 1024 * 1024  # 1 MB


def max_video_bytes() -> int:
    return settings.max_video_mb * 1024 * 1024


def too_big_error() -> HTTPException:
    return HTTPException(
        status_code=413,
        detail=f"Arquivo maior que o limite de {settings.max_video_mb} MB.",
    )


async def save_upload_to_temp(file: UploadFile, dest_dir: Path | None = None) -> Path:
    """Grava o upload em arquivo temporário (sem carregar tudo na RAM).

    Levanta 413 se passar do limite. O chamador é responsável por apagar/mover
    o arquivo devolvido.
    """
    suffix = Path(file.filename or "").suffix or ".mp4"
    fd, tmp_name = tempfile.mkstemp(suffix=suffix, dir=str(dest_dir) if dest_dir else None)
    tmp = Path(tmp_name)
    total = 0
    limit = max_video_bytes()
    try:
        with os.fdopen(fd, "wb") as out:
            while True:
                chunk = await file.read(_CHUNK)
                if not chunk:
                    break
                total += len(chunk)
                if total > limit:
                    raise too_big_error()
                out.write(chunk)
        if total == 0:
            raise HTTPException(status_code=400, detail="Arquivo vazio.")
        return tmp
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise

from __future__ import annotations

import asyncio
import traceback
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import JSONResponse

from ...config import settings
from ...services.preprocess_service import (
    VideoTooLongError,
    VideoUnreadableError,
    preprocess_video,
    probe_video,
)
from ...services.upload_service import save_upload_to_temp
from ...services.user_service import normalize_user_id

router = APIRouter(prefix="/users/{user_id}/preprocess", tags=["preprocess"])

# Limita quantos vídeos são processados ao mesmo tempo (MediaPipe é pesado em
# CPU). Os demais usuários esperam na fila, em vez de derrubar o servidor.
_slots: asyncio.Semaphore | None = None


def _get_slots() -> asyncio.Semaphore:
    global _slots
    if _slots is None:
        _slots = asyncio.Semaphore(max(1, settings.max_concurrent_preprocess))
    return _slots


@router.post("")
async def preprocess(user_id: str, file: UploadFile = File(...)) -> JSONResponse:
    """
    Recebe um vídeo, processa todos os frames com MediaPipe e devolve o JSON
    de landmarks por frame. Respeita o limite de tamanho e de duração e a
    fila de processamento simultâneo.
    """
    normalize_user_id(user_id)  # valida o ID (400 se inválido)
    if not file.filename:
        raise HTTPException(status_code=400, detail="Arquivo sem nome")

    tmp = await save_upload_to_temp(file)   # 413 se passar do limite de MB
    try:
        try:
            await asyncio.to_thread(probe_video, str(tmp))
        except VideoTooLongError as e:
            raise HTTPException(status_code=413, detail=str(e))
        except VideoUnreadableError as e:
            raise HTTPException(status_code=422, detail=str(e))

        async with _get_slots():
            try:
                result = await asyncio.to_thread(preprocess_video, str(tmp))
            except VideoTooLongError as e:
                raise HTTPException(status_code=413, detail=str(e))
            except Exception as e:
                tb = traceback.format_exc()
                raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {e}\n\n{tb}")
    finally:
        Path(tmp).unlink(missing_ok=True)

    return JSONResponse(content=result)

from __future__ import annotations

import asyncio
import tempfile
import traceback
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import JSONResponse

from ...services.preprocess_service import preprocess_video

router = APIRouter(prefix="/preprocess", tags=["preprocess"])


@router.post("")
async def preprocess(file: UploadFile = File(...)) -> JSONResponse:
    """
    Recebe um vídeo, processa todos os frames com MediaPipe (mp.solutions.hands)
    e devolve o JSON com os landmarks indexados por número de frame.

    Roda em thread separada (asyncio.to_thread) para não bloquear o event loop
    do uvicorn durante o processamento — permite que heartbeat e outras
    requisições continuem sendo atendidas enquanto o vídeo é processado.
    """
    if not file.filename:
        raise HTTPException(status_code=400, detail="Arquivo sem nome")

    suffix = Path(file.filename).suffix or ".mp4"

    # Salva em arquivo temporário (cv2 não lê de memória)
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(await file.read())
        tmp_path = tmp.name

    try:
        # asyncio.to_thread → roda o subprocess em thread separada,
        # liberando o event loop para responder heartbeat durante o processamento
        result = await asyncio.to_thread(preprocess_video, tmp_path)
    except Exception as e:
        tb = traceback.format_exc()
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {e}\n\n{tb}")
    finally:
        Path(tmp_path).unlink(missing_ok=True)

    return JSONResponse(content=result)

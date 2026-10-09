"""Workspaces por usuário.

Cada usuário é identificado por um ID (UUID gerado pelo navegador, ou um ID
escolhido por ele). Tudo que é dele fica isolado em:

    <data_dir>/users/u_<id>/project.json
    <data_dir>/users/u_<id>/videos/

O ID funciona como "chave de acesso": quem souber o ID acessa o workspace.
Não há autenticação — adequado para rede interna.
"""
from __future__ import annotations

import re
import threading
from pathlib import Path

from fastapi import HTTPException

from ..config import settings

# 4–64 caracteres, começando com letra/número. Sem barras, pontos ou espaços
# (evita path traversal).
_USER_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{3,63}$")


def normalize_user_id(user_id: str) -> str:
    """Valida e devolve o ID canônico (minúsculo — NTFS ignora maiúsculas)."""
    if not _USER_ID_RE.fullmatch(user_id or ""):
        raise HTTPException(
            status_code=400,
            detail="ID de usuário inválido (use 4 a 64 letras, números, '-' ou '_').",
        )
    return user_id.lower()


def user_dir(user_id: str) -> Path:
    # Prefixo "u_" evita nomes reservados do Windows (con, nul, com1...).
    d = Path(settings.data_dir) / settings.users_dirname / f"u_{normalize_user_id(user_id)}"
    d.mkdir(parents=True, exist_ok=True)
    return d


def user_videos_dir(user_id: str) -> Path:
    d = user_dir(user_id) / settings.videos_dirname
    d.mkdir(parents=True, exist_ok=True)
    return d


# Um lock por usuário: evita leitura/escrita simultânea do mesmo project.json
_locks: dict[str, threading.Lock] = {}
_locks_guard = threading.Lock()


def user_lock(user_id: str) -> threading.Lock:
    uid = normalize_user_id(user_id)
    with _locks_guard:
        return _locks.setdefault(uid, threading.Lock())

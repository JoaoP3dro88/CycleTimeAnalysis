from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from ..models.schemas import Project
from .user_service import user_dir, user_lock


def project_path(user_id: str) -> Path:
    return user_dir(user_id) / "project.json"


def load_project(user_id: str) -> Project:
    path = project_path(user_id)
    with user_lock(user_id):
        if not path.exists():
            return Project()
        raw = json.loads(path.read_text(encoding="utf-8"))
    return Project.model_validate(raw)


def save_project(user_id: str, project: Project) -> None:
    path = project_path(user_id)
    payload = json.dumps(project.model_dump(mode="json"), indent=2, ensure_ascii=False)
    with user_lock(user_id):
        # Escrita atômica: grava em arquivo temporário e troca — nunca deixa
        # um project.json pela metade se o processo for interrompido.
        fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(payload)
            os.replace(tmp, path)
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)

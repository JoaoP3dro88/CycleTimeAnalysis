from __future__ import annotations

import json
from pathlib import Path

from ..models.schemas import Project


def ensure_data_dir(data_dir: str) -> Path:
    p = Path(data_dir)
    p.mkdir(parents=True, exist_ok=True)
    return p


def project_path(data_dir: str) -> Path:
    return ensure_data_dir(data_dir) / "project.json"


def load_project(data_dir: str) -> Project:
    path = project_path(data_dir)
    if not path.exists():
        return Project()

    raw = json.loads(path.read_text(encoding="utf-8"))
    return Project.model_validate(raw)


def save_project(data_dir: str, project: Project) -> None:
    path = project_path(data_dir)
    path.write_text(
        json.dumps(project.model_dump(mode="json"), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

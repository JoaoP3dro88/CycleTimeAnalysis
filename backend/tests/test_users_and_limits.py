"""Testes: workspaces por usuário, limite de duração (10 min) e de tamanho."""
from __future__ import annotations

import importlib
import os
import sys

import pytest

cv2 = pytest.importorskip("cv2")
np = pytest.importorskip("numpy")
from fastapi.testclient import TestClient  # noqa: E402

UID_A = "aaaa1111-0000-4000-8000-000000000001"
UID_B = "bbbb2222-0000-4000-8000-000000000002"


def _make_video(path, seconds: float, fps: int = 10) -> None:
    w = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), fps, (64, 48))
    frame = np.zeros((48, 64, 3), dtype=np.uint8)
    for _ in range(int(seconds * fps)):
        w.write(frame)
    w.release()


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("CTA_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("CTA_MAX_VIDEO_SECONDS", "5")     # limite curto p/ teste
    monkeypatch.setenv("CTA_MAX_VIDEO_MB", "1")
    for m in [m for m in sys.modules if m == "backend" or m.startswith("backend.")]:
        del sys.modules[m]
    main = importlib.import_module("backend.main")
    return TestClient(main.app)


def _project(takt):
    return {"meta": {"fps": 30, "total_frames": 0, "takt_time": takt}, "events": []}


def test_projects_are_isolated_per_user(client):
    assert client.post(f"/api/users/{UID_A}/projects/import", json=_project(11)).status_code == 200
    assert client.post(f"/api/users/{UID_B}/projects/import", json=_project(22)).status_code == 200
    a = client.get(f"/api/users/{UID_A}/projects/current").json()
    b = client.get(f"/api/users/{UID_B}/projects/current").json()
    assert a["meta"]["takt_time"] == 11
    assert b["meta"]["takt_time"] == 22


@pytest.mark.parametrize("bad", ["a", "..", "con", "a b c d", "x" * 80, "..%2f..%2fx"])
def test_invalid_user_id_rejected(client, bad):
    r = client.get(f"/api/users/{bad}/projects/current")
    assert r.status_code in (400, 404, 422)


def test_user_id_is_case_insensitive(client):
    client.post(f"/api/users/{UID_A.upper()}/projects/import", json=_project(33))
    assert client.get(f"/api/users/{UID_A}/projects/current").json()["meta"]["takt_time"] == 33


def test_upload_short_video_ok_and_isolated(client, tmp_path):
    v = tmp_path / "ok.mp4"
    _make_video(v, seconds=2)
    with open(v, "rb") as f:
        r = client.post(f"/api/users/{UID_A}/projects/videos/upload", files={"file": ("ok.mp4", f, "video/mp4")})
    assert r.status_code == 200, r.text
    assert r.json()["url"] == f"/api/users/{UID_A}/projects/videos/ok.mp4"

    assert [x["name"] for x in client.get(f"/api/users/{UID_A}/projects/videos").json()] == ["ok.mp4"]
    assert client.get(f"/api/users/{UID_B}/projects/videos").json() == []
    assert client.get(f"/api/users/{UID_A}/projects/videos/ok.mp4").status_code == 200
    assert client.get(f"/api/users/{UID_B}/projects/videos/ok.mp4").status_code == 404


def test_upload_too_long_rejected(client, tmp_path):
    v = tmp_path / "long.mp4"
    _make_video(v, seconds=8)                      # > 5 s do limite de teste
    with open(v, "rb") as f:
        r = client.post(f"/api/users/{UID_A}/projects/videos/upload", files={"file": ("long.mp4", f, "video/mp4")})
    assert r.status_code == 413
    assert "limite" in r.json()["detail"]
    assert client.get(f"/api/users/{UID_A}/projects/videos").json() == []   # nada ficou salvo


def test_upload_too_big_rejected(client):
    r = client.post(
        f"/api/users/{UID_A}/projects/videos/upload",
        files={"file": ("big.mp4", b"\0" * (3 * 1024 * 1024), "video/mp4")},
    )
    assert r.status_code == 413


def test_upload_garbage_rejected(client):
    r = client.post(
        f"/api/users/{UID_A}/projects/videos/upload",
        files={"file": ("x.mp4", b"not a video", "video/mp4")},
    )
    assert r.status_code == 422


def test_preprocess_too_long_rejected_before_processing(client, tmp_path):
    v = tmp_path / "long.mp4"
    _make_video(v, seconds=8)
    with open(v, "rb") as f:
        r = client.post(f"/api/users/{UID_A}/preprocess", files={"file": ("long.mp4", f, "video/mp4")})
    assert r.status_code == 413


def test_path_traversal_blocked(client):
    r = client.get(f"/api/users/{UID_A}/projects/videos/..%2f..%2fproject.json")
    assert r.status_code in (400, 404)

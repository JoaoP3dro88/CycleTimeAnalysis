# Backend (FastAPI)

This folder contains the Python backend API that powers the Cycle Time Analysis web app.

## What you get

- FastAPI app with CORS enabled for the Vite dev server (and `--cors-origins` in production)
- **Multi-user workspaces**: every route is scoped by a user ID — data lives in
  `data/users/u_<id>/project.json` and `data/users/u_<id>/videos/`
- **Video limits**: max duration (default 10 min) and max size (default 2048 MB)
- Endpoints (`{user_id}` = 4–64 chars `A-Z a-z 0-9 _ -`, case-insensitive):
  - `GET  /health`
  - `GET  /api/users/{user_id}/projects/current`
  - `POST /api/users/{user_id}/projects/import`
  - `GET  /api/users/{user_id}/projects/export`
  - `POST /api/users/{user_id}/projects/reset`
  - `GET  /api/users/{user_id}/analytics/current`
  - `POST /api/users/{user_id}/projects/videos/upload` (multipart; 413 if too long/big, 422 if unreadable)
  - `GET  /api/users/{user_id}/projects/videos` (list)
  - `GET  /api/users/{user_id}/projects/videos/{filename}` (stream)
  - `POST /api/users/{user_id}/preprocess` (MediaPipe; queued, max N at once)

## Limits (settings)

| Setting | CLI flag (`run.py`) | Env var | Default |
|---|---|---|---|
| Max video duration (s) | `--max-video-seconds` | `CTA_MAX_VIDEO_SECONDS` | 600 (10 min) |
| Max video size (MB) | `--max-video-mb` | `CTA_MAX_VIDEO_MB` | 2048 |
| Simultaneous preprocess jobs | `--max-concurrent-preprocess` | `CTA_MAX_CONCURRENT_PREPROCESS` | 2 |

Keep `VITE_MAX_VIDEO_SECONDS` (frontend/.env.production) equal to the backend duration limit.

## Run (Windows PowerShell)

Create a virtual env, install dependencies and run the server.

```powershell
cd c:\Users\klj1ct\Desktop\CycleTimeAnalysis\backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000
```

Open:

- API docs: http://127.0.0.1:8000/docs
- Health check: http://127.0.0.1:8000/health

## Tests

```powershell
pytest backend/tests -q
```

## About video persistence

Browsers can't reliably reopen a local video file path after refresh (security model).
This backend supports a "workspace library":

- When you upload a video, it's copied to the user's own folder `data/users/u_<id>/videos/`
- The frontend can then reload the same video by URL across sessions

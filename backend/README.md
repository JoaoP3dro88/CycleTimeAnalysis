# Backend (FastAPI)

This folder contains the Python backend API that powers the Cycle Time Analysis web app.

## What you get

- FastAPI app with CORS enabled for the Vite dev server
- Simple JSON persistence to `backend/data/project.json`
- Endpoints:
  - `GET /health`
  - `GET /api/projects/current`
  - `POST /api/projects/import`
  - `GET /api/projects/export`
  - `GET /api/analytics/current`
  - Video persistence (solution B):
    - `POST /api/projects/videos/upload` (multipart form-data)
    - `GET /api/projects/videos` (list)
    - `GET /api/projects/videos/{filename}` (download/stream)

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

## About video persistence

Browsers can't reliably reopen a local video file path after refresh (security model).
This backend supports a "workspace library":

- When you upload a video, it's copied to `backend/data/videos/`
- The frontend can then reload the same video by URL across sessions

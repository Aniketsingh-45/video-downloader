# MySaver — Video Downloader

MySaver is a FastAPI + yt-dlp downloader for public YouTube, Instagram, and Facebook videos, with a beautiful animated frontend and live download progress.

The backend serves both the API **and** the frontend (`index.html`), so you normally only need one command.

---

## 1. Backend (API + serves the frontend)

```powershell
# from this folder
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn main:app --reload
```

- App: http://localhost:8000
- API docs: http://localhost:8000/docs

> If PowerShell blocks the venv activation, run this first in the same terminal:
> `Set-ExecutionPolicy -Scope Process Bypass`

## 2. Frontend (optional, separated)

The frontend is a single `index.html` with zero build step — FastAPI already serves it. But if you want to open it as a standalone site (e.g. in VS Code Live Server) while the backend runs separately:

```powershell
python -m http.server 5500
```

then open http://localhost:5500. The page auto-connects to the API at the same origin; when served from a different port, change `API_BASE` at the top of the `<script>` in `index.html` to `http://localhost:8000`.

---

## 3. API endpoints

| Method | Path                     | Body                          | Purpose                             |
| ------ | ------------------------ | ----------------------------- | ----------------------------------- |
| POST   | `/api/info`              | `{ "url": "..." }`            | Title, thumbnail, duration, sizes   |
| POST   | `/api/download`          | `{ "url": "...", "quality": "best" }` | Starts download, returns `task_id` |
| GET    | `/api/progress/{task_id}`| —                             | Poll live progress (%)              |
| GET    | `/api/file/{task_id}`    | —                             | Download the finished file          |

Quality values: `best`, `720p`, `480p`, `audio`.

---

## 4. Deploy

Deploy the whole folder as one service on Railway, Render, or any Python host. Start command:

```bash
uvicorn main:app --host 0.0.0.0 --port $PORT
```

The UI and API share one domain, so no frontend API configuration is needed.

---

## Notes

- Some formats require [FFmpeg](https://ffmpeg.org/download.html) on your system `PATH` so video + audio can be merged.
- Playlists are intentionally disabled (`noplaylist`); single videos only.
- Private, login-protected, or restricted content is not supported.
- Only download content you own or have permission to use. Server files are deleted 5 minutes after download.

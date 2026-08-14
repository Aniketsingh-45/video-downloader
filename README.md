<div align="center">
  <img src="https://raw.githubusercontent.com/Aniketsingh-45/video-downloader/main/logo.jpg" alt="MySaver Logo" width="120" style="border-radius: 24px; box-shadow: 0 0 20px rgba(132, 61, 255, 0.4);" onerror="this.src='https://placehold.co/120x120/030108/843dff?text=MS&font=Montserrat'">
  
  # ✨ MySaver ✨
  
  **Premium Video & Audio Downloader**
  
  [![FastAPI](https://img.shields.io/badge/FastAPI-009688?style=for-the-badge&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
  [![yt-dlp](https://img.shields.io/badge/yt--dlp-FF0000?style=for-the-badge&logo=youtube&logoColor=white)](https://github.com/yt-dlp/yt-dlp)
  [![Python](https://img.shields.io/badge/Python-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
</div>

<br/>

MySaver is a **FastAPI + yt-dlp** powered downloader for public YouTube, Instagram, and Facebook videos. It features a beautiful, animated, and responsive glassmorphism frontend with live download progress. 

The backend elegantly serves both the REST API and the frontend (`index.html`), streamlining your workflow.

---

## 🚀 Quick Start (Backend + Frontend)

The fastest way to get up and running:

```powershell
# 1. Create and activate a virtual environment
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# 2. Install dependencies
pip install -r requirements.txt

# 3. Start the server
uvicorn main:app --reload
```

> **Note for Windows Users:** If PowerShell blocks the venv activation, run this first:  
> `Set-ExecutionPolicy -Scope Process Bypass`

🌟 **Open your browser:**
- **App:** [http://localhost:8000](http://localhost:8000)
- **API Docs:** [http://localhost:8000/docs](http://localhost:8000/docs)

---

## 🎨 Standalone Frontend (Optional)

The frontend is a pristine, zero-build-step `index.html`. While FastAPI serves it perfectly, you can run it via VS Code Live Server or Python's HTTP server:

```powershell
python -m http.server 5500
```

> **Tip:** If serving on a different port than the backend, remember to update `API_BASE` in the `<script>` tag inside `index.html` to point to your backend (e.g., `http://localhost:8000`).

---

## 🔌 API Reference

| Method | Endpoint | Payload | Description |
| :--- | :--- | :--- | :--- |
| **`POST`** | `/api/info` | `{ "url": "..." }` | Fetch media metadata (title, thumbnail, duration, available sizes). |
| **`POST`** | `/api/download` | `{ "url": "...", "quality": "best" }` | Initiate download. Returns a unique `task_id`. |
| **`GET`** | `/api/progress/{task_id}` | — | Poll for real-time download progress (%). |
| **`GET`** | `/api/file/{task_id}` | — | Retrieve the final downloaded file. |

**Available Qualities:** `best`, `4k`, `1440p`, `1080p`, `720p`, `480p`, `360p`, `240p`, `144p`, `audio`.

---

## ☁️ Deployment

Deploy effortlessly to platforms like Railway, Render, or Heroku. Use this start command:

```bash
uvicorn main:app --host 0.0.0.0 --port $PORT
```

*Because the UI and API share a single domain, no complex CORS or frontend configuration is needed!*

---

## ⚠️ Important Notes

- **FFmpeg:** Some high-quality formats require [FFmpeg](https://ffmpeg.org/download.html) to be installed and added to your system `PATH` to merge video and audio streams.
- **Playlists:** Currently disabled (`noplaylist`). Designed for single videos.
- **Privacy:** Private, login-protected, or geo-restricted content cannot be downloaded.
- **Responsibility:** Only download content you own or have explicit permission to use. Server files are automatically cleared 5 minutes post-download.

---

<div align="center">
  <p>Crafted with ❤️ by <b>Aniket Singh</b></p>
</div>

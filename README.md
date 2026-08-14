<div align="center">
  <img src="https://raw.githubusercontent.com/Aniketsingh-45/video-downloader/main/logo.jpg" alt="MySaver Logo" width="120" style="border-radius: 24px; box-shadow: 0 0 20px rgba(132, 61, 255, 0.4);" onerror="this.src='https://placehold.co/120x120/030108/843dff?text=MS&font=Montserrat'">
  
  # ✨ MySaver ✨
  
  **All-In-One Media Downloader — Videos, Photos & Posts**
  
  [![FastAPI](https://img.shields.io/badge/FastAPI-009688?style=for-the-badge&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
  [![yt-dlp](https://img.shields.io/badge/yt--dlp-FF0000?style=for-the-badge&logo=youtube&logoColor=white)](https://github.com/yt-dlp/yt-dlp)
  [![Python](https://img.shields.io/badge/Python-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
</div>

<br/>

MySaver is a **FastAPI + yt-dlp** powered all-in-one media downloader. Download **videos, photos, reels, carousels, and posts** from YouTube, Instagram, and Facebook — all from a single, beautiful, glassmorphism UI with live progress tracking.

### 🎯 Key Features
- 🎬 **Video Downloads** — From 144p to 4K Ultra HD
- 📷 **Photo & Post Downloads** — Single images and carousel/multi-photo posts
- 🎵 **Audio Extraction** — Extract MP3 audio from any video
- 📦 **Carousel/Multi-Photo ZIP** — Download all photos from a post at once
- ⚡ **Individual Item Downloads** — Pick specific items from a carousel
- 🎨 **Premium Animated UI** — Glassmorphism, gradient animations, confetti effects

---

## 🚀 Quick Start

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

## 🔌 API Reference

| Method | Endpoint | Payload | Description |
| :--- | :--- | :--- | :--- |
| **`POST`** | `/api/info` | `{ "url": "..." }` | Fetch media metadata (title, thumbnail, duration, available sizes, media type). |
| **`POST`** | `/api/download` | `{ "url": "...", "quality": "best", "playlist_item": null }` | Initiate download. Set `playlist_item` (1-indexed) for individual carousel items. Returns `task_id`. |
| **`GET`** | `/api/progress/{task_id}` | — | Poll for real-time download progress (%). |
| **`GET`** | `/api/file/{task_id}` | — | Retrieve the final downloaded file. |

**Available Qualities:** `best`, `4k`, `1440p`, `1080p`, `720p`, `480p`, `360p`, `240p`, `144p`, `audio`, `photo`, `zip`.

---

## ☁️ Deployment

Deploy effortlessly to platforms like Railway, Render, or Heroku:

```bash
uvicorn main:app --host 0.0.0.0 --port $PORT
```

*The UI and API share a single domain — no CORS or frontend configuration needed!*

---

## ⚠️ Important Notes

- **FFmpeg:** Required for merging video+audio streams and MP3 extraction. Install from [ffmpeg.org](https://ffmpeg.org/download.html) and add to `PATH`.
- **Instagram:** Only public posts can be downloaded. Private/login-required content is not supported.
- **Responsibility:** Only download content you own or have permission to use.
- **Cleanup:** Server files are automatically deleted 5 minutes after download.

---

<div align="center">
  <p>Crafted with ❤️ by <b>Aniket Singh</b></p>
</div>

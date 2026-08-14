<div align="center">
  <img src="https://raw.githubusercontent.com/Aniketsingh-45/video-downloader/main/logo.jpg" alt="MySaver Logo" width="140" style="border-radius: 28px; box-shadow: 0 0 30px rgba(132, 61, 255, 0.4);" onerror="this.src='https://placehold.co/140x140/030108/843dff?text=MS&font=Montserrat'">
  
  <br/>
  
  <h1>✨ MySaver ✨</h1>
  
  <p><b>The Ultimate All-In-One Media Downloader</b><br/>Videos, Photos, Reels, and Carousels with Zero Quality Loss.</p>
  
  [![FastAPI](https://img.shields.io/badge/FastAPI-009688?style=for-the-badge&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
  [![Python](https://img.shields.io/badge/Python-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
  [![yt-dlp](https://img.shields.io/badge/yt--dlp-FF0000?style=for-the-badge&logo=youtube&logoColor=white)](https://github.com/yt-dlp/yt-dlp)
  [![License](https://img.shields.io/badge/License-MIT-blue.svg?style=for-the-badge)](#)
</div>

<br/>

**MySaver** is a premium, open-source media downloader built with a highly optimized FastAPI backend and a stunning glassmorphism frontend. It intelligently parses any link you throw at it and allows you to download videos up to 4K, extract MP3 audio, download single photos, or effortlessly grab entire Instagram multi-photo carousels in a single ZIP file.

---

## 🌟 Key Features

- 🎬 **Universal Video Download:** Fetch videos from YouTube, Instagram, Facebook, and hundreds of other sites in qualities ranging from 144p to 4K.
- 📸 **Smart Photo & Post Handling:** Specifically engineered to download high-resolution photos and reels that typical video downloaders fail on.
- 📦 **Carousel ZIP Downloads:** Paste an Instagram post with multiple photos, and instantly download them all together in one convenient `.zip` file, or pick them individually.
- 🎵 **Audio Extraction:** Convert any video directly to a high-quality MP3 file automatically.
- 🎨 **Premium UI/UX:** A responsive, dark-mode frontend featuring floating fluid blobs, glassmorphism cards, and live download progress tracking.
- ⚡ **Lightning Fast Backend:** Built with asynchronous FastAPI, multi-threading, and custom `yt-dlp` loggers for a completely silent, fast backend terminal experience.

---

## 📱 Supported Platforms

While MySaver supports hundreds of sites via `yt-dlp`, it is heavily optimized for:
| Platform | Supported Media |
| :--- | :--- |
| **YouTube** | Videos (up to 4K), Shorts, Audio |
| **Instagram** | Reels, Single Photos, Multi-Photo Carousels |
| **Facebook** | Public Videos, Posts |
| **Twitter / X** | Videos and GIFs |
| **TikTok** | Videos |

> **Note:** Only public posts can be downloaded. Private content requiring login credentials is not supported.

---

## 🚀 Quick Start

### 1. Prerequisites
- **Python 3.8+**
- **FFmpeg** (Required for merging video/audio and MP3 extraction. Download from [ffmpeg.org](https://ffmpeg.org/download.html) and add it to your system `PATH`).

### 2. Installation

Clone the repository and set up a virtual environment:

```powershell
# Create and activate virtual environment
python -m venv .venv
.\.venv\Scripts\Activate.ps1   # (Windows)
# source .venv/bin/activate    # (Mac/Linux)

# Install required packages
pip install -r requirements.txt
```

### 3. Run the Server

```powershell
uvicorn main:app --reload
```

🌟 **Open your browser:**
- **Web App:** [http://localhost:8000](http://localhost:8000)
- **API Documentation:** [http://localhost:8000/docs](http://localhost:8000/docs)

---

## 🔌 API Reference

MySaver exposes a clean REST API if you want to integrate it into your own apps.

#### `POST /api/info`
Analyzes a URL and returns available formats, titles, thumbnails, and media types.
```json
{
  "url": "https://instagram.com/p/..."
}
```

#### `POST /api/download`
Starts a download task in the background.
```json
{
  "url": "https://instagram.com/p/...",
  "quality": "zip", 
  "playlist_item": null
}
```
*Valid qualities:* `best`, `4k`, `1080p`, `720p`, `audio`, `photo`, `zip`.

#### `GET /api/progress/{task_id}`
Polls the real-time download progress (returns 0-100%).

#### `GET /api/file/{task_id}`
Serves the final downloaded file (automatically deletes from the server after download).

---

## ☁️ Deployment

MySaver combines the frontend and backend into a single ASGI app, meaning **no CORS configuration is required**. You can easily deploy this to Railway, Render, or Heroku with a single command:

```bash
uvicorn main:app --host 0.0.0.0 --port $PORT
```

---

<div align="center">
  <p>Crafted with ❤️ by <b>Aniket Singh</b></p>
</div>

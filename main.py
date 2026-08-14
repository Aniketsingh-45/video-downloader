import os
import re
import threading
import tempfile
import time
import shutil
import uuid

import yt_dlp
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

app = FastAPI(title="MySaver API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DOWNLOAD_DIR = os.path.join(tempfile.gettempdir(), "mysaver_downloads")
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

# In-memory download tasks: {task_id: {...}}
TASKS: dict = {}
TASKS_LOCK = threading.Lock()

AUTO_CLEANUP_SECONDS = 300  # files are deleted 5 minutes after download


class VideoRequest(BaseModel):
    url: str
    quality: str = "best"  # best | 720p | 480p | audio


def validate_url(url: str) -> str:
    url = url.strip()
    if not url.startswith(("http://", "https://")):
        raise HTTPException(
            status_code=422,
            detail="Please enter a valid URL starting with http:// or https://",
        )
    return url


def _register_task(task_id: str) -> None:
    with TASKS_LOCK:
        TASKS[task_id] = {
            "status": "started",
            "percent": 0,
            "message": "Starting…",
            "filename": None,
            "error": None,
            "filepath": None,
            "created": time.time(),
        }


def _update_task(task_id: str, **fields) -> None:
    with TASKS_LOCK:
        task = TASKS.get(task_id)
        if task:
            task.update(fields)


def _cleanup_task(task_id: str) -> None:
    with TASKS_LOCK:
        TASKS.pop(task_id, None)


def auto_delete_file(path: str, task_id: str, delay: int = AUTO_CLEANUP_SECONDS) -> None:
    """Delete a downloaded file (and its task) after a delay to keep the server clean."""
    def _delete():
        time.sleep(delay)
        try:
            if os.path.exists(path):
                os.remove(path)
        except Exception:
            pass
        _cleanup_task(task_id)

    threading.Thread(target=_delete, daemon=True).start()


# ---------------------------------------------------------------- sizing ----

def estimate_sizes(formats, info):
    sizes = {"4k": None, "1440p": None, "1080p": None, "best": None, "720p": None, "480p": None, "360p": None, "240p": None, "144p": None, "audio": None}
    
    def to_mb(n):
        return f"{n / (1024 * 1024):.1f} MB" if n > 0 else None

    def get_size(f):
        if not f:
            return 0
        return f.get("filesize") or f.get("filesize_approx") or 0

    video_formats = [f for f in formats if f.get("vcodec") not in ("none", None)]
    audio_formats = [f for f in formats if f.get("acodec") not in ("none", None)]
    
    ext = info.get("ext", "").lower()
    
    if not video_formats and not audio_formats:
        if ext in ("jpg", "jpeg", "png", "webp", "gif") or not formats:
            sizes["photo"] = to_mb(info.get("filesize") or 0)
            return sizes

    if not formats:
        return sizes

    best_audio = audio_formats[-1] if audio_formats else None
    audio_size = get_size(best_audio)
    if audio_size > 0:
        sizes["audio"] = to_mb(audio_size)

    def best_video(max_height=None):
        pool = video_formats
        if max_height:
            pool = [f for f in pool if f.get("height") and f.get("height") <= max_height]
        return pool[-1] if pool else None

    def calc(vid):
        if not vid:
            return None
        vid_size = get_size(vid)
        has_audio = vid.get("acodec") not in ("none", None)
        total = vid_size + (0 if has_audio else audio_size)
        return to_mb(total) if total > 0 else None

    sizes["4k"] = calc(best_video(2160))
    sizes["1440p"] = calc(best_video(1440))
    sizes["1080p"] = calc(best_video(1080))
    sizes["best"] = calc(best_video())
    sizes["720p"] = calc(best_video(720))
    sizes["480p"] = calc(best_video(480))
    sizes["360p"] = calc(best_video(360))
    sizes["240p"] = calc(best_video(240))
    sizes["144p"] = calc(best_video(144))
    return sizes


def get_format_string(quality: str) -> str:
    formats = {
        "4k": "bestvideo[height<=2160][ext=mp4]+bestaudio[ext=m4a]/best[height<=2160][ext=mp4]/best",
        "1440p": "bestvideo[height<=1440][ext=mp4]+bestaudio[ext=m4a]/best[height<=1440][ext=mp4]",
        "1080p": "bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/best[height<=1080][ext=mp4]",
        "best": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
        "720p": "bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/best[height<=720][ext=mp4]",
        "480p": "bestvideo[height<=480][ext=mp4]+bestaudio[ext=m4a]/best[height<=480][ext=mp4]",
        "360p": "bestvideo[height<=360][ext=mp4]+bestaudio[ext=m4a]/best[height<=360][ext=mp4]",
        "240p": "bestvideo[height<=240][ext=mp4]+bestaudio[ext=m4a]/best[height<=240][ext=mp4]",
        "144p": "bestvideo[height<=144][ext=mp4]+bestaudio[ext=m4a]/best[height<=144][ext=mp4]",
        "audio": "bestaudio[ext=m4a]/bestaudio",
    }
    return formats.get(quality, formats["best"])


def friendly_error(message: str) -> str:
    if "Unsupported URL" in message:
        return "That link is not supported. Try YouTube, Instagram, or Facebook."
    if "Video unavailable" in message or "Private video" in message:
        return "That video is unavailable or private."
    if "Sign in" in message or "login" in message.lower():
        return "This content needs a login. Only public videos can be saved."
    return "Something went wrong. Check the link and try again."


# ---------------------------------------------------------------- info ------

@app.post("/api/info")
async def get_video_info(request: VideoRequest):
    """Fetch title, thumbnail, duration and available sizes for a link."""
    try:
        url = validate_url(request.url)
        opts = {
            "quiet": True,
            "no_warnings": True,
            "extract_flat": "in_playlist",
            "playlistend": 50,
            "ignoreerrors": True,
            "ignore_no_formats_error": True,
            "extractor_args": {"youtube": ["player_client=android", "player_client=web"]},
        }
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
            platform = (
                info.get("extractor_key")
                or info.get("extractor")
                or ""
            ).upper()
            
            title = info.get("title") or "Untitled video"
            
            if info.get("_type") == "playlist":
                entries = list(info.get("entries") or [])
                sizes = {"zip": f"{len(entries)} items"}
                thumbnail = ""
                if entries and isinstance(entries[0], dict):
                    thumbnail = entries[0].get("thumbnail") or ""
                return {
                    "title": title,
                    "thumbnail": thumbnail,
                    "duration": 0,
                    "uploader": info.get("uploader") or info.get("channel") or "",
                    "platform": platform,
                    "sizes": sizes,
                }

            formats = info.get("formats", [])
            return {
                "title": title,
                "thumbnail": info.get("thumbnail") or "",
                "duration": info.get("duration") or 0,
                "uploader": info.get("uploader") or info.get("channel") or "",
                "platform": platform,
                "sizes": estimate_sizes(formats, info),
            }
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=400, detail=str(exc)
        )


# ---------------------------------------------------------------- download --

def _download_worker(task_id: str, url: str, quality: str) -> None:
    def hook(d):
        if d.get("status") == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
            done = d.get("downloaded_bytes") or 0
            percent = min(int(done / total * 100), 99) if total else 0
            speed = d.get("_speed_str") or ""
            _update_task(task_id, percent=percent, message=f"Downloading… {percent}% {speed}")
        elif d.get("status") == "finished":
            _update_task(task_id, percent=100, message="Finalising file…")

    outtmpl_path = os.path.join(DOWNLOAD_DIR, f"{task_id}.%(ext)s")
    
    if quality == "zip":
        playlist_dir = os.path.join(DOWNLOAD_DIR, task_id)
        os.makedirs(playlist_dir, exist_ok=True)
        opts = {
            "outtmpl": os.path.join(playlist_dir, "%(title)s.%(ext)s"),
            "quiet": True,
            "no_warnings": True,
            "playlistend": 50,
            "noplaylist": False,
            "ignoreerrors": True,
            "ignore_no_formats_error": True,
            "writethumbnail": True,
            "extractor_args": {"youtube": ["player_client=android", "player_client=web"]},
            "progress_hooks": [hook],
        }
        
        try:
            _update_task(task_id, message="Starting download…")
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=True)
                
            _update_task(task_id, message="Creating ZIP file…")
            zip_path = os.path.join(DOWNLOAD_DIR, f"{task_id}.zip")
            shutil.make_archive(os.path.join(DOWNLOAD_DIR, task_id), 'zip', playlist_dir)
            
            title = (info.get("title") or "Playlist").strip()
            safe_title = re.sub(r"[^\w\s\-]", "", title).strip()[:50].strip()
            if not safe_title:
                safe_title = "playlist"
                
            _update_task(
                task_id,
                status="done",
                percent=100,
                message="Done!",
                filename=f"{safe_title}.zip",
                filepath=zip_path,
            )
            
            shutil.rmtree(playlist_dir, ignore_errors=True)
            auto_delete_file(zip_path, task_id)
            
        except Exception as exc:
            _update_task(task_id, status="error", error=friendly_error(str(exc)))
            shutil.rmtree(playlist_dir, ignore_errors=True)
            try:
                os.remove(os.path.join(DOWNLOAD_DIR, f"{task_id}.zip"))
            except:
                pass
        return

    if quality == "photo":
        ext = "jpg"
        opts = {
            "outtmpl": outtmpl_path,
            "format": "best",
            "quiet": True,
            "no_warnings": True,
            "noplaylist": True,
            "ignoreerrors": True,
            "ignore_no_formats_error": True,
            "writethumbnail": True,
            "extractor_args": {"youtube": ["player_client=android", "player_client=web"]},
            "progress_hooks": [hook],
        }
    elif quality == "audio":
        ext = "mp3"
        opts = {
            "outtmpl": outtmpl_path,
            "format": "bestaudio/best",
            "quiet": True,
            "no_warnings": True,
            "noplaylist": True,
            "extractor_args": {"youtube": ["player_client=android", "player_client=web"]},
            "progress_hooks": [hook],
            "postprocessors": [{
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "192",
            }]
        }
    else:
        ext = "mp4"
        opts = {
            "outtmpl": outtmpl_path,
            "format": get_format_string(quality),
            "quiet": True,
            "no_warnings": True,
            "merge_output_format": ext,
            "noplaylist": True,
            "concurrent_fragment_downloads": 10,
            "http_chunk_size": 10485760,
            "extractor_args": {"youtube": ["player_client=android", "player_client=web"]},
            "progress_hooks": [hook],
        }

    try:
        _update_task(task_id, message="Starting download…")
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
        info = info or {}

        output_path = None
        for f in os.listdir(DOWNLOAD_DIR):
            if f.startswith(task_id) and not f.endswith((".part", ".ytdl")):
                if not output_path or f.endswith(f".{ext}"):
                    output_path = os.path.join(DOWNLOAD_DIR, f)

        if not output_path or not os.path.isfile(output_path):
            if quality == "photo":
                image_url = None
                formats = info.get("formats") or []
                image_formats = [fmt for fmt in formats if fmt.get("vcodec") == "none" and fmt.get("acodec") == "none"]
                if image_formats:
                    image_url = image_formats[-1].get("url")
                if not image_url:
                    image_url = info.get("thumbnail") or info.get("url")
                if not image_url:
                    thumbnails = info.get("thumbnails") or []
                    if thumbnails:
                        image_url = thumbnails[-1].get("url")
                        
                if image_url:
                    import urllib.request
                    fallback_ext = image_url.split("?")[0].split(".")[-1]
                    if fallback_ext.lower() not in ("jpg", "jpeg", "png", "webp", "gif"):
                        fallback_ext = "jpg"
                    output_path = os.path.join(DOWNLOAD_DIR, f"{task_id}.{fallback_ext}")
                    req = urllib.request.Request(image_url, headers={'User-Agent': 'Mozilla/5.0'})
                    with urllib.request.urlopen(req) as response, open(output_path, 'wb') as out_file:
                        shutil.copyfileobj(response, out_file)
                else:
                    raise RuntimeError("The downloaded file could not be found.")
            else:
                raise RuntimeError("The downloaded file could not be found.")

        actual_ext = output_path.split(".")[-1]
        title = (info.get("title") or "video").strip()
        safe_title = re.sub(r"[^\w\s\-]", "", title).strip()[:50].strip()
        if not safe_title:
            safe_title = "video"
            
        filename = f"{safe_title}.{actual_ext}"

        _update_task(
            task_id,
            status="done",
            percent=100,
            message="Done!",
            filename=filename,
            filepath=output_path,
        )
        auto_delete_file(output_path, task_id)

    except Exception as exc:
        _update_task(task_id, status="error", error=friendly_error(str(exc)))
        try:
            for f in os.listdir(DOWNLOAD_DIR):
                if f.startswith(task_id):
                    os.remove(os.path.join(DOWNLOAD_DIR, f))
        except Exception:
            pass


@app.post("/api/download")
async def start_download(request: VideoRequest):
    """Start downloading in the background and return a task id to poll."""
    url = validate_url(request.url)
    task_id = uuid.uuid4().hex
    _register_task(task_id)
    threading.Thread(
        target=_download_worker, args=(task_id, url, request.quality), daemon=True
    ).start()
    return {"task_id": task_id}


@app.get("/api/progress/{task_id}")
async def get_progress(task_id: str):
    """Poll the status of a running download task."""
    with TASKS_LOCK:
        task = TASKS.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return {
        "status": task["status"],
        "percent": task["percent"],
        "message": task["message"],
        "filename": task["filename"],
        "error": task["error"],
    }


@app.get("/api/file/{task_id}")
async def get_file(task_id: str, background_tasks: BackgroundTasks):
    """Serve the finished file to the browser."""
    with TASKS_LOCK:
        task = TASKS.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    if task["status"] == "error":
        raise HTTPException(status_code=500, detail=task.get("error") or "Download failed")
    if not task.get("filepath") or not os.path.isfile(task["filepath"]):
        raise HTTPException(status_code=404, detail="File is not ready yet")

    def cleanup():
        try:
            if os.path.exists(task["filepath"]):
                os.remove(task["filepath"])
        except Exception:
            pass
        _cleanup_task(task_id)

    background_tasks.add_task(cleanup)
    media = "audio/mp4" if str(task["filename"]).endswith(".m4a") else "video/mp4"
    return FileResponse(
        task["filepath"], filename=task["filename"], media_type=media
    )


# Static frontend (index.html) is served from the same folder.
app.mount("/", StaticFiles(directory=BASE_DIR, html=True), name="frontend")

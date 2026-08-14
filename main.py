from typing import Optional
import os
import re
import threading
import tempfile
import time
import shutil
import uuid
import urllib.request

import yt_dlp
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

class QuietLogger:
    def debug(self, msg): pass
    def warning(self, msg): pass
    def error(self, msg): pass
    
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


class MediaRequest(BaseModel):
    url: str
    quality: str = "best"  # best | 720p | 480p | audio | photo | zip
    playlist_item: Optional[int] = None


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
            if os.path.isfile(path):
                os.remove(path)
            elif os.path.isdir(path):
                shutil.rmtree(path, ignore_errors=True)
        except Exception:
            pass
        _cleanup_task(task_id)

    threading.Thread(target=_delete, daemon=True).start()


# ---------------------------------------------------------------- helpers ---

def _has_video_formats(info: dict) -> bool:
    """Check if the info dict has any video formats."""
    for f in info.get("formats") or []:
        if f.get("vcodec") not in ("none", None):
            return True
    return False


def _detect_media_type(info: dict) -> str:
    """Return 'image', 'video', or 'audio' based on available formats."""
    formats = info.get("formats") or []
    ext = (info.get("ext") or "").lower()

    if _has_video_formats(info):
        return "video"
    has_audio = any(f.get("acodec") not in ("none", None) for f in formats)
    if has_audio:
        return "audio"
    if ext in ("jpg", "jpeg", "png", "webp", "gif", "bmp"):
        return "image"
    if not formats and (info.get("url") or info.get("thumbnail")):
        return "image"
    return "video"


def _get_best_image_url(info: dict) -> tuple:
    """
    Extract the best image URL from info dict.
    Returns (url, headers). Tries multiple strategies.
    """
    headers = info.get("http_headers") or {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }
    formats = info.get("formats") or []

    # Strategy 1: image-only formats (no audio, no video)
    image_fmts = [f for f in formats if f.get("vcodec") == "none" and f.get("acodec") == "none"]
    if image_fmts:
        fmt = image_fmts[-1]
        return fmt.get("url"), fmt.get("http_headers") or headers

    # Strategy 2: formats whose URL ends in an image extension
    for fmt in reversed(formats):
        u = (fmt.get("url") or "").split("?")[0].lower()
        if u.endswith((".jpg", ".jpeg", ".png", ".webp", ".gif")):
            return fmt["url"], fmt.get("http_headers") or headers

    # Strategy 3: direct URL on the info dict
    if info.get("url"):
        return info["url"], headers

    # Strategy 4: highest-resolution thumbnail
    thumbnails = info.get("thumbnails") or []
    if thumbnails:
        best = max(thumbnails, key=lambda t: (t.get("width") or 0) * (t.get("height") or 0))
        return best.get("url"), best.get("http_headers") or headers
    if info.get("thumbnail"):
        return info["thumbnail"], headers

    return None, headers


def _download_image_to_file(url: str, output_path: str, headers: dict = None) -> str:
    """Download an image from a URL. Returns the actual output path."""
    if not headers:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        }
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=30) as response:
        with open(output_path, 'wb') as out_file:
            shutil.copyfileobj(response, out_file)
    return output_path


# ---------------------------------------------------------------- sizing ----

def estimate_sizes(formats, info):
    sizes = {}

    def to_mb(n):
        return f"{n / (1024 * 1024):.1f} MB" if n > 0 else None

    def get_size(f):
        return f.get("filesize") or f.get("filesize_approx") or 0 if f else 0

    media_type = _detect_media_type(info)

    if media_type == "image":
        sizes["photo"] = to_mb(info.get("filesize") or 0) or "Image"
        return sizes

    video_formats = [f for f in formats if f.get("vcodec") not in ("none", None)]
    audio_formats = [f for f in formats if f.get("acodec") not in ("none", None)]

    if not formats:
        sizes["photo"] = "Image"
        return sizes

    best_audio = audio_formats[-1] if audio_formats else None
    audio_size = get_size(best_audio)
    if audio_size > 0:
        sizes["audio"] = to_mb(audio_size)

    if not video_formats:
        if not audio_formats:
            sizes["photo"] = "Image"
        return sizes

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
    print(f"[MySaver ERROR] {message}")
    msg = str(message)
    if "Unsupported URL" in msg:
        return "That link is not supported. Try YouTube, Instagram, or Facebook."
    if "Video unavailable" in msg or "Private video" in msg:
        return "That content is unavailable or private."
    if "Sign in" in msg or "login" in msg.lower() or "cookies" in msg.lower():
        return "This content requires login. Only public posts can be downloaded."
    if "HTTP Error 403" in msg or "403" in msg:
        return "Access denied. The content may be private or require login."
    if "HTTP Error 404" in msg or "404" in msg:
        return "Content not found. The link may have been removed."
    if "empty media response" in msg.lower():
        return "This content requires login. Only public posts can be downloaded."
    if "No video formats" in msg or "Requested format" in msg:
        return "No downloadable format found for this content."
    return f"Download error: {msg[:120]}"


# ---------------------------------------------------------------- info ------

@app.post("/api/info")
async def get_media_info(request: MediaRequest):
    """Fetch title, thumbnail, duration and available sizes for a link."""
    try:
        url = validate_url(request.url)
        opts = {
            "quiet": True,
            "no_warnings": True,
            "noplaylist": False,
            "playlistend": 30,
            "ignoreerrors": True,
            "ignore_no_formats_error": True,
            "extractor_args": {"youtube": ["player_client=android", "player_client=web"]},
            "logger": QuietLogger(),
        }
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)

        if not info:
            raise HTTPException(status_code=400, detail="Could not retrieve any info from that URL.")

        platform = (
            info.get("extractor_key")
            or info.get("extractor")
            or ""
        ).upper()

        title = info.get("title") or "Untitled"

        if info.get("_type") == "playlist":
            raw_entries = list(info.get("entries") or [])
            clean_entries = []
            all_images = True

            for idx, entry in enumerate(raw_entries):
                if not isinstance(entry, dict):
                    continue

                is_img = not _has_video_formats(entry)
                if not is_img:
                    all_images = False

                thumb = entry.get("thumbnail") or ""
                if not thumb:
                    thumbs = entry.get("thumbnails") or []
                    if thumbs:
                        thumb = thumbs[-1].get("url", "")

                clean_entries.append({
                    "id": str(idx + 1),
                    "title": entry.get("title") or f"Item {idx+1}",
                    "thumbnail": thumb,
                    "is_image": is_img,
                })

            count = len(clean_entries)
            thumbnail = clean_entries[0]["thumbnail"] if clean_entries else ""

            return {
                "title": title,
                "thumbnail": thumbnail,
                "duration": 0,
                "uploader": info.get("uploader") or info.get("channel") or "",
                "platform": platform,
                "sizes": {"zip": f"{count} items"},
                "entries": clean_entries,
                "media_type": "carousel",
            }

        media_type = _detect_media_type(info)
        formats = info.get("formats", [])
        return {
            "title": title,
            "thumbnail": info.get("thumbnail") or "",
            "duration": info.get("duration") or 0,
            "uploader": info.get("uploader") or info.get("channel") or "",
            "platform": platform,
            "sizes": estimate_sizes(formats, info),
            "media_type": media_type,
        }
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=400, detail=friendly_error(str(exc))
        )


# ---------------------------------------------------------------- download --

def _download_single_item(entry: dict, dest_dir: str, prefix: str, task_id: str = "", progress_msg: str = "") -> bool:
    """
    Download a single media item (video or image) into dest_dir.
    Returns True if a file was successfully written.
    """
    title_raw = entry.get("title") or prefix
    safe_title = re.sub(r"[^\w\s\-]", "", title_raw).strip()[:50].strip() or prefix

    # Try as video first (if it has video formats)
    if _has_video_formats(entry):
        entry_url = entry.get("webpage_url") or entry.get("url") or entry.get("original_url", "")
        if entry_url:
            vid_opts = {
                "outtmpl": os.path.join(dest_dir, f"{safe_title}.%(ext)s"),
                "format": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
                "quiet": True,
                "no_warnings": True,
                "noplaylist": True,
                "ignoreerrors": True,
                "merge_output_format": "mp4",
                "extractor_args": {"youtube": ["player_client=android", "player_client=web"]},
                "logger": QuietLogger(),
            }
            try:
                with yt_dlp.YoutubeDL(vid_opts) as ydl:
                    ydl.extract_info(entry_url, download=True)
                # Verify a file was written
                for f in os.listdir(dest_dir):
                    if f.startswith(safe_title):
                        return True
            except Exception as e:
                print(f"[MySaver] Video DL failed for {safe_title}: {e}")

    # Try as image
    image_url, headers = _get_best_image_url(entry)
    if image_url:
        raw_ext = image_url.split("?")[0].split(".")[-1].lower()
        if raw_ext not in ("jpg", "jpeg", "png", "webp", "gif"):
            raw_ext = "jpg"
        try:
            _download_image_to_file(image_url, os.path.join(dest_dir, f"{safe_title}.{raw_ext}"), headers)
            return True
        except Exception as e:
            print(f"[MySaver] Image DL failed for {safe_title}: {e}")

    return False


def _download_worker(task_id: str, url: str, quality: str, playlist_item: Optional[int] = None) -> None:
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

    # ── ZIP (multi-item) ──
    if quality == "zip":
        playlist_dir = os.path.join(DOWNLOAD_DIR, task_id)
        os.makedirs(playlist_dir, exist_ok=True)

        try:
            # Step 1: Extract full info for all entries (no download yet)
            _update_task(task_id, message="Analyzing all items…")
            info_opts = {
                "quiet": True,
                "no_warnings": True,
                "noplaylist": False,
                "playlistend": 30,
                "ignoreerrors": True,
                "ignore_no_formats_error": True,
                "extractor_args": {"youtube": ["player_client=android", "player_client=web"]},
                "logger": QuietLogger(),
            }
            with yt_dlp.YoutubeDL(info_opts) as ydl:
                info = ydl.extract_info(url, download=False)
            info = info or {}

            entries = []
            if info.get("_type") == "playlist":
                entries = [e for e in (info.get("entries") or []) if isinstance(e, dict)]
            else:
                entries = [info]

            if not entries:
                raise RuntimeError("No downloadable items found.")

            # Step 2: Download each entry individually
            total = len(entries)
            downloaded = 0
            for idx, entry in enumerate(entries):
                pct = int(((idx) / total) * 90)
                _update_task(task_id, percent=pct, message=f"Downloading item {idx+1}/{total}…")
                ok = _download_single_item(entry, playlist_dir, f"item_{idx+1}", task_id)
                if ok:
                    downloaded += 1

            if downloaded == 0:
                raise RuntimeError("Could not download any items. They may be private or require login.")

            # Step 3: ZIP
            _update_task(task_id, percent=92, message=f"Creating ZIP ({downloaded} files)…")
            zip_path = os.path.join(DOWNLOAD_DIR, f"{task_id}.zip")
            shutil.make_archive(os.path.join(DOWNLOAD_DIR, task_id), 'zip', playlist_dir)

            title = (info.get("title") or "Download").strip()
            safe_title = re.sub(r"[^\w\s\-]", "", title).strip()[:50].strip() or "download"

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

    # ── PHOTO (or auto-detect from carousel item) ──
    if quality == "photo":
        try:
            _update_task(task_id, message="Extracting media info…")

            extract_opts = {
                "quiet": True,
                "no_warnings": True,
                "noplaylist": False,
                "ignoreerrors": True,
                "ignore_no_formats_error": True,
                "extractor_args": {"youtube": ["player_client=android", "player_client=web"]},
                "logger": QuietLogger(),
            }
            if playlist_item:
                extract_opts["playlist_items"] = str(playlist_item)

            with yt_dlp.YoutubeDL(extract_opts) as ydl:
                info = ydl.extract_info(url, download=False)
            info = info or {}

            # If playlist, grab the specific entry
            if info.get("_type") == "playlist":
                entries = [e for e in (info.get("entries") or []) if isinstance(e, dict)]
                if entries:
                    info = entries[0]

            _update_task(task_id, percent=30, message="Downloading image…")

            # Try to get image URL
            image_url, headers = _get_best_image_url(info)
            if not image_url:
                raise RuntimeError("Could not find a downloadable image URL for this content.")

            raw_ext = image_url.split("?")[0].split(".")[-1].lower()
            if raw_ext not in ("jpg", "jpeg", "png", "webp", "gif"):
                raw_ext = "jpg"

            output_path = os.path.join(DOWNLOAD_DIR, f"{task_id}.{raw_ext}")
            _download_image_to_file(image_url, output_path, headers)

            title = (info.get("title") or "photo").strip()
            safe_title = re.sub(r"[^\w\s\-]", "", title).strip()[:50].strip() or "photo"

            _update_task(
                task_id,
                status="done",
                percent=100,
                message="Done!",
                filename=f"{safe_title}.{raw_ext}",
                filepath=output_path,
            )
            auto_delete_file(output_path, task_id)

        except Exception as exc:
            _update_task(task_id, status="error", error=friendly_error(str(exc)))
            for f in os.listdir(DOWNLOAD_DIR):
                if f.startswith(task_id):
                    try:
                        os.remove(os.path.join(DOWNLOAD_DIR, f))
                    except:
                        pass
        return

    # ── AUDIO ──
    if quality == "audio":
        ext = "mp3"
        opts = {
            "outtmpl": outtmpl_path,
            "format": "bestaudio/best",
            "quiet": True,
            "no_warnings": True,
            "noplaylist": True,
            "extractor_args": {"youtube": ["player_client=android", "player_client=web"]},
            "progress_hooks": [hook],
            "logger": QuietLogger(),
            "postprocessors": [{
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "192",
            }]
        }
    # ── VIDEO ──
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
            "logger": QuietLogger(),
        }

    # For carousel item video download, we need playlist mode
    if playlist_item:
        opts["playlist_items"] = str(playlist_item)
        opts["noplaylist"] = False

    try:
        _update_task(task_id, message="Starting download…")
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
        info = info or {}

        # If we extracted a playlist with a specific item
        if info.get("_type") == "playlist":
            entries = list(info.get("entries") or [])
            if entries and isinstance(entries[0], dict):
                info = entries[0]

        output_path = None
        for f in os.listdir(DOWNLOAD_DIR):
            if f.startswith(task_id) and not f.endswith((".part", ".ytdl")):
                if not output_path or f.endswith(f".{ext}"):
                    output_path = os.path.join(DOWNLOAD_DIR, f)

        if not output_path or not os.path.isfile(output_path):
            raise RuntimeError("The downloaded file could not be found on disk.")

        actual_ext = output_path.split(".")[-1]
        title = (info.get("title") or "download").strip()
        safe_title = re.sub(r"[^\w\s\-]", "", title).strip()[:50].strip() or "download"

        _update_task(
            task_id,
            status="done",
            percent=100,
            message="Done!",
            filename=f"{safe_title}.{actual_ext}",
            filepath=output_path,
        )
        auto_delete_file(output_path, task_id)

    except Exception as exc:
        _update_task(task_id, status="error", error=friendly_error(str(exc)))
        for f in os.listdir(DOWNLOAD_DIR):
            if f.startswith(task_id):
                try:
                    os.remove(os.path.join(DOWNLOAD_DIR, f))
                except:
                    pass


@app.post("/api/download")
async def start_download(request: MediaRequest):
    """Start downloading in the background and return a task id to poll."""
    url = validate_url(request.url)
    task_id = uuid.uuid4().hex
    _register_task(task_id)
    threading.Thread(
        target=_download_worker, args=(task_id, url, request.quality, request.playlist_item), daemon=True
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

    filename = str(task["filename"]).lower()
    ext = filename.split(".")[-1]
    mime_map = {
        "mp4": "video/mp4", "webm": "video/webm", "mkv": "video/x-matroska",
        "mp3": "audio/mpeg", "m4a": "audio/mp4", "ogg": "audio/ogg", "wav": "audio/wav",
        "jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png",
        "webp": "image/webp", "gif": "image/gif",
        "zip": "application/zip",
    }
    media = mime_map.get(ext, "application/octet-stream")

    return FileResponse(
        task["filepath"], filename=task["filename"], media_type=media
    )


# Static frontend (index.html) is served from the same folder.
app.mount("/", StaticFiles(directory=BASE_DIR, html=True), name="frontend")

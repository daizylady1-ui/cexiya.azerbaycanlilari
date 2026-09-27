"""Сборка Reels: видео-фон (свои клипы / Pexels / слайды) + плашки с текстом + логотип внизу."""
import os
import random
import shutil
import subprocess
from pathlib import Path

import requests

from .util import ROOT, log

FPS = 30


def ffmpeg_bin() -> str:
    found = shutil.which("ffmpeg")
    if found:
        return found
    import imageio_ffmpeg
    return imageio_ffmpeg.get_ffmpeg_exe()


def run(args: list[str]) -> None:
    cmd = [ffmpeg_bin(), "-y", "-hide_banner", "-loglevel", "error", *args]
    subprocess.run(cmd, check=True)


# ── источники видео-фона ─────────────────────────────────────

def own_clips() -> list[Path]:
    folder = ROOT / "assets" / "clips"
    return sorted(p for p in folder.glob("*") if p.suffix.lower() in (".mp4", ".mov", ".m4v")) if folder.exists() else []


def pexels_clip(query: str, cache: Path) -> Path | None:
    """Бесплатное стоковое видео с Pexels (лицензия разрешает коммерческое использование)."""
    key = os.environ.get("PEXELS_API_KEY")
    if not key or not query:
        return None
    try:
        r = requests.get("https://api.pexels.com/videos/search",
                         params={"query": query, "orientation": "portrait", "per_page": 10},
                         headers={"Authorization": key}, timeout=30)
        r.raise_for_status()
        videos = r.json().get("videos", [])
        if not videos:
            return None
        video = random.choice(videos[:6])
        files = [f for f in video["video_files"] if f.get("height") and f["height"] >= 1280 and f.get("file_type") == "video/mp4"]
        if not files:
            return None
        best = min(files, key=lambda f: abs(f["height"] - 1920))
        cache.mkdir(parents=True, exist_ok=True)
        path = cache / f"pexels_{video['id']}.mp4"
        if not path.exists():
            with requests.get(best["link"], stream=True, timeout=120) as dl:
                dl.raise_for_status()
                with open(path, "wb") as f:
                    for chunk in dl.iter_content(1 << 20):
                        f.write(chunk)
        return path
    except (requests.RequestException, KeyError, ValueError) as e:
        log.warning("Pexels '%s': %s", query, e)
        return None


# ── сегменты ─────────────────────────────────────────────────

SCALE = "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,setsar=1,fps=30"


def segment_from_clip(clip: Path, overlay: Path, seconds: float, out: Path) -> Path:
    run(["-stream_loop", "-1", "-t", str(seconds), "-i", str(clip), "-i", str(overlay),
         "-filter_complex", f"[0:v]{SCALE}[b];[b][1:v]overlay=0:0,format=yuv420p[v]",
         "-map", "[v]", "-an", "-t", str(seconds),
         "-c:v", "libx264", "-preset", "veryfast", "-crf", "22", "-maxrate", "4M", "-bufsize", "8M", str(out)])
    return out


def segment_from_image(frame: Path, overlay: Path | None, seconds: float, out: Path) -> Path:
    """Статичный кадр с лёгким наездом камеры (Ken Burns)."""
    frames = int(seconds * FPS)
    zoom = f"scale=2160:3840,zoompan=z='min(zoom+0.0007,1.08)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={frames}:s=1080x1920:fps={FPS}"
    inputs = ["-loop", "1", "-t", str(seconds), "-i", str(frame)]
    if overlay:
        inputs += ["-i", str(overlay)]
        fc = f"[0:v]{zoom}[b];[b][1:v]overlay=0:0,format=yuv420p[v]"
    else:
        fc = f"[0:v]{zoom},format=yuv420p[v]"
    run([*inputs, "-filter_complex", fc, "-map", "[v]", "-an", "-frames:v", str(frames),
         "-c:v", "libx264", "-preset", "veryfast", "-crf", "22", "-maxrate", "4M", "-bufsize", "8M", str(out)])
    return out


def assemble(segments: list[Path], out: Path, music_dir: Path | None) -> Path:
    """Склейка сегментов + музыка (или тихая дорожка — Instagram надёжнее принимает видео со звуком)."""
    lst = out.with_suffix(".txt")
    lst.write_text("".join(f"file '{p.resolve().as_posix()}'\n" for p in segments), encoding="utf-8")
    silent = out.with_name(out.stem + "_v.mp4")
    run(["-f", "concat", "-safe", "0", "-i", str(lst), "-c:v", "libx264", "-preset", "veryfast",
         "-crf", "22", "-maxrate", "4M", "-bufsize", "8M", "-pix_fmt", "yuv420p", "-r", str(FPS), str(silent)])

    tracks = sorted(music_dir.glob("*.mp3")) if music_dir and music_dir.exists() else []
    if tracks:
        audio = ["-stream_loop", "-1", "-i", str(random.choice(tracks))]
        af = ["-af", "afade=t=in:d=1,volume=0.8"]
    else:
        audio = ["-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=44100"]
        af = []
    run(["-i", str(silent), *audio, "-map", "0:v", "-map", "1:a", *af,
         "-c:v", "copy", "-c:a", "aac", "-b:a", "128k", "-shortest", "-movflags", "+faststart", str(out)])
    silent.unlink(missing_ok=True)
    lst.unlink(missing_ok=True)
    return out

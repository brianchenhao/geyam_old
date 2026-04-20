"""Video utilities. Middle-frame extraction uses ffmpeg via imageio-ffmpeg."""
import subprocess
from pathlib import Path

import imageio_ffmpeg


def _ffmpeg() -> str:
    return imageio_ffmpeg.get_ffmpeg_exe()


def _probe_frame_count(video_path: str) -> int | None:
    """Try ffprobe-equivalent via ffmpeg -- returns total frames or None if unknown."""
    try:
        out = subprocess.run(
            [_ffmpeg(), "-i", video_path, "-map", "0:v:0",
             "-c", "copy", "-f", "null", "-"],
            capture_output=True, text=True, timeout=30,
        )
        # ffmpeg writes "frame=  N" on stderr
        for line in out.stderr.splitlines()[::-1]:
            if "frame=" in line:
                token = line.split("frame=", 1)[1].strip().split()[0]
                if token.isdigit():
                    return int(token)
        return None
    except Exception:
        return None


def probe_duration_sec(video_path: str) -> float | None:
    try:
        out = subprocess.run(
            [_ffmpeg(), "-i", video_path], capture_output=True, text=True, timeout=30,
        )
        for line in out.stderr.splitlines():
            if "Duration:" in line:
                dur = line.split("Duration:", 1)[1].split(",", 1)[0].strip()
                h, m, s = dur.split(":")
                return int(h) * 3600 + int(m) * 60 + float(s)
    except Exception:
        return None
    return None


def extract_middle_frame(video_path: str, out_image_path: str) -> None:
    """Write a single JPEG of the middle frame. Raises on ffmpeg failure."""
    Path(out_image_path).parent.mkdir(parents=True, exist_ok=True)

    dur = probe_duration_sec(video_path)
    mid = max(dur / 2.0, 0.0) if dur else 0.0
    cmd = [
        _ffmpeg(), "-y", "-ss", f"{mid:.3f}", "-i", video_path,
        "-frames:v", "1", "-q:v", "2", out_image_path,
    ]
    res = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    if res.returncode != 0 or not Path(out_image_path).exists():
        raise RuntimeError(f"ffmpeg failed: {res.stderr[-500:]}")

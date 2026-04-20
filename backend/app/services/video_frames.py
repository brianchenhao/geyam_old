"""Video frame utilities. Uses imageio_ffmpeg's bundled ffmpeg binary via subprocess
so we do not have to depend on a system-installed ffmpeg.
"""
import os
import shutil
import subprocess
from pathlib import Path
from typing import Optional


def _ffmpeg_exe() -> str:
    import imageio_ffmpeg
    return imageio_ffmpeg.get_ffmpeg_exe()


def probe_duration_seconds(video_path: str | Path) -> Optional[float]:
    """Returns duration in seconds, or None if ffprobe fails."""
    exe = _ffmpeg_exe()
    try:
        out = subprocess.run(
            [exe, "-i", str(video_path), "-hide_banner"],
            capture_output=True, text=True, timeout=15,
        )
        # ffmpeg emits 'Duration: HH:MM:SS.xx' on stderr even in probe-only mode
        for line in out.stderr.splitlines():
            s = line.strip()
            if s.startswith("Duration:"):
                # "Duration: 00:00:03.12, start: ..., bitrate: ..."
                hh, mm, rest = s.split()[1].rstrip(",").split(":")
                return int(hh) * 3600 + int(mm) * 60 + float(rest)
    except Exception:
        return None
    return None


def extract_middle_frame(video_path: str | Path, out_path: str | Path) -> bool:
    """Saves the middle frame of the video as JPEG."""
    dur = probe_duration_seconds(video_path) or 0.0
    mid = max(dur / 2.0, 0.0)
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    r = subprocess.run(
        [_ffmpeg_exe(), "-y", "-ss", f"{mid:.2f}", "-i", str(video_path),
         "-frames:v", "1", "-q:v", "3", str(out_path)],
        capture_output=True, timeout=30,
    )
    return r.returncode == 0 and Path(out_path).exists()


def extract_frames_at_fps(video_path: str | Path, out_dir: str | Path,
                           fps: int = 2, prefix: str = "frame") -> int:
    """Writes `prefix`_0001.jpg, `prefix`_0002.jpg ... Returns count saved."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    pattern = str(out_dir / f"{prefix}_%04d.jpg")
    r = subprocess.run(
        [_ffmpeg_exe(), "-y", "-i", str(video_path), "-vf", f"fps={fps}",
         "-q:v", "3", pattern],
        capture_output=True, timeout=120,
    )
    if r.returncode != 0:
        return 0
    return len(list(out_dir.glob(f"{prefix}_*.jpg")))

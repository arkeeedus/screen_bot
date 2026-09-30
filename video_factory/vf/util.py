import os
import re
import shutil
import subprocess
import unicodedata
from functools import lru_cache

import yaml


def load_config(path):
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def log(msg):
    print(msg, flush=True)


@lru_cache(maxsize=1)
def ffmpeg_bin():
    """ffmpeg из PATH, иначе бинарник из пакета imageio-ffmpeg (ставится через pip)."""
    exe = shutil.which("ffmpeg")
    if exe:
        return exe
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except ImportError:
        raise RuntimeError("ffmpeg не найден: установите ffmpeg или выполните pip install imageio-ffmpeg")


def run_ffmpeg(args, cwd=None):
    cmd = [ffmpeg_bin(), "-hide_banner", "-loglevel", "error", "-y", *args]
    res = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if res.returncode != 0:
        raise RuntimeError(f"ffmpeg завершился с ошибкой:\n{' '.join(cmd)}\n{res.stderr[-3000:]}")
    return res


def media_duration(path):
    """Длительность файла в секундах (без ffprobe — парсим вывод ffmpeg)."""
    res = subprocess.run([ffmpeg_bin(), "-hide_banner", "-i", str(path)],
                         capture_output=True, text=True, encoding="utf-8", errors="replace")
    m = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", res.stderr)
    if not m:
        raise RuntimeError(f"Не удалось определить длительность {path}")
    h, mnt, s = m.groups()
    return int(h) * 3600 + int(mnt) * 60 + float(s)


@lru_cache(maxsize=1)
def nvenc_available():
    """Проверяем, что h264_nvenc реально работает (есть RTX и драйвер), а не только собран в ffmpeg."""
    try:
        run_ffmpeg(["-f", "lavfi", "-i", "color=black:s=256x256:d=0.1", "-c:v", "h264_nvenc", "-f", "null", "-"])
        return True
    except Exception:
        return False


def video_encoder_args(encoder="auto"):
    if encoder == "auto":
        encoder = "h264_nvenc" if nvenc_available() else "libx264"
    if encoder == "h264_nvenc":
        return ["-c:v", "h264_nvenc", "-preset", "p5", "-rc", "vbr", "-cq", "21", "-b:v", "0", "-pix_fmt", "yuv420p"]
    return ["-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p"]


def slugify(text, max_len=40):
    text = unicodedata.normalize("NFKC", text).lower()
    text = re.sub(r"[^\w\s-]", "", text, flags=re.UNICODE)
    text = re.sub(r"[\s_-]+", "_", text).strip("_")
    return text[:max_len] or "video"


def env_or(value, env_name):
    return value or os.environ.get(env_name, "")

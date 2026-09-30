"""Монтаж через ffmpeg: клипы сцен с эффектом Ken Burns, склейка, музыка, субтитры."""
import os
import random
import shutil
import wave

from .util import run_ffmpeg, video_encoder_args

SR = 48000


def to_wav(src, dst):
    run_ffmpeg(["-i", src, "-ac", "1", "-ar", str(SR), "-sample_fmt", "s16", dst])
    with wave.open(dst, "rb") as w:
        return w.getnframes() / SR


def concat_wavs(parts, dst):
    """parts: [(wav_path, pause_after_sec)] — склейка с паузами, тайминг точный до сэмпла."""
    with wave.open(dst, "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(SR)
        for path, pause in parts:
            with wave.open(path, "rb") as w:
                out.writeframes(w.readframes(w.getnframes()))
            out.writeframes(b"\x00\x00" * int(pause * SR))


def _ken_burns(idx, frames, w, h, fps):
    n = max(frames - 1, 1)
    z = 0.18
    variants = [
        (f"1+{z}*on/{n}", "iw/2-(iw/zoom/2)", "ih/2-(ih/zoom/2)"),                 # наезд в центр
        (f"{1 + z}-{z}*on/{n}", "iw/2-(iw/zoom/2)", "ih/2-(ih/zoom/2)"),           # отъезд
        (f"{1 + z}", f"(iw-iw/zoom)*on/{n}", "ih/2-(ih/zoom/2)"),                  # панорама вправо
        (f"{1 + z}", f"(iw-iw/zoom)*(1-on/{n})", "ih/2-(ih/zoom/2)"),              # панорама влево
        (f"1+{z}*on/{n}", "iw/2-(iw/zoom/2)", f"(ih-ih/zoom)*0.3"),                # наезд вверх
    ]
    zexp, x, y = variants[idx % len(variants)]
    return (f"scale={w * 2}:{h * 2}:force_original_aspect_ratio=increase,crop={w * 2}:{h * 2},"
            f"zoompan=z='{zexp}':x='{x}':y='{y}':d={frames}:s={w}x{h}:fps={fps},setsar=1,format=yuv420p")


def render_scene_clip(src, kind, duration, out, idx, rcfg, cwd):
    w, h, fps = rcfg.get("width", 1080), rcfg.get("height", 1920), rcfg.get("fps", 30)
    frames = max(1, round(duration * fps))
    enc = video_encoder_args(rcfg.get("encoder", "auto"))
    if kind == "video":
        vf = f"scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},fps={fps},setsar=1,format=yuv420p"
        args = ["-stream_loop", "-1", "-i", src, "-vf", vf]
    elif rcfg.get("ken_burns", True):
        args = ["-i", src, "-vf", _ken_burns(idx, frames, w, h, fps)]
    else:
        vf = f"scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},setsar=1,format=yuv420p"
        args = ["-loop", "1", "-framerate", str(fps), "-i", src, "-vf", vf]
    run_ffmpeg([*args, "-frames:v", str(frames), "-an", *enc, "-r", str(fps), out], cwd=cwd)


def _pick_music(music_dir):
    if not music_dir or not os.path.isdir(music_dir):
        return None
    tracks = [os.path.join(music_dir, f) for f in os.listdir(music_dir)
              if f.lower().endswith((".mp3", ".wav", ".m4a", ".ogg"))]
    return os.path.abspath(random.choice(tracks)) if tracks else None


def final_render(clips, narration, ass_file, out_file, rcfg, cwd, fonts_dir=None):
    with open(os.path.join(cwd, "clips.txt"), "w", encoding="utf-8") as f:
        for c in clips:
            f.write(f"file '{c}'\n")

    args = ["-f", "concat", "-safe", "0", "-i", "clips.txt", "-i", narration]
    music = _pick_music(rcfg.get("music_dir"))
    if music:
        args += ["-stream_loop", "-1", "-i", music]
        afilter = (f"[2:a]volume={rcfg.get('music_volume', 0.12)}[m];"
                   "[1:a][m]amix=inputs=2:duration=first:dropout_transition=0:normalize=0[a]")
    else:
        afilter = "[1:a]anull[a]"

    vfilter = "[0:v]null[v]"
    if ass_file:
        fonts_opt = ""
        if fonts_dir and os.path.isdir(fonts_dir) and any(f.lower().endswith((".ttf", ".otf"))
                                                          for f in os.listdir(fonts_dir)):
            shutil.copytree(fonts_dir, os.path.join(cwd, "fonts"), dirs_exist_ok=True)
            fonts_opt = ":fontsdir=fonts"
        vfilter = f"[0:v]ass={ass_file}{fonts_opt}[v]"

    args += ["-filter_complex", f"{vfilter};{afilter}", "-map", "[v]", "-map", "[a]",
             *video_encoder_args(rcfg.get("encoder", "auto")),
             "-c:a", "aac", "-b:a", "192k", "-shortest", "-movflags", "+faststart", out_file]
    run_ffmpeg(args, cwd=cwd)

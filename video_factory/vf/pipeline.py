"""Конвейер: тема -> сценарий -> озвучка -> видеоряд -> субтитры -> готовый ролик."""
import json
import os
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

from . import render, script_gen, subtitles, tts, visuals
from .util import log, slugify

SCENE_PAUSE = 0.18   # пауза между сценами, сек
TAIL_PAUSE = 0.8     # хвост в конце ролика


def make_video(topic, config, script_path=None, base_dir="."):
    t0 = time.time()
    rcfg = dict(config.get("render", {}))
    if rcfg.get("music_dir") and not os.path.isabs(rcfg["music_dir"]):
        rcfg["music_dir"] = os.path.join(base_dir, rcfg["music_dir"])
    out_root = os.path.join(base_dir, config.get("output_dir", "out"))

    # 1. Сценарий
    if script_path:
        log(f"[1/5] Сценарий из файла {script_path}")
        script = script_gen.load_script(script_path)
        topic = topic or script["title"]
    else:
        log(f"[1/5] Пишу сценарий: {topic}")
        script = script_gen.generate_script(topic, config)
    scenes = script["scenes"]
    log(f"  «{script['title']}», сцен: {len(scenes)}")

    job = os.path.join(out_root, f"{datetime.now():%Y-%m-%d_%H%M%S}_{slugify(script['title'])}")
    work = os.path.join(job, "work")
    os.makedirs(work, exist_ok=True)
    with open(os.path.join(job, "script.json"), "w", encoding="utf-8") as f:
        json.dump(script, f, ensure_ascii=False, indent=2)

    # 2. Озвучка по сценам — длительность сцены = длительность её фразы
    log("[2/5] Озвучка")
    parts, words, durations, offset = [], [], [], 0.0
    for i, sc in enumerate(scenes):
        raw, _, scene_words = tts.synthesize(sc["text"], os.path.join(work, f"voice_{i:02d}"), config)
        wav = os.path.join(work, f"voice_{i:02d}_n.wav")
        dur = render.to_wav(raw, wav)
        pause = TAIL_PAUSE if i == len(scenes) - 1 else SCENE_PAUSE
        parts.append((wav, pause))
        words += [(w, s + offset, e + offset, i) for w, s, e in scene_words]
        durations.append(dur + pause)
        offset += dur + pause
        log(f"  сцена {i + 1}: {dur:.1f} c")
    render.concat_wavs(parts, os.path.join(work, "narration.wav"))
    total = offset

    # 3. Видеоряд
    log(f"[3/5] Видеоряд ({config.get('visuals', {}).get('source', 'pollinations')})")
    workers = 1 if config.get("visuals", {}).get("source") == "local" else 3

    def _gen(i):
        path, kind = visuals.make_visual(scenes[i], os.path.join(work, f"visual_{i:02d}"), config, i)
        log(f"  сцена {i + 1}: {os.path.basename(path)}")
        return os.path.basename(path), kind

    with ThreadPoolExecutor(workers) as ex:
        media = list(ex.map(_gen, range(len(scenes))))

    # 4. Клипы сцен
    log("[4/5] Монтаж сцен")
    clips = []
    for i, ((src, kind), dur) in enumerate(zip(media, durations)):
        clip = f"clip_{i:02d}.mp4"
        render.render_scene_clip(src, kind, dur, clip, i, rcfg, cwd=work)
        clips.append(clip)

    # 5. Субтитры + финальная сборка
    log("[5/5] Субтитры и финальный рендер")
    ass_name = None
    if config.get("subtitles", {}).get("enabled", True) or config.get("hook", {}).get("enabled", True):
        ass_name = "subs.ass"
        with open(os.path.join(work, ass_name), "w", encoding="utf-8") as f:
            f.write(subtitles.build_ass(words, total, script.get("hook"), config,
                                        rcfg.get("width", 1080), rcfg.get("height", 1920)))
    out_file = os.path.abspath(os.path.join(job, "video.mp4"))
    render.final_render(clips, "narration.wav", ass_name, out_file, rcfg, cwd=work,
                        fonts_dir=os.path.join(base_dir, "assets", "fonts"))

    with open(os.path.join(job, "post.txt"), "w", encoding="utf-8") as f:
        f.write(f"{script['title']}\n\n{script['description']}\n\n{' '.join(script['hashtags'])}\n")

    log(f"Готово за {time.time() - t0:.0f} c: {out_file} ({total:.1f} c)")
    return out_file

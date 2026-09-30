"""Видеоконвейер: генерирует вертикальные ролики (Shorts/TikTok/Reels) на заданную тему.

Примеры:
  python main.py "5 фактов о чёрных дырах"
  python main.py --topics topics.txt
  python main.py --script my_script.json
  python main.py "История Bitcoin" --llm groq --visuals local --tts silero
"""
import argparse
import os
import sys
import traceback

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

from vf.pipeline import make_video  # noqa: E402
from vf.util import load_config, log  # noqa: E402


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser(description="Генератор коротких видео на заданную тему")
    p.add_argument("topic", nargs="?", help="тема ролика")
    p.add_argument("--topics", help="файл со списком тем (по одной на строку)")
    p.add_argument("--script", help="готовый сценарий в JSON (без LLM)")
    p.add_argument("--config", default=os.path.join(BASE_DIR, "config.yaml"))
    p.add_argument("--llm", help="провайдер сценария: ollama, groq, gemini, openrouter, pollinations, openai")
    p.add_argument("--model", help="модель LLM")
    p.add_argument("--visuals", help="источник видеоряда: pollinations, local, pexels")
    p.add_argument("--tts", help="озвучка: edge, silero")
    p.add_argument("--voice", help="голос edge-tts, например ru-RU-SvetlanaNeural")
    p.add_argument("--lang", help="язык ролика: ru, uk, en")
    p.add_argument("--duration", type=int, help="длительность, сек")
    p.add_argument("--scenes", type=int, help="количество сцен")
    args = p.parse_args()

    config = load_config(args.config)
    for key, section, field in [("llm", "script", "provider"), ("model", "script", "model"),
                                ("visuals", "visuals", "source"), ("tts", "tts", "engine"),
                                ("voice", "tts", "voice"), ("scenes", "script", "scenes")]:
        if getattr(args, key):
            config.setdefault(section, {})[field] = getattr(args, key)
    if args.lang:
        config["language"] = args.lang
    if args.duration:
        config["duration_sec"] = args.duration

    jobs = []
    if args.script:
        jobs.append((args.topic, args.script))
    if args.topic and not args.script:
        jobs.append((args.topic, None))
    if args.topics:
        with open(args.topics, encoding="utf-8") as f:
            jobs += [(line.strip(), None) for line in f if line.strip() and not line.startswith("#")]
    if not jobs:
        topic = input("Введите тему ролика: ").strip()
        if not topic:
            p.print_help()
            return 1
        jobs.append((topic, None))

    done, failed = [], []
    for n, (topic, script) in enumerate(jobs, 1):
        log(f"\n===== Ролик {n}/{len(jobs)} =====")
        try:
            done.append(make_video(topic, config, script_path=script, base_dir=BASE_DIR))
        except Exception as e:
            log(f"ОШИБКА: {e}")
            traceback.print_exc()
            failed.append(topic)

    log(f"\nГотово: {len(done)}, ошибок: {len(failed)}")
    for path in done:
        log(f"  {path}")
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())

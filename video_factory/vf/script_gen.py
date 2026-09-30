"""Генерация сценария ролика через LLM (локально или через бесплатный API)."""
import json
import re

import requests

from .util import env_or, log

PRESETS = {
    "ollama": {"base_url": "http://localhost:11434/v1", "env": "", "model": "qwen2.5:7b"},
    "groq": {"base_url": "https://api.groq.com/openai/v1", "env": "GROQ_API_KEY", "model": "llama-3.3-70b-versatile"},
    "gemini": {"base_url": "https://generativelanguage.googleapis.com/v1beta/openai", "env": "GEMINI_API_KEY",
               "model": "gemini-2.0-flash"},
    "openrouter": {"base_url": "https://openrouter.ai/api/v1", "env": "OPENROUTER_API_KEY",
                   "model": "meta-llama/llama-3.3-70b-instruct:free"},
    "pollinations": {"base_url": "https://text.pollinations.ai/openai", "env": "", "model": "openai"},
    "openai": {"base_url": "http://localhost:1234/v1", "env": "OPENAI_API_KEY", "model": "local-model"},
}

LANG_NAMES = {"ru": "русском", "uk": "украинском", "en": "английском"}

PROMPT = """Ты — сценарист коротких вертикальных видео.
Напиши сценарий ролика на тему: "{topic}".
Язык озвучки и текста: на {lang_name} языке ({lang}).
Стиль: {style}.
Длительность озвучки ≈ {duration} секунд (≈ {words} слов суммарно), ровно {scenes} сцен.
Для каждой сцены дай текст диктора (1–2 коротких предложения) и промпт для генерации картинки
НА АНГЛИЙСКОМ (конкретная сцена, объекты, ракурс, без текста на картинке).
Для стоковых видео дай 2–3 английских слова поиска (stock_query).

Ответь СТРОГО JSON без пояснений в формате:
{{
  "title": "заголовок ролика до 60 символов",
  "hook": "короткая плашка сверху, до 40 символов, без эмодзи",
  "description": "описание для публикации, 1–2 предложения",
  "hashtags": ["#тег1", "#тег2", "#тег3", "#тег4", "#тег5"],
  "scenes": [
    {{"text": "текст диктора", "image_prompt": "english image prompt", "stock_query": "english words"}}
  ]
}}"""


def _extract_json(text):
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text)
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("LLM не вернула JSON")
    return json.loads(text[start:end + 1])


def _validate(data):
    scenes = [s for s in data.get("scenes", []) if str(s.get("text", "")).strip()]
    if not scenes:
        raise ValueError("В сценарии нет сцен")
    for s in scenes:
        s["text"] = s["text"].strip()
        s.setdefault("image_prompt", s["text"])
        s.setdefault("stock_query", " ".join(s["image_prompt"].split()[:3]))
    data["scenes"] = scenes
    data.setdefault("title", scenes[0]["text"][:60])
    data.setdefault("hook", data["title"][:40])
    data.setdefault("description", data["title"])
    data.setdefault("hashtags", [])
    return data


def chat(cfg, prompt):
    provider = cfg.get("provider", "ollama")
    preset = PRESETS.get(provider, PRESETS["openai"])
    base_url = (cfg.get("base_url") or preset["base_url"]).rstrip("/")
    api_key = env_or(cfg.get("api_key"), preset["env"]) if preset["env"] else cfg.get("api_key", "")
    if preset["env"] and not api_key:
        raise RuntimeError(f"Для провайдера {provider} задайте api_key в config.yaml или переменную {preset['env']}")
    model = cfg.get("model") or preset["model"]
    if provider != "ollama" and cfg.get("model") == PRESETS["ollama"]["model"]:
        model = preset["model"]  # модель из примера конфига — подставляем подходящую для провайдера

    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    body = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": cfg.get("temperature", 0.9),
        "response_format": {"type": "json_object"},
    }
    log(f"  LLM: {provider} / {model}")
    r = requests.post(f"{base_url}/chat/completions", json=body, headers=headers, timeout=300)
    if r.status_code >= 400 and "response_format" in r.text:
        body.pop("response_format")  # не все серверы поддерживают JSON-режим
        r = requests.post(f"{base_url}/chat/completions", json=body, headers=headers, timeout=300)
    if r.status_code >= 400:
        raise RuntimeError(f"LLM {provider}: HTTP {r.status_code}: {r.text[:500]}")
    return r.json()["choices"][0]["message"]["content"]


def generate_script(topic, config):
    cfg = config.get("script", {})
    lang = config.get("language", "ru")
    duration = config.get("duration_sec", 45)
    prompt = PROMPT.format(
        topic=topic, lang=lang, lang_name=LANG_NAMES.get(lang, lang),
        style=cfg.get("style", ""), duration=duration,
        words=int(duration * 2.4), scenes=cfg.get("scenes", 7),
    )
    last_err = None
    for attempt in range(3):
        try:
            return _validate(_extract_json(chat(cfg, prompt)))
        except (ValueError, json.JSONDecodeError, KeyError) as e:
            last_err = e
            log(f"  Сценарий не распознан ({e}), попытка {attempt + 2}/3...")
    raise RuntimeError(f"Не удалось получить сценарий: {last_err}")


def load_script(path):
    with open(path, encoding="utf-8") as f:
        return _validate(json.load(f))

"""Видеоряд для сцен: генерация картинок (онлайн/локально на RTX) или стоковые видео."""
import random
import time
import urllib.parse

import requests

from .util import env_or, log


def _pollinations(scene, out_noext, cfg, idx):
    prompt = f"{scene['image_prompt']}, {cfg.get('image_style', '')}".strip(", ")
    params = {
        "width": cfg.get("gen_width", 768), "height": cfg.get("gen_height", 1344),
        "nologo": "true", "seed": random.randint(1, 10 ** 9), "model": cfg.get("pollinations_model", "flux"),
    }
    token = env_or(cfg.get("pollinations_token"), "POLLINATIONS_TOKEN")
    if token:  # бесплатный токен с auth.pollinations.ai убирает водяной знак и лимиты
        params["token"] = token
    url = "https://image.pollinations.ai/prompt/" + urllib.parse.quote(prompt) + "?" + urllib.parse.urlencode(params)
    for attempt in range(4):
        try:
            r = requests.get(url, timeout=180)
            if r.status_code == 200 and r.headers.get("content-type", "").startswith("image"):
                path = out_noext + ".jpg"
                with open(path, "wb") as f:
                    f.write(r.content)
                return path, "image"
            err = f"HTTP {r.status_code}"
        except requests.RequestException as e:
            err = str(e)
        log(f"  pollinations: {err}, повтор через {5 * (attempt + 1)} c...")
        time.sleep(5 * (attempt + 1))
    raise RuntimeError("pollinations не отдал картинку")


_pipe = None


def _local_sd(scene, out_noext, cfg, idx):
    """Stable Diffusion / FLUX на своей видеокарте через diffusers."""
    global _pipe
    import torch
    from diffusers import AutoPipelineForText2Image
    if _pipe is None:
        model = cfg.get("local_model", "stabilityai/sdxl-turbo")
        log(f"  Загрузка {model} на GPU (первый раз скачивается с HuggingFace)...")
        dtype = torch.bfloat16 if "FLUX" in model else torch.float16
        _pipe = AutoPipelineForText2Image.from_pretrained(model, torch_dtype=dtype)
        if torch.cuda.is_available():
            if cfg.get("cpu_offload") or "FLUX" in model:
                _pipe.enable_model_cpu_offload()  # экономит VRAM на картах 8–12 ГБ
            else:
                _pipe.to("cuda")
    prompt = f"{scene['image_prompt']}, {cfg.get('image_style', '')}"
    image = _pipe(
        prompt=prompt,
        num_inference_steps=cfg.get("local_steps", 4),
        guidance_scale=cfg.get("local_guidance", 0.0),
        width=cfg.get("gen_width", 768), height=cfg.get("gen_height", 1344),
    ).images[0]
    path = out_noext + ".png"
    image.save(path)
    return path, "image"


def _pexels(scene, out_noext, cfg, idx):
    key = env_or(cfg.get("pexels_api_key"), "PEXELS_API_KEY")
    if not key:
        raise RuntimeError("Для pexels задайте PEXELS_API_KEY")
    r = requests.get("https://api.pexels.com/videos/search", headers={"Authorization": key},
                     params={"query": scene["stock_query"], "orientation": "portrait", "per_page": 10}, timeout=60)
    r.raise_for_status()
    videos = r.json().get("videos", [])
    if not videos:
        raise RuntimeError(f"pexels: ничего не найдено по '{scene['stock_query']}'")
    video = random.choice(videos[:5])
    files = [f for f in video["video_files"] if f.get("height") and f["file_type"] == "video/mp4"]
    # ближайший к 1920 по высоте, чтобы не качать 4K
    best = min(files, key=lambda f: abs(f["height"] - 1920))
    path = out_noext + ".mp4"
    with requests.get(best["link"], stream=True, timeout=300) as resp:
        resp.raise_for_status()
        with open(path, "wb") as f:
            for chunk in resp.iter_content(1 << 20):
                f.write(chunk)
    return path, "video"


SOURCES = {"pollinations": _pollinations, "local": _local_sd, "pexels": _pexels}


def make_visual(scene, out_noext, config, idx):
    cfg = config.get("visuals", {})
    source = cfg.get("source", "pollinations")
    try:
        return SOURCES[source](scene, out_noext, cfg, idx)
    except Exception as e:
        fb = cfg.get("fallback")
        if not fb or fb == source:
            raise
        log(f"  {source} не сработал ({e}), пробую {fb}")
        return SOURCES[fb](scene, out_noext, cfg, idx)

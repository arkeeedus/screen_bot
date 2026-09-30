"""Озвучка сцен. Возвращает аудиофайл, длительность и тайминги слов для субтитров."""
import asyncio
import os
import wave

from .util import log, media_duration


def _estimate_words(text, duration):
    """Если движок не отдаёт тайминги — раскладываем слова пропорционально длине."""
    words = text.split()
    total = sum(len(w) + 1 for w in words) or 1
    t, out = 0.0, []
    for w in words:
        d = duration * (len(w) + 1) / total
        out.append((w, t, t + d))
        t += d
    return out


# ---------- Microsoft Edge TTS (бесплатно, онлайн) ----------

def _edge_fix_ssl():
    # За корпоративным прокси с собственным сертификатом edge-tts не видит SSL_CERT_FILE — добавляем вручную.
    ca = os.environ.get("SSL_CERT_FILE")
    if ca and os.path.exists(ca):
        try:
            from edge_tts import communicate
            communicate._SSL_CTX.load_verify_locations(ca)
        except Exception:
            pass


async def _edge_async(text, out_path, voice, rate):
    import edge_tts
    comm = edge_tts.Communicate(text, voice, rate=rate, boundary="WordBoundary")
    words = []
    with open(out_path, "wb") as f:
        async for chunk in comm.stream():
            if chunk["type"] == "audio":
                f.write(chunk["data"])
            elif chunk["type"] == "WordBoundary":
                start = chunk["offset"] / 1e7
                words.append((chunk["text"], start, start + chunk["duration"] / 1e7))
    return words


def _edge(text, out_path, cfg):
    _edge_fix_ssl()
    out_path = out_path + ".mp3"
    for attempt in range(3):
        try:
            words = asyncio.run(_edge_async(text, out_path, cfg.get("voice", "ru-RU-DmitryNeural"),
                                            cfg.get("rate", "+0%")))
            break
        except Exception as e:
            if attempt == 2:
                raise
            log(f"  edge-tts ошибка ({e}), повтор...")
    duration = media_duration(out_path)
    if not words:
        return out_path, duration, _estimate_words(text, duration)
    tokens = text.split()
    if len(tokens) == len(words):  # edge-tts отдаёт слова без пунктуации — возвращаем её для разбивки субтитров
        words = [(tok, s, e) for tok, (_, s, e) in zip(tokens, words)]
    return out_path, duration, words


# ---------- Silero (локально, GPU/CPU) ----------

_silero = None


def _silero_tts(text, out_path, cfg):
    global _silero
    import torch
    if _silero is None:
        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        log(f"  Загрузка Silero на {device}...")
        model, _ = torch.hub.load("snakers4/silero-models", "silero_tts",
                                  language=cfg.get("silero_language", "ru"),
                                  speaker=cfg.get("silero_model", "v4_ru"), trust_repo=True)
        model.to(device)
        _silero = model
    sr = 48000
    audio = _silero.apply_tts(text=text, speaker=cfg.get("silero_speaker", "aidar"), sample_rate=sr)
    pcm = (audio.clamp(-1, 1).cpu().numpy() * 32767).astype("int16")
    out_path = out_path + ".wav"
    with wave.open(out_path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(pcm.tobytes())
    duration = len(pcm) / sr
    return out_path, duration, _estimate_words(text, duration)


ENGINES = {"edge": _edge, "silero": _silero_tts}


def synthesize(text, out_path_noext, config):
    cfg = config.get("tts", {})
    engine = cfg.get("engine", "edge")
    if engine not in ENGINES:
        raise ValueError(f"Неизвестный движок озвучки: {engine}")
    return ENGINES[engine](text, out_path_noext, cfg)

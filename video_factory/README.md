# Видеоконвейер (контент-завод)

Генерирует вертикальные ролики 1080×1920 для TikTok, Shorts и Reels на заданную тему. Работает бесплатно: либо на вашей видеокарте NVIDIA RTX, либо через бесплатные онлайн-сервисы.

```
тема ─► сценарий (LLM) ─► озвучка ─► картинки/клипы ─► субтитры ─► video.mp4 + post.txt
```

На выходе в `out/<дата>_<название>/`:
- `video.mp4` — готовый ролик: озвучка, эффект Ken Burns (плавный зум) по картинкам, крупные субтитры с подсветкой слова, плашка-хук сверху и фоновая музыка;
- `post.txt` — заголовок, описание и хэштеги для публикации;
- `script.json` — сценарий. Его можно поправить и собрать ролик заново через `--script`.

## Из чего собирается (всё бесплатно)

| Этап | Локально на RTX | Бесплатно онлайн |
|---|---|---|
| Сценарий | **Ollama** (qwen2.5, llama3.1, gemma2) | Groq, Gemini (AI Studio), OpenRouter `:free`, Pollinations |
| Озвучка | **Silero** (torch, без интернета) | **Edge TTS** — нейроголоса Microsoft, ru/uk/en |
| Видеоряд | **SDXL-Turbo / FLUX.1-schnell** через diffusers | **Pollinations** (картинки без ключа), **Pexels** (стоковое видео) |
| Монтаж | ffmpeg, кодирование на **NVENC**, если есть RTX | — |

## Установка (Windows)

1. Установите [Python 3.10+](https://www.python.org/downloads/) и при установке отметьте «Add to PATH».
2. Для локального сценария установите [Ollama](https://ollama.com) и скачайте модель:
   ```
   ollama pull qwen2.5:7b
   ```
   Для 8 ГБ VRAM хватит `qwen2.5:7b`. Для 16 ГБ и больше подойдёт `qwen2.5:14b`: текст будет лучше.
3. Запустите `run.bat`. При первом запуске он сам создаст окружение и поставит зависимости, потом спросит тему.

Ffmpeg ставить отдельно не нужно: он подтягивается пакетом `imageio-ffmpeg`.

### Картинки и озвучка на видеокарте (по желанию)

```
.venv\Scripts\pip install torch --index-url https://download.pytorch.org/whl/cu124
.venv\Scripts\pip install -r requirements-gpu.txt
```

Затем в `config.yaml` укажите `visuals.source: local` и/или `tts.engine: silero`.
- `stabilityai/sdxl-turbo`: быстро, от 8 ГБ VRAM, 4 шага на картинку.
- `black-forest-labs/FLUX.1-schnell`: заметно качественнее, но нужно 12–16+ ГБ VRAM или `cpu_offload`. Модель скачивается с HuggingFace при первом запуске.

## Использование

```bash
python main.py "5 фактов о чёрных дырах"             # один ролик
python main.py --topics topics.txt                   # пачка роликов по списку тем
python main.py --script examples/example_script.json # свой сценарий, без LLM
python main.py "Почему кошки мурлыкают" --llm groq --visuals local --tts silero --voice ru-RU-SvetlanaNeural
python main.py "Why cats purr" --lang en --voice en-US-GuyNeural --duration 30
```

Все параметры описаны в `config.yaml`: провайдеры, голоса, стиль картинок, шрифт и цвета субтитров, длительность, количество сцен.

### Бесплатные ключи (если не хотите запускать LLM локально)

| Сервис | Где взять | Переменная окружения |
|---|---|---|
| Groq (быстрые Llama 3.3 70B) | https://console.groq.com | `GROQ_API_KEY` |
| Google Gemini | https://aistudio.google.com/apikey | `GEMINI_API_KEY` |
| OpenRouter (модели `:free`) | https://openrouter.ai/keys | `OPENROUTER_API_KEY` |
| Pexels (стоковое видео) | https://www.pexels.com/api/ | `PEXELS_API_KEY` |
| Pollinations: без водяного знака | https://auth.pollinations.ai | `POLLINATIONS_TOKEN` |

Ключ можно положить прямо в `config.yaml` (поле `api_key`) или задать в Windows: `setx GROQ_API_KEY "ваш_ключ"`.

### Музыка и шрифт

- Положите mp3 в `assets/music/`, и для каждого ролика будет выбираться случайный трек. Используйте музыку без авторских ограничений, например из YouTube Audio Library.
- Положите `.ttf` в `assets/fonts/` и укажите имя шрифта в `subtitles.font`. Для кириллицы хорошо подходят Montserrat ExtraBold и Rubik Bold (Google Fonts).

## Советы

- Бесплатные онлайн-сервисы иногда отвечают ошибками 500 или 524. Конвейер сам повторяет запросы, а для видеоряда можно задать запасной источник (`visuals.fallback`).
- Самый надёжный вариант без лимитов — всё локально: Ollama + `visuals.source: local` + Silero или Edge.
- Автопубликацию в соцсети конвейер пока не делает: `post.txt` содержит готовый текст для загрузки. Её можно добавить отдельным шагом, например через YouTube Data API или сервисы вроде Blotato.

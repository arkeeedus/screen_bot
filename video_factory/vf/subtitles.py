"""Субтитры в стиле TikTok (ASS): крупные слова, подсветка текущего слова, плашка-хук сверху."""


def _ass_color(hex_color, alpha=0):
    h = hex_color.lstrip("#")
    r, g, b = h[0:2], h[2:4], h[4:6]
    return f"&H{alpha:02X}{b}{g}{r}".upper()


def _ts(t):
    t = max(0.0, t)
    h = int(t // 3600)
    m = int(t % 3600 // 60)
    s = t % 60
    return f"{h}:{m:02d}:{s:05.2f}"


def _clean(word, upper):
    word = word.replace("{", "(").replace("}", ")").replace("\\", "/").strip(" ,.;:«»\"")
    return word.upper() if upper else word


def _chunks(words, n):
    """Группы по n слов; группа рвётся на конце предложения и на границе сцены."""
    chunk = []
    for i, w in enumerate(words):
        chunk.append(w)
        scene_ends = i + 1 < len(words) and words[i + 1][3] != w[3]
        if len(chunk) >= n or scene_ends or w[0].rstrip()[-1:] in ".!?…":
            yield chunk
            chunk = []
    if chunk:
        yield chunk


def build_ass(words, total_duration, hook_text, config, width, height):
    sub = config.get("subtitles", {})
    hook = config.get("hook", {})
    font = sub.get("font", "Arial Black")
    upper = sub.get("uppercase", True)
    base = _ass_color(sub.get("color", "#FFFFFF"))
    hl = _ass_color(sub.get("highlight_color", "#FFE600"))
    margin_v = int(height * (1 - sub.get("position_y", 0.68)))

    lines = [
        "[Script Info]", "ScriptType: v4.00+", f"PlayResX: {width}", f"PlayResY: {height}",
        "WrapStyle: 0", "ScaledBorderAndShadow: yes", "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, "
        "Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, "
        "MarginL, MarginR, MarginV, Encoding",
        f"Style: Sub,{font},{sub.get('font_size', 92)},{base},{base},&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,"
        f"{sub.get('outline', 6)},2,2,60,60,{margin_v},1",
        f"Style: Hook,{font},{hook.get('font_size', 64)},&H00000000,&H00000000,&H00FFFFFF,&H00FFFFFF,-1,0,0,0,"
        f"100,100,0,0,3,18,0,8,80,80,{int(height * 0.09)},1",
        "", "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
    ]

    if hook.get("enabled", True) and hook_text:
        end = hook.get("seconds") or total_duration
        text = hook_text.replace("{", "(").replace("}", ")").replace("\n", "\\N")
        lines.append(f"Dialogue: 1,{_ts(0)},{_ts(end)},Hook,,0,0,0,,{text}")

    if sub.get("enabled", True):
        chunks = list(_chunks(words, sub.get("words_per_chunk", 3)))
        for ci, chunk in enumerate(chunks):
            next_start = chunks[ci + 1][0][1] if ci + 1 < len(chunks) else total_duration
            chunk_end = chunk[-1][2]
            if next_start - chunk_end < 0.4:  # без мигания между группами
                chunk_end = next_start
            for wi, (_, start, *_) in enumerate(chunk):
                end = chunk[wi + 1][1] if wi + 1 < len(chunk) else chunk_end
                if end <= start:
                    continue
                parts = []
                for wj, (w, *_) in enumerate(chunk):
                    txt = _clean(w, upper)
                    parts.append(f"{{\\c{hl}}}{txt}{{\\c{base}}}" if wj == wi else txt)
                pop = "{\\fscx112\\fscy112\\t(0,90,\\fscx100\\fscy100)}" if wi == 0 else ""
                lines.append(f"Dialogue: 0,{_ts(start)},{_ts(end)},Sub,,0,0,0,,{pop}{' '.join(parts)}")
    return "\n".join(lines) + "\n"

"""
metadata.py — free, heuristic title/description/tag generation for a rendered
clip, built entirely from its own transcript text. No external API calls, so
no extra cost and no extra account to set up.
"""

import re
from collections import Counter
from typing import Dict, List

STOPWORDS = {
    "the", "a", "an", "and", "or", "but", "is", "are", "was", "were", "be",
    "been", "to", "of", "in", "on", "for", "with", "as", "at", "by", "this",
    "that", "it", "its", "i", "you", "we", "they", "he", "she", "so", "just",
    "like", "get", "got", "if", "not", "do", "does", "did", "have", "has",
    "had", "from", "can", "will", "would", "could", "about", "what", "which",
    "who", "when", "where", "there", "here", "up", "out", "all", "your", "my",
    "и", "в", "на", "с", "по", "для", "это", "что", "как", "не", "а", "но",
    "то", "же", "бы", "он", "она", "они", "мы", "вы", "я", "у", "из", "от",
    "к", "за", "до", "при", "или", "есть", "быть", "был", "было",
}

WORD_RE = re.compile(r"[\w'-]+", re.UNICODE)


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def generate_title(hook: str, text: str, max_len: int = 90) -> str:
    base = _clean(hook) or _clean(text)
    base = base.rstrip(".").strip()
    if not base:
        return "Clip"
    if len(base) > max_len:
        base = base[:max_len].rsplit(" ", 1)[0] + "…"
    return base[0].upper() + base[1:]


def extract_tags(text: str, max_tags: int = 15) -> List[str]:
    words = [w.lower() for w in WORD_RE.findall(text)]
    words = [w for w in words if len(w) > 2 and w not in STOPWORDS and not w.isdigit()]
    counts = Counter(words)
    tags: List[str] = []
    for w, _ in counts.most_common(max_tags * 2):
        tag = re.sub(r"[^\w]", "", w)
        if tag and tag not in tags:
            tags.append(tag)
        if len(tags) >= max_tags:
            break
    return tags


def generate_description(text: str, source_title: str = "", source_url: str = "", max_len: int = 1500) -> str:
    text = _clean(text)
    body = text[:400]
    if len(text) > 400:
        body = body.rsplit(" ", 1)[0] + "…"

    lines = [body]
    if source_title or source_url:
        lines.append("")
        credit = f"Full video: {source_title}" if source_title else "Full video:"
        if source_url:
            credit += f"\n{source_url}"
        lines.append(credit)

    tags = extract_tags(text, max_tags=8)
    if tags:
        lines.append("")
        lines.append(" ".join(f"#{t}" for t in tags))

    return "\n".join(lines)[:max_len]


def build_metadata(clip: Dict, source_title: str = "", source_url: str = "") -> Dict:
    hook = clip.get("hook", "")
    text = clip.get("text", "")
    return {
        "title": generate_title(hook, text),
        "description": generate_description(text, source_title, source_url),
        "tags": extract_tags(text),
    }

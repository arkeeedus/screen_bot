"""
clip_factory.py — turn a long-form video you have the rights to use into a batch
of short vertical clips with burned-in word-by-word captions and a hook overlay,
ready to submit to a clipping campaign (e.g. on Whop) or post directly.

Only point this at video you're actually allowed to re-cut and republish: your
own recordings, or source material a campaign brief has licensed to clippers.
It does not bypass anything — it automates the same steps described in
README_CLIP_FACTORY.md: download -> find strong moments in the transcript ->
render vertical clips with captions.

Pipeline:
    fetch  - download the source video + its captions with yt-dlp
    plan   - score the transcript and propose N clip windows (clips_plan.json)
    render - cut each planned window with ffmpeg: vertical crop, word captions,
             hook text overlay for the first 2 seconds
    run    - fetch + plan + render in one go

Requires the `yt-dlp` Python package and an `ffmpeg` binary on PATH.
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass, asdict
from typing import List

STRONG_WORDS = {
    "secret", "mistake", "never", "always", "actually", "important", "stop",
    "why", "how", "best", "worst", "free", "money", "warning", "truth",
    "biggest", "nobody", "everyone", "wrong", "right", "million", "billion",
    "секрет", "никогда", "ошибка", "важно", "деньги", "бесплатно", "как",
    "почему", "остановись", "лучший", "худший", "миллион", "миллиард",
    "правда", "главное", "никто", "все", "нельзя", "нужно",
}

SENTENCE_END = re.compile(r"[.!?]$")
VTT_TIME = re.compile(r"(\d\d):(\d\d):(\d\d)\.(\d\d\d)")
INLINE_TAG = re.compile(r"<(\d\d:\d\d:\d\d\.\d\d\d)>")
TAG_STRIP = re.compile(r"</?c[^>]*>")


@dataclass
class Word:
    text: str
    start: float
    end: float


@dataclass
class Sentence:
    words: List[Word]

    @property
    def start(self) -> float:
        return self.words[0].start

    @property
    def end(self) -> float:
        return self.words[-1].end

    @property
    def duration(self) -> float:
        return self.end - self.start

    @property
    def text(self) -> str:
        return " ".join(w.text for w in self.words)


@dataclass
class ClipPlan:
    index: int
    start: float
    end: float
    duration: float
    score: float
    text: str
    hook: str


def _vtt_time_to_seconds(m: "re.Match") -> float:
    h, mi, s, ms = m.groups()
    return int(h) * 3600 + int(mi) * 60 + int(s) + int(ms) / 1000.0


def parse_vtt_words(vtt_text: str) -> List[Word]:
    """Extract a flat, deduplicated, time-ordered list of words from a WebVTT
    transcript. Uses YouTube's inline per-word timestamp tags when present
    (auto-generated captions), and falls back to spreading a cue's words
    evenly across its start/end when they aren't (manually uploaded captions).
    """
    blocks = re.split(r"\n\s*\n", vtt_text.strip())
    seen = {}
    for block in blocks:
        lines = [l for l in block.splitlines() if l.strip()]
        if not lines:
            continue
        timing = None
        text_lines = []
        for line in lines:
            times = VTT_TIME.findall(line)
            if "-->" in line and len(times) >= 2:
                start = _vtt_time_to_seconds(VTT_TIME.search(line))
                end_match = list(VTT_TIME.finditer(line))[1]
                end = _vtt_time_to_seconds(end_match)
                timing = (start, end)
            elif timing is not None:
                text_lines.append(line)
        if timing is None or not text_lines:
            continue

        block_start, block_end = timing
        text = " ".join(text_lines)
        text = TAG_STRIP.sub("", text)

        if INLINE_TAG.search(text):
            parts = INLINE_TAG.split(text)
            tag_times = [block_start] + [
                _vtt_time_to_seconds(VTT_TIME.search(t)) for t in INLINE_TAG.findall(text)
            ]
            for i, chunk in enumerate(parts):
                words = chunk.split()
                if not words:
                    continue
                seg_start = tag_times[i]
                seg_end = tag_times[i + 1] if i + 1 < len(tag_times) else block_end
                _distribute_words(words, seg_start, max(seg_end, seg_start + 0.01), seen)
        else:
            words = text.split()
            _distribute_words(words, block_start, block_end, seen)

    ordered = sorted(seen.values(), key=lambda w: w.start)
    return ordered


def _distribute_words(words: List[str], start: float, end: float, seen: dict) -> None:
    if not words:
        return
    step = max(end - start, 0.01) / len(words)
    for i, w in enumerate(words):
        w_start = start + i * step
        w_end = w_start + step
        key = (w.lower(), round(w_start, 1))
        if key not in seen:
            seen[key] = Word(text=w, start=w_start, end=w_end)


def words_to_sentences(words: List[Word], pause_gap: float = 1.1) -> List[Sentence]:
    sentences: List[Sentence] = []
    current: List[Word] = []
    for w in words:
        if current and (w.start - current[-1].end > pause_gap):
            sentences.append(Sentence(current))
            current = []
        current.append(w)
        if SENTENCE_END.search(w.text):
            sentences.append(Sentence(current))
            current = []
    if current:
        sentences.append(Sentence(current))
    return sentences


def score_sentence(s: Sentence) -> float:
    score = 0.0
    lowered = s.text.lower()
    for w in STRONG_WORDS:
        if w in lowered:
            score += 1.0
    if "?" in s.text:
        score += 2.0
    if re.search(r"\d", s.text):
        score += 1.5
    if "%" in s.text or "$" in s.text:
        score += 1.0
    if 3.0 <= s.duration <= 12.0:
        score += 0.5
    return score


def find_segments(
    words: List[Word], count: int, min_dur: float, max_dur: float
) -> List[ClipPlan]:
    sentences = words_to_sentences(words)
    for s in sentences:
        s.score = score_sentence(s)  # type: ignore[attr-defined]

    candidates = []
    n = len(sentences)
    for i in range(n):
        dur = 0.0
        score = 0.0
        for j in range(i, n):
            dur = sentences[j].end - sentences[i].start
            score += sentences[j].score  # type: ignore[attr-defined]
            if dur > max_dur:
                break
            if dur >= min_dur:
                candidates.append((score, i, j, dur))

    candidates.sort(key=lambda c: c[0], reverse=True)

    chosen = []
    used_ranges: List[tuple] = []
    for score, i, j, dur in candidates:
        start, end = sentences[i].start, sentences[j].end
        if any(not (end <= u_start or start >= u_end) for u_start, u_end in used_ranges):
            continue
        used_ranges.append((start, end))
        text = " ".join(sentences[k].text for k in range(i, j + 1))
        hook_words = text.split()[:10]
        hook = " ".join(hook_words)
        if len(hook) < len(text):
            hook += "..."
        chosen.append(
            ClipPlan(
                index=len(chosen),
                start=round(start, 2),
                end=round(end, 2),
                duration=round(dur, 2),
                score=round(score, 2),
                text=text,
                hook=hook.upper(),
            )
        )
        if len(chosen) >= count:
            break

    chosen.sort(key=lambda c: c.start)
    for idx, c in enumerate(chosen):
        c.index = idx
    return chosen


def cmd_fetch(args: argparse.Namespace) -> None:
    if shutil.which("yt-dlp") is None:
        try:
            import yt_dlp  # noqa: F401
        except ImportError:
            print("yt-dlp not found. Install it with: pip install yt-dlp")
            sys.exit(1)

    os.makedirs(args.workdir, exist_ok=True)
    video_out = os.path.join(args.workdir, "source.%(ext)s")
    cmd = [
        sys.executable, "-m", "yt_dlp",
        "-f", "bv*[height<=1080]+ba/b[height<=1080]",
        "--merge-output-format", "mp4",
        "--write-auto-subs", "--write-subs",
        "--sub-langs", args.lang,
        "--convert-subs", "vtt",
        "-o", video_out,
        args.url,
    ]
    print("Running:", " ".join(cmd))
    subprocess.run(cmd, check=True)
    print(f"Downloaded to {args.workdir}/")


def _find_transcript(workdir: str, lang: str) -> str:
    for name in os.listdir(workdir):
        if name.startswith("source") and name.endswith(f"{lang}.vtt"):
            return os.path.join(workdir, name)
    for name in os.listdir(workdir):
        if name.endswith(".vtt"):
            return os.path.join(workdir, name)
    raise FileNotFoundError(f"No .vtt transcript found in {workdir}. Run `fetch` first.")


def cmd_plan(args: argparse.Namespace) -> None:
    vtt_path = _find_transcript(args.workdir, args.lang)
    with open(vtt_path, encoding="utf-8") as f:
        words = parse_vtt_words(f.read())
    if not words:
        print(f"No captions could be parsed from {vtt_path}")
        sys.exit(1)

    plans = find_segments(words, args.clips, args.min, args.max)
    plan_path = os.path.join(args.workdir, "clips_plan.json")
    with open(plan_path, "w", encoding="utf-8") as f:
        json.dump([asdict(p) for p in plans], f, ensure_ascii=False, indent=2)

    print(f"Planned {len(plans)} clip(s) -> {plan_path}")
    print("Review and edit the hooks/timestamps before rendering:\n")
    for p in plans:
        print(f"  [{p.index}] {p.start:>7.1f}s - {p.end:>7.1f}s ({p.duration:.1f}s)  {p.hook}")


def _escape_ffmpeg_path(path: str) -> str:
    path = os.path.abspath(path).replace("\\", "/")
    path = path.replace(":", "\\:")
    return path


def _escape_drawtext(text: str) -> str:
    return (
        text.replace("\\", "\\\\\\\\")
        .replace(":", "\\:")
        .replace("'", "\u2019")
        .replace("%", "\\%")
    )


def _write_ass(words: List[Word], start: float, end: float, out_path: str, chunk_size: int = 3) -> None:
    clip_words = [w for w in words if w.start >= start and w.start < end]

    def fmt(t: float) -> str:
        t = max(t, 0.0)
        h = int(t // 3600)
        m = int((t % 3600) // 60)
        s = t % 60
        return f"{h}:{m:02d}:{s:05.2f}"

    header = (
        "[Script Info]\nScriptType: v4.00+\nPlayResX: 1080\nPlayResY: 1920\n\n"
        "[V4+ Styles]\n"
        "Format: Name, Fontname, Fontsize, PrimaryColour, OutlineColour, "
        "BackColour, Bold, Outline, Shadow, Alignment, MarginL, MarginR, MarginV\n"
        "Style: Default,Arial,90,&H00FFFFFF,&H00000000,&H80000000,1,4,0,2,60,60,220\n\n"
        "[Events]\n"
        "Format: Layer, Start, End, Style, Text\n"
    )
    lines = []
    for i in range(0, len(clip_words), chunk_size):
        chunk = clip_words[i:i + chunk_size]
        rel_start = chunk[0].start - start
        rel_end = chunk[-1].end - start
        text = " ".join(w.text for w in chunk).upper().replace("\n", " ")
        lines.append(f"Dialogue: 0,{fmt(rel_start)},{fmt(rel_end)},Default,{text}")

    with open(out_path, "w", encoding="utf-8") as f:
        f.write(header + "\n".join(lines) + "\n")


def cmd_render(args: argparse.Namespace) -> None:
    if shutil.which("ffmpeg") is None:
        print("ffmpeg not found on PATH. Install it (e.g. `winget install Gyan.FFmpeg`).")
        sys.exit(1)

    plan_path = os.path.join(args.workdir, "clips_plan.json")
    with open(plan_path, encoding="utf-8") as f:
        plans = json.load(f)

    video_path = None
    for name in os.listdir(args.workdir):
        if name.startswith("source.") and name.split(".")[-1] in ("mp4", "mkv", "webm"):
            video_path = os.path.join(args.workdir, name)
            break
    if video_path is None:
        raise FileNotFoundError(f"No source video found in {args.workdir}. Run `fetch` first.")

    vtt_path = _find_transcript(args.workdir, args.lang)
    with open(vtt_path, encoding="utf-8") as f:
        words = parse_vtt_words(f.read())

    out_dir = os.path.join(args.workdir, "clips")
    os.makedirs(out_dir, exist_ok=True)

    if args.only is not None:
        plans = [p for p in plans if p["index"] == args.only]

    for p in plans:
        start, end = p["start"], p["end"]
        idx = p["index"]
        ass_path = os.path.join(out_dir, f"clip_{idx:02d}.ass")
        _write_ass(words, start, end, ass_path)

        out_path = os.path.join(out_dir, f"clip_{idx:02d}.mp4")
        hook = _escape_drawtext(p["hook"])
        ass_escaped = _escape_ffmpeg_path(ass_path)
        vf = (
            "crop=ih*9/16:ih,scale=1080:1920,"
            f"subtitles='{ass_escaped}',"
            f"drawtext=fontfile='{_escape_ffmpeg_path(args.fontfile)}':"
            f"text='{hook}':fontsize=64:fontcolor=white:borderw=3:bordercolor=black:"
            "x=(w-text_w)/2:y=120:enable='between(t,0,2)'"
        )
        cmd = [
            "ffmpeg", "-y",
            "-ss", str(start), "-to", str(end), "-i", video_path,
            "-vf", vf,
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
            "-c:a", "aac", "-b:a", "128k",
            out_path,
        ]
        print(f"Rendering clip {idx}: {out_path}")
        subprocess.run(cmd, check=True)

    print(f"\nDone. {len(plans)} clip(s) in {out_dir}/")


def cmd_run(args: argparse.Namespace) -> None:
    cmd_fetch(args)
    cmd_plan(args)
    args.only = None
    cmd_render(args)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Download a video and turn it into captioned vertical clips."
    )
    sub = parser.add_subparsers(dest="command", required=True)

    def add_common(p):
        p.add_argument("--workdir", default="clip_output", help="Output folder")
        p.add_argument("--lang", default="en", help="Caption language code")

    p_fetch = sub.add_parser("fetch", help="Download source video + captions")
    add_common(p_fetch)
    p_fetch.add_argument("url", help="Video URL you have the rights to use")
    p_fetch.set_defaults(func=cmd_fetch)

    p_plan = sub.add_parser("plan", help="Score the transcript and propose clip windows")
    add_common(p_plan)
    p_plan.add_argument("--clips", type=int, default=7)
    p_plan.add_argument("--min", type=float, default=25.0, help="Min clip length (s)")
    p_plan.add_argument("--max", type=float, default=60.0, help="Max clip length (s)")
    p_plan.set_defaults(func=cmd_plan)

    p_render = sub.add_parser("render", help="Render clips from clips_plan.json")
    add_common(p_render)
    p_render.add_argument("--fontfile", default="/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf")
    p_render.add_argument("--only", type=int, default=None, help="Render a single clip index")
    p_render.set_defaults(func=cmd_render)

    p_run = sub.add_parser("run", help="fetch + plan + render in one go")
    add_common(p_run)
    p_run.add_argument("url")
    p_run.add_argument("--clips", type=int, default=7)
    p_run.add_argument("--min", type=float, default=25.0)
    p_run.add_argument("--max", type=float, default=60.0)
    p_run.add_argument("--fontfile", default="/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf")
    p_run.set_defaults(func=cmd_run)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()

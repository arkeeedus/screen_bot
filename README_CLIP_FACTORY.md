# clip_factory

Turns one long video into a batch of short vertical clips with burned-in
captions and a 2-second hook overlay — the pipeline discussed for submitting
to legitimate clipping campaigns (e.g. on Whop) or posting directly.

**Only run this on video you actually have the rights to re-cut and
republish**: your own recordings, or source material a campaign brief has
licensed to clippers. It does not get around copyright, and it does not
replace reading the campaign's brief for banned phrases or formatting rules.

## What it does

1. `fetch` — downloads the video and its captions with `yt-dlp`.
2. `plan` — scores the transcript (questions, numbers, emphasis words) and
   proposes N non-overlapping clip windows into `clips_plan.json`. **Review
   and edit this file before rendering** — the scoring is a heuristic, not a
   guarantee of a good clip, and hooks are auto-generated from the first
   sentence so you'll usually want to rewrite them.
3. `render` — for each planned window: crops to 9:16, burns in word-by-word
   captions built from the transcript, and overlays the hook text for the
   first 2 seconds. Outputs to `clip_output/clips/clip_00.mp4`, etc.

Caption timing comes from YouTube's transcript, not a fresh speech-to-text
pass, so it can be off by a few tenths of a second — check a clip or two
before batch-publishing.

## Install

```bash
pip install yt-dlp
# ffmpeg must be on PATH
#   Windows: winget install Gyan.FFmpeg
#   macOS:   brew install ffmpeg
#   Linux:   apt install ffmpeg
```

## Usage

All-in-one:

```bash
python clip_factory.py run "https://youtube.com/watch?v=..." \
    --clips 7 --min 25 --max 60 --lang en \
    --fontfile "C:\Windows\Fonts\arial.ttf"
```

Step by step (recommended, so you can review the plan before rendering):

```bash
python clip_factory.py fetch "https://youtube.com/watch?v=..." --lang en
python clip_factory.py plan --clips 7 --min 25 --max 60 --lang en
# edit clip_output/clips_plan.json: fix hooks, drop/adjust windows
python clip_factory.py render --fontfile "C:\Windows\Fonts\arial.ttf"

# re-render just one clip after tweaking its window in clips_plan.json
python clip_factory.py render --only 2
```

`--fontfile` needs to point at a font that covers the script you're
captioning in (e.g. a standard Windows font for Cyrillic).

## After rendering

Upload the clips yourself to whichever platform the campaign brief calls
for, and submit the links there. This tool doesn't post or submit anything
on its own.

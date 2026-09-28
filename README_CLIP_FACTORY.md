# clip_factory

Turns video into short vertical clips with burned-in captions and a
2-second hook overlay, and can optionally publish them to YouTube, TikTok
and Instagram Reels with a generated title/description/tags.

**Only run this on video you actually have the rights to re-cut and
republish**: your own recordings, or source material a campaign brief has
licensed to clippers. It does not get around copyright, and it does not
replace reading a campaign's brief for banned phrases or formatting rules.
Auto-publishing is opt-in and defaults to private/draft on every platform —
see **Safety defaults** below.

## Two ways to use it

- **`clip_factory.py`** — clip a single video you give it a URL for.
  Good for a one-off, or for reviewing the pipeline before automating it.
- **`auto_publish.py`** — the full pipeline: watch a list of channels and/or
  direct links (`sources.json`), skip videos already processed, clip each
  new one, generate metadata, and (if you pass `--auto-publish`) post to
  whichever platforms you've enabled in `publish_config.json`.

`auto_publish.py` calls into `clip_factory.py`, `metadata.py` and
`sources.py` — all of it lives in this repo, nothing is hidden.

## What the pipeline does

1. **fetch** — downloads a video and its captions with `yt-dlp`.
2. **plan** — scores the transcript (questions, numbers, emphasis words) and
   proposes N non-overlapping clip windows into `clips_plan.json`.
3. **render** — for each window: crops to 9:16, burns in word-by-word
   captions, overlays the hook text for the first 2 seconds.
4. **metadata** (`auto_publish.py` only) — generates a title, description
   and tag list for each clip from its own transcript text, no external API,
   no extra cost. Written into `clips_plan.json` alongside each clip.
5. **publish** (`auto_publish.py` only, opt-in) — uploads each clip to the
   platforms you've enabled.

Caption timing comes from the video's own transcript, not a fresh
speech-to-text pass, so it can be off by a few tenths of a second, and the
heuristic scoring/metadata are a starting point, not a guarantee of a good
clip. **Review `clips_plan.json` before publishing** — that's what it's for.

## Install

```bash
pip install -r requirements-clip-factory.txt
# ffmpeg must be on PATH
#   Windows: winget install Gyan.FFmpeg
#   macOS:   brew install ffmpeg
#   Linux:   apt install ffmpeg
```

## clip_factory.py — single video

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

## auto_publish.py — watch sources, clip, publish

```bash
cp sources.example.json sources.json
cp publish_config.example.json publish_config.json
# edit both — see below
```

`sources.json`:

```json
{
  "direct": ["https://www.youtube.com/watch?v=VIDEO_ID"],
  "channels": ["https://www.youtube.com/@your_channel_handle"],
  "max_per_channel_check": 5
}
```

- `direct` — specific video URLs to process once each.
- `channels` — channel URLs to check; the tool lists each channel's most
  recent `max_per_channel_check` uploads and processes any it hasn't seen
  before. Only add channels you have the rights to re-cut content from.
- Already-processed video IDs are tracked in
  `<workdir>/seen.json` so re-running never reprocesses the same video.

Dry run — clip and generate metadata, publish nothing:

```bash
python auto_publish.py run --sources sources.json --config publish_config.json
```

Review `auto_publish_output/<video_id>/clips/` and the `metadata` block in
each `clips_plan.json`. When you're happy, enable the platforms you want in
`publish_config.json` (`"enabled": true`) and add `--auto-publish`:

```bash
python auto_publish.py run --sources sources.json --config publish_config.json --auto-publish
```

Run it again later (e.g. from Task Scheduler / cron) and it'll only process
videos it hasn't seen yet.

## Safety defaults

Nothing goes public on its own:

- Without `--auto-publish`, nothing is uploaded anywhere — clips just sit on
  disk for you to review.
- **YouTube** defaults to `privacy: "private"`. Change to `"unlisted"` or
  `"public"` in `publish_config.json` once you trust the output.
- **TikTok** defaults to `privacy: "SELF_ONLY"` (draft, visible only to you)
  — this is also the only option TikTok allows until they audit your app for
  public posting.
- **Instagram** has no draft option in the Graph API, so it stays disabled
  (`"enabled": false`) until you deliberately turn it on and give it a
  public URL to fetch the clip from (see below).

## Platform setup (all from scratch)

### YouTube

1. https://console.cloud.google.com/ → create a project.
2. APIs & Services → Library → enable **YouTube Data API v3**.
3. APIs & Services → OAuth consent screen → External → add yourself as a
   test user (fine for personal use — full Google review is only needed to
   let *other* people authorize your app).
4. APIs & Services → Credentials → Create Credentials → OAuth client ID →
   Application type **Desktop app**. Download the JSON, save it as
   `youtube_client_secret.json` in this folder.
5. Set `"client_secret_path": "youtube_client_secret.json"` in
   `publish_config.json` and `"enabled": true`.
6. First publish opens a browser for you to log in and approve; the token
   is cached to `youtube_token.json` so you won't need to log in again.

### TikTok

1. https://developers.tiktok.com/ → register an app → add the
   **Content Posting API** product.
2. Note the app's Client Key and Client Secret.
3. In the app's settings, register a Redirect URI, e.g.
   `http://localhost:8722/callback`.
4. Run:
   ```bash
   python publish_tiktok.py authorize --client-key YOUR_KEY --client-secret YOUR_SECRET
   ```
   This opens a browser for you to log in and approve; the token is cached
   to `tiktok_token.json`.
5. Fill in `client_key`, `client_secret`, `redirect_uri` and set
   `"enabled": true` in `publish_config.json`.
6. Until TikTok audits your app, posts can only be `SELF_ONLY` (private
   drafts) — request the audit from the developer portal once you're ready
   to post publicly.

### Instagram Reels

1. Convert your Instagram account to a Business or Creator account and link
   it to a Facebook Page (Instagram app → Settings → Account type).
2. https://developers.facebook.com/ → create an app → add the
   **Instagram Graph API** product.
3. Generate a long-lived access token with the `instagram_content_publish`
   permission (Graph API Explorer is fine for personal use; a full OAuth
   flow is needed if this will run unattended for a long time, since tokens
   expire).
4. Find your `ig_user_id`: `GET /me/accounts` (lists your Pages), then
   `GET /{page_id}?fields=instagram_business_account`.
5. **Instagram fetches the video from a public URL — it does not accept a
   file upload.** Host your rendered clips somewhere reachable (your own
   site, an S3/R2 bucket, etc.) and set `public_video_base_url` in
   `publish_config.json` to that base URL.
6. Set the access token as an environment variable (default name
   `IG_ACCESS_TOKEN`, or change `access_token_env`), set `ig_user_id`, and
   set `"enabled": true`.

## After rendering (no publishing configured)

Upload the clips yourself to whichever platform the campaign brief calls
for. This tool doesn't post or submit anything unless you explicitly enable
a platform and pass `--auto-publish`.

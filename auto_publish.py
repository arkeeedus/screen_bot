"""
auto_publish.py — the full pipeline: find new source videos (direct links
and/or monitored channels), turn each into vertical clips via clip_factory,
generate a title/description/tags for every clip from its own transcript,
and optionally publish to YouTube/TikTok/Instagram.

Safety defaults: nothing is posted publicly on its own. `run` without
--auto-publish only fetches, renders, and writes metadata for you to review.
Even with --auto-publish, each platform defaults to a private/draft
visibility (YouTube: private, TikTok: SELF_ONLY) so a clip never goes live
without you reviewing it and flipping it public yourself — Instagram has no
"draft" option in the Graph API, so it stays disabled until you set
public_video_base_url yourself in publish_config.json.

Usage:
    python auto_publish.py run --sources sources.json --config publish_config.json
    python auto_publish.py run --sources sources.json --config publish_config.json --auto-publish

See README_CLIP_FACTORY.md for the sources.json / publish_config.json formats
and per-platform credential setup.
"""

import argparse
import json
import os

import clip_factory as cf
import metadata as meta
import sources as src


def process_video(video_url: str, workdir: str, args: argparse.Namespace, source_title: str = None):
    fetch_args = argparse.Namespace(url=video_url, workdir=workdir, lang=args.lang)
    cf.cmd_fetch(fetch_args)

    plan_args = argparse.Namespace(workdir=workdir, lang=args.lang, clips=args.clips, min=args.min, max=args.max)
    cf.cmd_plan(plan_args)

    render_args = argparse.Namespace(workdir=workdir, lang=args.lang, fontfile=args.fontfile, only=None)
    cf.cmd_render(render_args)

    plan_path = os.path.join(workdir, "clips_plan.json")
    with open(plan_path, encoding="utf-8") as f:
        plans = json.load(f)

    credit = source_title or video_url
    for p in plans:
        p["metadata"] = meta.build_metadata(p, source_title=credit, source_url=video_url)
    with open(plan_path, "w", encoding="utf-8") as f:
        json.dump(plans, f, ensure_ascii=False, indent=2)

    return plans


def publish_clip(clip_path: str, md: dict, pub_config: dict) -> dict:
    results = {}

    yt_cfg = pub_config.get("youtube", {})
    if yt_cfg.get("enabled"):
        import publish_youtube
        video_id = publish_youtube.publish(
            clip_path, md["title"], md["description"], md["tags"],
            yt_cfg["client_secret_path"], yt_cfg["token_path"],
            privacy=yt_cfg.get("privacy", "private"),
            category_id=yt_cfg.get("category_id", "22"),
        )
        results["youtube"] = video_id

    tk_cfg = pub_config.get("tiktok", {})
    if tk_cfg.get("enabled"):
        import publish_tiktok
        publish_id, status = publish_tiktok.publish(
            clip_path, md["title"], tk_cfg["client_key"], tk_cfg["client_secret"],
            tk_cfg["token_path"], privacy=tk_cfg.get("privacy", "SELF_ONLY"),
        )
        results["tiktok"] = {"publish_id": publish_id, "status": status}

    ig_cfg = pub_config.get("instagram", {})
    if ig_cfg.get("enabled"):
        base = ig_cfg.get("public_video_base_url", "").rstrip("/")
        if not base:
            print("  Skipping Instagram: set public_video_base_url in publish_config.json"
                  " (Instagram fetches the clip from a public URL, it can't take a file upload).")
        else:
            import publish_instagram
            video_url = f"{base}/{os.path.basename(clip_path)}"
            access_token = os.environ.get(ig_cfg.get("access_token_env", "IG_ACCESS_TOKEN"), "")
            media_id = publish_instagram.publish(video_url, md["description"], ig_cfg["ig_user_id"], access_token)
            results["instagram"] = media_id

    return results


def cmd_run(args: argparse.Namespace) -> None:
    sources_cfg = src.load_config(args.sources)
    pub_config = {}
    if os.path.exists(args.config):
        with open(args.config, encoding="utf-8") as f:
            pub_config = json.load(f)
    elif args.auto_publish:
        print(f"--auto-publish was set but {args.config} doesn't exist; nothing will be published.")

    queue = src.resolve_new_sources(sources_cfg, args.workdir)
    if not queue:
        print("No new source videos found.")
        return

    for item in queue:
        video_url = item["url"]
        video_workdir = os.path.join(args.workdir, item["id"] or "video")
        print(f"\n=== Processing {video_url} -> {video_workdir} ===")
        plans = process_video(video_url, video_workdir, args, source_title=item.get("title"))

        clips_dir = os.path.join(video_workdir, "clips")
        for p in plans:
            clip_path = os.path.join(clips_dir, f"clip_{p['index']:02d}.mp4")
            md = p["metadata"]
            print(f"  clip {p['index']}: {md['title']}")
            if not os.path.exists(clip_path):
                print(f"    WARNING: rendered file missing: {clip_path}")
                continue
            if args.auto_publish:
                results = publish_clip(clip_path, md, pub_config)
                print(f"    published: {results}")
            else:
                print("    rendered, not published (pass --auto-publish once you've reviewed it)")

        src.mark_seen(args.workdir, item["id"])

    print(f"\nDone. Review clips under {args.workdir}/<video_id>/clips/ before publishing.")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Find, clip, and optionally publish new source videos.")
    sub = parser.add_subparsers(dest="command", required=True)

    p_run = sub.add_parser("run", help="Resolve sources, render clips, optionally publish")
    p_run.add_argument("--sources", default="sources.json")
    p_run.add_argument("--config", default="publish_config.json")
    p_run.add_argument("--workdir", default="auto_publish_output")
    p_run.add_argument("--lang", default="en")
    p_run.add_argument("--clips", type=int, default=7)
    p_run.add_argument("--min", type=float, default=25.0)
    p_run.add_argument("--max", type=float, default=60.0)
    p_run.add_argument("--fontfile", default="/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf")
    p_run.add_argument(
        "--auto-publish", action="store_true",
        help="Actually publish to enabled platforms (still private/draft by default per platform)",
    )
    p_run.set_defaults(func=cmd_run)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()

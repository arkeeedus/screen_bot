"""
publish_instagram.py — publish a clip as an Instagram Reel via the Instagram
Graph API.

One-time setup:
1. Convert your Instagram account to a Business or Creator account and link
   it to a Facebook Page (Instagram app -> Settings -> Account type).
2. https://developers.facebook.com/ -> create an app -> add the
   "Instagram Graph API" product.
3. Generate a long-lived access token with the instagram_content_publish
   permission (Graph API Explorer for personal use; a full OAuth flow is
   needed if this will run unattended for a long time, since tokens expire).
4. Find your ig_user_id: GET /me/accounts (lists your Pages), then
   GET /{page_id}?fields=instagram_business_account.

Important: Instagram fetches the video FROM a public URL you provide — it
does not accept a direct file upload. Host the rendered clip somewhere
reachable (your own site, an S3/R2 bucket, etc.) before calling publish(),
and pass that public URL in.

Requires: pip install requests
"""

import time

import requests

GRAPH = "https://graph.facebook.com/v19.0"


def publish(video_url: str, caption: str, ig_user_id: str, access_token: str) -> str:
    create = requests.post(
        f"{GRAPH}/{ig_user_id}/media",
        data={
            "media_type": "REELS",
            "video_url": video_url,
            "caption": caption[:2200],
            "access_token": access_token,
        },
    )
    create.raise_for_status()
    container_id = create.json()["id"]

    for _ in range(30):
        status = requests.get(
            f"{GRAPH}/{container_id}",
            params={"fields": "status_code", "access_token": access_token},
        ).json()
        code = status.get("status_code")
        if code == "FINISHED":
            break
        if code == "ERROR":
            raise RuntimeError(f"Instagram container failed to process: {status}")
        time.sleep(5)
    else:
        raise TimeoutError("Instagram container did not finish processing in time")

    publish_resp = requests.post(
        f"{GRAPH}/{ig_user_id}/media_publish",
        data={"creation_id": container_id, "access_token": access_token},
    )
    publish_resp.raise_for_status()
    media_id = publish_resp.json()["id"]
    print(f"Instagram Reel published: media_id={media_id}")
    return media_id

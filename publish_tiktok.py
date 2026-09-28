"""
publish_tiktok.py — post a clip to TikTok via the Content Posting API
(direct post, FILE_UPLOAD source).

One-time setup:
1. https://developers.tiktok.com/ -> register an app, add the "Content
   Posting API" product.
2. Note the app's Client Key + Client Secret.
3. In the app's settings, register a Redirect URI, e.g.
   http://localhost:8722/callback.
4. Run: python publish_tiktok.py authorize --client-key ... --client-secret ...
   This opens a browser, you log in and approve, and the token is cached to
   tiktok_token.json.

Important: until TikTok reviews and approves your app for public posting,
unaudited apps can only post as SELF_ONLY (a private draft visible just to
you) — that's this module's default. Widening that to public posting requires
TikTok's app audit, which you request from the developer portal.

Requires: pip install requests
"""

import argparse
import http.server
import json
import os
import time
import urllib.parse
import webbrowser

import requests

AUTH_URL = "https://www.tiktok.com/v2/auth/authorize/"
TOKEN_URL = "https://open.tiktokapis.com/v2/oauth/token/"
INIT_URL = "https://open.tiktokapis.com/v2/post/publish/video/init/"
STATUS_URL = "https://open.tiktokapis.com/v2/post/publish/status/fetch/"


class _CallbackHandler(http.server.BaseHTTPRequestHandler):
    code = None

    def do_GET(self):
        qs = urllib.parse.urlparse(self.path).query
        params = urllib.parse.parse_qs(qs)
        _CallbackHandler.code = params.get("code", [None])[0]
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Authorized, you can close this tab.")

    def log_message(self, *args):
        pass


def authorize(client_key: str, client_secret: str, redirect_uri: str, token_path: str) -> None:
    port = int(urllib.parse.urlparse(redirect_uri).port or 8722)
    params = {
        "client_key": client_key,
        "scope": "video.publish",
        "response_type": "code",
        "redirect_uri": redirect_uri,
        "state": "clip_factory",
    }
    auth_link = f"{AUTH_URL}?{urllib.parse.urlencode(params)}"
    print("Open this URL and approve access:\n", auth_link)
    webbrowser.open(auth_link)

    server = http.server.HTTPServer(("localhost", port), _CallbackHandler)
    while _CallbackHandler.code is None:
        server.handle_request()
    code = _CallbackHandler.code

    resp = requests.post(
        TOKEN_URL,
        data={
            "client_key": client_key,
            "client_secret": client_secret,
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": redirect_uri,
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    resp.raise_for_status()
    data = resp.json()
    data["obtained_at"] = time.time()
    with open(token_path, "w", encoding="utf-8") as f:
        json.dump(data, f)
    print(f"Saved token to {token_path}")


def _load_access_token(token_path: str, client_key: str, client_secret: str) -> str:
    with open(token_path, encoding="utf-8") as f:
        data = json.load(f)
    if time.time() - data.get("obtained_at", 0) > data.get("expires_in", 0) - 60:
        resp = requests.post(
            TOKEN_URL,
            data={
                "client_key": client_key,
                "client_secret": client_secret,
                "grant_type": "refresh_token",
                "refresh_token": data["refresh_token"],
            },
        )
        resp.raise_for_status()
        data = resp.json()
        data["obtained_at"] = time.time()
        with open(token_path, "w", encoding="utf-8") as f:
            json.dump(data, f)
    return data["access_token"]


def publish(
    video_path: str,
    title: str,
    client_key: str,
    client_secret: str,
    token_path: str,
    privacy: str = "SELF_ONLY",
):
    """privacy: 'SELF_ONLY' (default, draft/private), 'MUTUAL_FOLLOW_FRIENDS',
    or 'PUBLIC_TO_EVERYONE' (requires an audited app)."""
    access_token = _load_access_token(token_path, client_key, client_secret)
    size = os.path.getsize(video_path)
    headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json; charset=UTF-8"}

    init_body = {
        "post_info": {
            "title": title[:150],
            "privacy_level": privacy,
            "disable_duet": False,
            "disable_comment": False,
            "disable_stitch": False,
        },
        "source_info": {
            "source": "FILE_UPLOAD",
            "video_size": size,
            "chunk_size": size,
            "total_chunk_count": 1,
        },
    }
    init_resp = requests.post(INIT_URL, headers=headers, json=init_body)
    init_resp.raise_for_status()
    data = init_resp.json()["data"]
    upload_url = data["upload_url"]
    publish_id = data["publish_id"]

    with open(video_path, "rb") as f:
        video_bytes = f.read()
    put_headers = {"Content-Type": "video/mp4", "Content-Range": f"bytes 0-{size - 1}/{size}"}
    put_resp = requests.put(upload_url, headers=put_headers, data=video_bytes)
    put_resp.raise_for_status()

    for _ in range(30):
        time.sleep(2)
        status_resp = requests.post(STATUS_URL, headers=headers, json={"publish_id": publish_id})
        status = status_resp.json().get("data", {}).get("status")
        if status in ("PUBLISH_COMPLETE", "FAILED"):
            print(f"TikTok publish {publish_id}: {status} (privacy={privacy})")
            return publish_id, status

    print(f"TikTok publish {publish_id}: still processing, check status later")
    return publish_id, "PENDING"


def _cli():
    parser = argparse.ArgumentParser(description="TikTok OAuth authorization helper")
    sub = parser.add_subparsers(dest="command", required=True)

    p_auth = sub.add_parser("authorize", help="Run the one-time OAuth flow")
    p_auth.add_argument("--client-key", required=True)
    p_auth.add_argument("--client-secret", required=True)
    p_auth.add_argument("--redirect-uri", default="http://localhost:8722/callback")
    p_auth.add_argument("--token-path", default="tiktok_token.json")

    args = parser.parse_args()
    if args.command == "authorize":
        authorize(args.client_key, args.client_secret, args.redirect_uri, args.token_path)


if __name__ == "__main__":
    _cli()

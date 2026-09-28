"""
publish_youtube.py — upload a clip to YouTube via the YouTube Data API v3.

One-time setup:
1. https://console.cloud.google.com/ -> create a project.
2. APIs & Services -> Library -> enable "YouTube Data API v3".
3. APIs & Services -> OAuth consent screen -> External -> add yourself as a
   test user (this keeps the app unpublished/unreviewed, which is fine for
   personal use — Google review is only needed to let other users authorize).
4. APIs & Services -> Credentials -> Create Credentials -> OAuth client ID ->
   Application type "Desktop app". Download the JSON as
   youtube_client_secret.json.
5. First call to publish() opens a browser for you to log in and approve
   access; the resulting token is cached to youtube_token.json so you don't
   have to log in again.

Requires: pip install google-api-python-client google-auth-oauthlib
"""

import os
from typing import List

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]


def _get_service(client_secret_path: str, token_path: str):
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build

    creds = None
    if os.path.exists(token_path):
        creds = Credentials.from_authorized_user_file(token_path, SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(client_secret_path, SCOPES)
            creds = flow.run_local_server(port=0)
        with open(token_path, "w", encoding="utf-8") as f:
            f.write(creds.to_json())
    return build("youtube", "v3", credentials=creds)


def publish(
    video_path: str,
    title: str,
    description: str,
    tags: List[str],
    client_secret_path: str,
    token_path: str,
    privacy: str = "private",
    category_id: str = "22",
) -> str:
    """privacy: 'private' (default), 'unlisted', or 'public'."""
    from googleapiclient.http import MediaFileUpload

    service = _get_service(client_secret_path, token_path)
    body = {
        "snippet": {
            "title": title[:100],
            "description": description[:5000],
            "tags": tags[:500],
            "categoryId": category_id,
        },
        "status": {"privacyStatus": privacy, "selfDeclaredMadeForKids": False},
    }
    media = MediaFileUpload(video_path, chunksize=-1, resumable=True, mimetype="video/mp4")
    request = service.videos().insert(part="snippet,status", body=body, media_body=media)

    response = None
    while response is None:
        status, response = request.next_chunk()
        if status:
            print(f"  uploading... {int(status.progress() * 100)}%")

    video_id = response["id"]
    print(f"YouTube: https://youtube.com/watch?v={video_id} (privacy={privacy})")
    return video_id

"""各SNSへの投稿。どれも「投稿したら投稿ID（またはURL）を返す。失敗したら例外」。

http には httpx.Client を渡せるようにして、テストでは偽の通信に差し替える。
"""
import logging
import time
from pathlib import Path

import httpx
from oauthlib.oauth1 import Client as OAuth1Client

from .config import SocialSettings

log = logging.getLogger(__name__)


class PostError(RuntimeError):
    pass


def _check(r: httpx.Response, what: str) -> dict:
    if r.status_code >= 400:
        raise PostError(f"{what} 失敗 status={r.status_code} body={r.text[:300]}")
    return r.json() if r.content else {}


# --- X -----------------------------------------------------------------------
X_API = "https://api.x.com/2"


def _x_auth(s: SocialSettings, url: str) -> dict:
    """OAuth 1.0a の署名ヘッダー。本文（JSON・multipart）は署名に含めない決まり。"""
    c = OAuth1Client(s.x_api_key, s.x_api_secret, s.x_access_token, s.x_access_secret)
    _, headers, _ = c.sign(url, http_method="POST")
    return {"Authorization": headers["Authorization"]}


def post_x(s: SocialSettings, text: str, images: list[Path], http: httpx.Client) -> str:
    media_ids = []
    for img in images[:4]:
        url = f"{X_API}/media/upload"
        with img.open("rb") as f:
            r = http.post(url, headers=_x_auth(s, url),
                          files={"media": (img.name, f, "image/jpeg")}, data={"media_category": "tweet_image"})
        media_ids.append(_check(r, "X 画像アップロード")["data"]["id"])
    url = f"{X_API}/tweets"
    body = {"text": text}
    if media_ids:
        body["media"] = {"media_ids": media_ids}
    r = http.post(url, headers=_x_auth(s, url), json=body)
    return _check(r, "X 投稿")["data"]["id"]


# --- Threads -------------------------------------------------------------------
THREADS_API = "https://graph.threads.com/v1.0"


def post_threads(s: SocialSettings, text: str, image_urls: list[str], http: httpx.Client, wait=30) -> str:
    base = f"{THREADS_API}/{s.threads_user_id}"
    tok = {"access_token": s.threads_token}
    if len(image_urls) >= 2:
        children = [
            _check(http.post(f"{base}/threads", params=tok | {"media_type": "IMAGE", "image_url": u, "is_carousel_item": "true"}),
                   "Threads 画像の準備")["id"]
            for u in image_urls[:20]
        ]
        params = {"media_type": "CAROUSEL", "children": ",".join(children), "text": text}
    else:
        params = {"media_type": "IMAGE", "image_url": image_urls[0], "text": text}
    container = _check(http.post(f"{base}/threads", params=tok | params), "Threads 投稿の準備")["id"]
    time.sleep(wait)  # 公式の推奨: 準備から公開まで平均30秒ほど待つ
    return _check(http.post(f"{base}/threads_publish", params=tok | {"creation_id": container}), "Threads 公開")["id"]


# --- Instagram ---------------------------------------------------------------------
def _ig_wait(s: SocialSettings, http: httpx.Client, container: str, interval: int, tries: int) -> None:
    """コンテナの処理完了を待つ（公式の推奨: 1分に1回・最大5分）。"""
    for _ in range(tries):
        st = _check(http.get(f"https://{s.ig_graph_host}/{container}",
                             params={"fields": "status_code", "access_token": s.ig_token}), "Instagram 状態確認")
        code = st.get("status_code")
        if code == "FINISHED":
            return
        if code in ("ERROR", "EXPIRED"):
            raise PostError(f"Instagram の処理に失敗: {code}")
        time.sleep(interval)
    raise PostError("Instagram の処理が時間内に終わりませんでした")


def _ig_publish(s: SocialSettings, http: httpx.Client, container: str) -> str:
    r = http.post(f"https://{s.ig_graph_host}/{s.ig_user_id}/media_publish",
                  params={"creation_id": container, "access_token": s.ig_token})
    return _check(r, "Instagram 公開")["id"]


def post_instagram_carousel(s: SocialSettings, caption: str, image_urls: list[str], http: httpx.Client,
                            interval=60, tries=5) -> str:
    base = f"https://{s.ig_graph_host}/{s.ig_user_id}/media"
    tok = {"access_token": s.ig_token}
    children = [
        _check(http.post(base, params=tok | {"image_url": u, "is_carousel_item": "true"}), "Instagram 画像の準備")["id"]
        for u in image_urls[:20]
    ]
    container = _check(http.post(base, params=tok | {"media_type": "CAROUSEL", "children": ",".join(children),
                                                      "caption": caption}), "Instagram 投稿の準備")["id"]
    _ig_wait(s, http, container, interval, tries)
    return _ig_publish(s, http, container)


def post_instagram_reel(s: SocialSettings, caption: str, video_url: str, http: httpx.Client,
                        interval=60, tries=5) -> str:
    base = f"https://{s.ig_graph_host}/{s.ig_user_id}/media"
    container = _check(http.post(base, params={"media_type": "REELS", "video_url": video_url, "caption": caption,
                                               "access_token": s.ig_token}), "Instagram リールの準備")["id"]
    _ig_wait(s, http, container, interval, tries)
    return _ig_publish(s, http, container)


# --- LINE ---------------------------------------------------------------------
def post_line_broadcast(s: SocialSettings, text: str, image_url: str, http: httpx.Client) -> str:
    """友だち全員に一斉配信する。無料枠は「配信回数 × 友だち数」で減るので曜日を絞って使う。"""
    r = http.post(
        "https://api.line.me/v2/bot/message/broadcast",
        headers={"Authorization": f"Bearer {s.line_token}"},
        json={"messages": [
            {"type": "image", "originalContentUrl": image_url, "previewImageUrl": image_url},
            {"type": "text", "text": text[:5000]},
        ]},
    )
    _check(r, "LINE 一斉配信")
    return r.headers.get("x-line-request-id", "sent")


# --- YouTube ショート -------------------------------------------------------------
def post_youtube(s: SocialSettings, title: str, description: str, video: Path) -> str:
    """注意: 審査（監査）前の Google Cloud プロジェクトからの投稿は非公開になる。"""
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload

    creds = Credentials(None, refresh_token=s.yt_refresh_token, client_id=s.yt_client_id,
                        client_secret=s.yt_client_secret, token_uri="https://oauth2.googleapis.com/token",
                        scopes=["https://www.googleapis.com/auth/youtube.upload"])
    yt = build("youtube", "v3", credentials=creds, cache_discovery=False)
    req = yt.videos().insert(
        part="snippet,status",
        body={
            "snippet": {"title": title[:100], "description": description[:5000], "categoryId": "24",
                        "defaultLanguage": "ja", "tags": ["占い", "タロット", "星座占い"]},
            "status": {"privacyStatus": "public", "selfDeclaredMadeForKids": False},
        },
        media_body=MediaFileUpload(str(video), mimetype="video/mp4", chunksize=-1, resumable=True),
    )
    resp = None
    while resp is None:
        _, resp = req.next_chunk()
    return resp["id"]

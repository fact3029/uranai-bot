"""SNS 投稿の設定（環境変数・GitHub Actions の Secrets から読む）。"""
import os
from dataclasses import dataclass


def _env(name: str) -> str:
    return os.getenv(name, "").strip()


@dataclass(frozen=True)
class SocialSettings:
    # 画像・動画の公開置き場（S3 互換。Cloudflare R2 など）
    s3_endpoint: str = _env("S3_ENDPOINT_URL")
    s3_bucket: str = _env("S3_BUCKET")
    s3_key_id: str = _env("S3_ACCESS_KEY_ID")
    s3_secret: str = _env("S3_SECRET_ACCESS_KEY")
    media_base_url: str = _env("MEDIA_PUBLIC_BASE_URL").rstrip("/")

    # X（OAuth 1.0a ユーザー認証。期限切れしないので自動投稿向き）
    x_api_key: str = _env("X_API_KEY")
    x_api_secret: str = _env("X_API_SECRET")
    x_access_token: str = _env("X_ACCESS_TOKEN")
    x_access_secret: str = _env("X_ACCESS_TOKEN_SECRET")

    # Threads
    threads_user_id: str = _env("THREADS_USER_ID")
    threads_token: str = _env("THREADS_ACCESS_TOKEN")

    # Instagram（Facebook ページとつないだプロアカウント）
    ig_user_id: str = _env("IG_USER_ID")
    ig_token: str = _env("IG_ACCESS_TOKEN")
    ig_graph_host: str = _env("IG_GRAPH_HOST") or "graph.facebook.com"

    # YouTube（OAuth のリフレッシュトークン）
    yt_client_id: str = _env("YT_CLIENT_ID")
    yt_client_secret: str = _env("YT_CLIENT_SECRET")
    yt_refresh_token: str = _env("YT_REFRESH_TOKEN")

    # LINE（一斉配信は無料枠を使うので曜日を絞る。0=月曜 … 6=日曜）
    line_token: str = _env("LINE_CHANNEL_ACCESS_TOKEN")
    line_broadcast_weekdays: str = _env("LINE_BROADCAST_WEEKDAYS")

    @property
    def storage_ready(self) -> bool:
        return all([self.s3_bucket, self.s3_key_id, self.s3_secret, self.media_base_url])

    def ready(self, platform: str) -> bool:
        return {
            "x": all([self.x_api_key, self.x_api_secret, self.x_access_token, self.x_access_secret]),
            "threads": bool(self.threads_user_id and self.threads_token and self.storage_ready),
            "instagram": bool(self.ig_user_id and self.ig_token and self.storage_ready),
            "youtube": all([self.yt_client_id, self.yt_client_secret, self.yt_refresh_token]),
            "line": bool(self.line_token and self.line_broadcast_weekdays and self.storage_ready),
        }[platform]


PLATFORMS = ["x", "threads", "instagram", "youtube", "line"]

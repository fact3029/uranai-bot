"""画像・動画を公開URLに置く（Instagram・Threads・LINE は URL からしか画像を受け取らないため）。"""
import mimetypes
from pathlib import Path

import boto3

from .config import SocialSettings


def upload(s: SocialSettings, path: Path, key: str) -> str:
    client = boto3.client(
        "s3",
        endpoint_url=s.s3_endpoint or None,
        aws_access_key_id=s.s3_key_id,
        aws_secret_access_key=s.s3_secret,
        region_name="auto" if s.s3_endpoint else None,
    )
    ctype = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    client.upload_file(str(path), s.s3_bucket, key, ExtraArgs={"ContentType": ctype})
    return f"{s.media_base_url}/{key}"

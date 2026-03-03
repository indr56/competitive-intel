from __future__ import annotations

import logging
from pathlib import Path

from app.core.config import get_settings

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"


def _s3_configured() -> bool:
    settings = get_settings()
    key = settings.S3_ACCESS_KEY_ID
    return bool(key and key not in ("", "your-access-key"))


def get_s3_client():
    import boto3
    from botocore.config import Config

    settings = get_settings()
    return boto3.client(
        "s3",
        endpoint_url=settings.S3_ENDPOINT_URL or None,
        aws_access_key_id=settings.S3_ACCESS_KEY_ID,
        aws_secret_access_key=settings.S3_SECRET_ACCESS_KEY,
        region_name=settings.S3_REGION,
        config=Config(signature_version="s3v4"),
    )


def _upload_bytes_s3(key: str, data: bytes, content_type: str) -> str:
    settings = get_settings()
    client = get_s3_client()
    client.put_object(
        Bucket=settings.S3_BUCKET_NAME,
        Key=key,
        Body=data,
        ContentType=content_type,
    )
    if settings.S3_ENDPOINT_URL:
        return f"{settings.S3_ENDPOINT_URL}/{settings.S3_BUCKET_NAME}/{key}"
    return f"https://{settings.S3_BUCKET_NAME}.s3.{settings.S3_REGION}.amazonaws.com/{key}"


def _upload_bytes_local(key: str, data: bytes) -> str:
    dest = DATA_DIR / key
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(data)
    logger.info("Saved locally: %s (%d bytes)", dest, len(data))
    return f"file://{dest}"


def upload_bytes(key: str, data: bytes, content_type: str = "image/png") -> str:
    if _s3_configured():
        return _upload_bytes_s3(key, data, content_type)
    return _upload_bytes_local(key, data)


def upload_file(key: str, file_path: str, content_type: str = "image/png") -> str:
    with open(file_path, "rb") as f:
        return upload_bytes(key, f.read(), content_type)

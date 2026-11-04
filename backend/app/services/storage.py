"""Private object storage with short-lived signed download URLs.

`s3`    : any S3-compatible service (AWS S3, MinIO, R2). Objects are private; downloads use presigned URLs.
`local` : filesystem storage for development/tests. URLs are HMAC-signed and served by /api/files/{token}.
"""

import base64
import hashlib
import hmac
import json
import re
import time
from pathlib import Path
from urllib.parse import quote

from app.core.config import get_settings
from app.core.errors import NotFound, ServiceNotConfigured, Unauthorized


def safe_filename(name: str, default: str = "file") -> str:
    base = re.sub(r"[^A-Za-z0-9._\- ]+", "_", (name or default).split("/")[-1].split("\\")[-1]).strip(" .")
    return (base or default)[:120]


class Storage:
    def put(self, key: str, data: bytes, content_type: str) -> None: ...
    def get(self, key: str) -> bytes: ...
    def delete(self, key: str) -> None: ...
    def signed_url(self, key: str, filename: str, content_type: str, ttl: int | None = None) -> str: ...


class LocalStorage(Storage):
    def __init__(self) -> None:
        s = get_settings()
        self.root = Path(s.local_storage_path).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        p = (self.root / key).resolve()
        if self.root not in p.parents:  # block path traversal
            raise ValueError("Invalid storage key")
        return p

    def put(self, key: str, data: bytes, content_type: str) -> None:
        p = self._path(key)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)

    def get(self, key: str) -> bytes:
        p = self._path(key)
        if not p.exists():
            raise NotFound("File not found")
        return p.read_bytes()

    def delete(self, key: str) -> None:
        p = self._path(key)
        if p.exists():
            p.unlink()

    def signed_url(self, key: str, filename: str, content_type: str, ttl: int | None = None) -> str:
        s = get_settings()
        payload = {"k": key, "f": safe_filename(filename), "c": content_type, "e": int(time.time()) + (ttl or s.signed_url_ttl_seconds)}
        body = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")
        sig = hmac.new(s.secret_key.encode(), body.encode(), hashlib.sha256).hexdigest()
        return f"{s.api_url}/api/files/{body}.{sig}"


def verify_local_token(token: str) -> dict:
    s = get_settings()
    try:
        body, sig = token.rsplit(".", 1)
    except ValueError as exc:
        raise Unauthorized("Invalid download link") from exc
    expected = hmac.new(s.secret_key.encode(), body.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(sig, expected):
        raise Unauthorized("Invalid download link")
    try:
        payload = json.loads(base64.urlsafe_b64decode(body + "=" * (-len(body) % 4)))
    except Exception as exc:  # noqa: BLE001
        raise Unauthorized("Invalid download link") from exc
    if payload.get("e", 0) < time.time():
        raise Unauthorized("This download link has expired")
    return payload


class S3Storage(Storage):
    def __init__(self) -> None:
        import boto3
        from botocore.client import Config

        s = get_settings()
        if not (s.s3_access_key and s.s3_secret_key and s.s3_bucket):
            raise ServiceNotConfigured("S3 storage credentials are not configured")
        self.bucket = s.s3_bucket
        self.client = boto3.client(
            "s3",
            endpoint_url=s.s3_endpoint_url or None,
            region_name=s.s3_region,
            aws_access_key_id=s.s3_access_key,
            aws_secret_access_key=s.s3_secret_key,
            config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
        )

    def put(self, key: str, data: bytes, content_type: str) -> None:
        self.client.put_object(
            Bucket=self.bucket, Key=key, Body=data, ContentType=content_type, ServerSideEncryption="AES256"
        )

    def get(self, key: str) -> bytes:
        try:
            return self.client.get_object(Bucket=self.bucket, Key=key)["Body"].read()
        except self.client.exceptions.NoSuchKey as exc:
            raise NotFound("File not found") from exc

    def delete(self, key: str) -> None:
        self.client.delete_object(Bucket=self.bucket, Key=key)

    def signed_url(self, key: str, filename: str, content_type: str, ttl: int | None = None) -> str:
        return self.client.generate_presigned_url(
            "get_object",
            Params={
                "Bucket": self.bucket,
                "Key": key,
                "ResponseContentType": content_type,
                "ResponseContentDisposition": f"attachment; filename*=UTF-8''{quote(safe_filename(filename))}",
            },
            ExpiresIn=ttl or get_settings().signed_url_ttl_seconds,
        )


_instance: Storage | None = None


def get_storage() -> Storage:
    global _instance
    if _instance is None:
        s = get_settings()
        if s.storage_backend == "s3":
            _instance = S3Storage()
        else:
            if s.is_production_like:
                raise ServiceNotConfigured("STORAGE_BACKEND=local is not allowed in staging/production")
            _instance = LocalStorage()
    return _instance


def reset_storage() -> None:
    global _instance
    _instance = None

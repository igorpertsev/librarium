"""Where uploaded files (book covers) live: on local disk, or in S3-compatible storage.

Files are addressed by a key such as ``covers/<random>-L.webp`` and always served under
``/media/<key>``, so stored URLs do not depend on the storage. Local disk (``MEDIA_DIR``) is the
default; with ``S3_BUCKET`` set they go to that bucket (AWS S3, Cloudflare R2, Backblaze B2,
MinIO, RustFS…). ``/media`` then redirects to ``MEDIA_PUBLIC_URL`` when the bucket (or a CDN in
front of it) is public, or the backend streams the file from a private bucket.
"""

from __future__ import annotations

import asyncio
import io
from pathlib import Path
from typing import Protocol
from urllib.parse import urlsplit

from minio import Minio
from minio.error import S3Error

from app.core.config import Settings

# Names are random and never reused, so a stored file can be cached for good.
IMMUTABLE = "public, max-age=31536000, immutable"


class MediaStorage(Protocol):
    async def put(self, key: str, data: bytes, content_type: str) -> None: ...

    async def get(self, key: str) -> bytes | None: ...

    async def delete(self, key: str) -> None: ...

    def public_url(self, key: str) -> str | None:
        """Where browsers can fetch the file directly, if anywhere."""
        ...


class LocalStorage:
    def __init__(self, root: str) -> None:
        self.root = Path(root)

    def _path(self, key: str) -> Path:
        path = (self.root / key).resolve()
        if not path.is_relative_to(self.root.resolve()):
            raise ValueError(f"Key outside the media folder: {key!r}")
        return path

    async def put(self, key: str, data: bytes, content_type: str) -> None:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        await asyncio.to_thread(path.write_bytes, data)

    async def get(self, key: str) -> bytes | None:
        path = self._path(key)
        return await asyncio.to_thread(path.read_bytes) if path.is_file() else None

    async def delete(self, key: str) -> None:
        self._path(key).unlink(missing_ok=True)

    def public_url(self, key: str) -> str | None:
        return None  # served by the backend's /media mount


class S3Storage:
    def __init__(self, settings: Settings) -> None:
        if not (settings.s3_endpoint and settings.s3_bucket and settings.s3_secret_access_key):
            raise ValueError("S3 storage needs S3_ENDPOINT, S3_BUCKET and the access keys")
        endpoint = urlsplit(settings.s3_endpoint)
        self.client = Minio(
            endpoint.netloc,
            access_key=settings.s3_access_key_id,
            secret_key=settings.s3_secret_access_key.get_secret_value(),
            secure=endpoint.scheme == "https",
            region=settings.s3_region,
        )
        self.bucket = settings.s3_bucket
        self.prefix = settings.s3_prefix.strip("/") + "/" if settings.s3_prefix.strip("/") else ""
        self.public_base = settings.media_public_url

    def _key(self, key: str) -> str:
        return f"{self.prefix}{key}"

    async def put(self, key: str, data: bytes, content_type: str) -> None:
        await asyncio.to_thread(
            self.client.put_object,
            self.bucket,
            self._key(key),
            io.BytesIO(data),
            len(data),
            content_type=content_type,
            metadata={"Cache-Control": IMMUTABLE},
        )

    async def get(self, key: str) -> bytes | None:
        def read() -> bytes | None:
            try:
                response = self.client.get_object(self.bucket, self._key(key))
            except S3Error as exc:
                if exc.code in {"NoSuchKey", "NoSuchObject"}:
                    return None
                raise
            try:
                return response.read()
            finally:
                response.close()
                response.release_conn()

        return await asyncio.to_thread(read)

    async def exists(self, key: str) -> bool:
        def stat() -> bool:
            try:
                self.client.stat_object(self.bucket, self._key(key))
            except S3Error as exc:
                if exc.code in {"NoSuchKey", "NoSuchObject"}:
                    return False
                raise
            return True

        return await asyncio.to_thread(stat)

    async def delete(self, key: str) -> None:
        await asyncio.to_thread(self.client.remove_object, self.bucket, self._key(key))

    async def ensure_bucket(self) -> None:
        """Create the bucket if it does not exist (development and tests)."""

        def make() -> None:
            if not self.client.bucket_exists(self.bucket):
                self.client.make_bucket(self.bucket)

        await asyncio.to_thread(make)

    def public_url(self, key: str) -> str | None:
        return f"{self.public_base}/{self._key(key)}" if self.public_base else None


def make_storage(settings: Settings) -> MediaStorage:
    return S3Storage(settings) if settings.s3_bucket else LocalStorage(settings.media_dir)


async def copy_local_to_s3(media_dir: str, storage: S3Storage) -> tuple[int, int]:
    """Upload the covers kept in MEDIA_DIR to the bucket; returns (copied, already there)."""
    copied = present = 0
    paths = await asyncio.to_thread(lambda: sorted(Path(media_dir, "covers").glob("*.webp")))
    for path in paths:
        key = f"covers/{path.name}"
        if await storage.exists(key):
            present += 1
            continue
        await storage.put(key, await asyncio.to_thread(path.read_bytes), "image/webp")
        copied += 1
    return copied, present

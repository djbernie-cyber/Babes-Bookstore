import os
import boto3
from typing import Optional, BinaryIO
from datetime import datetime, timedelta
from botocore.exceptions import ClientError
import logging

from ..config import settings

logger = logging.getLogger(__name__)


class StorageService:
    """Cloudflare R2 / S3-compatible storage service with local-fallback.

    When R2 credentials are not configured the service transparently stores
    files under LOCAL_STORAGE_PATH so bundles remain downloadable in dev and
    in deployments that have not yet provisioned R2.
    """

    def __init__(self):
        if settings.R2_ACCOUNT_ID and settings.R2_ACCESS_KEY_ID:
            self.client = boto3.client(
                "s3",
                endpoint_url=f"https://{settings.R2_ACCOUNT_ID}.r2.cloudflarestorage.com",
                aws_access_key_id=settings.R2_ACCESS_KEY_ID,
                aws_secret_access_key=settings.R2_SECRET_ACCESS_KEY,
                region_name="auto",
            )
        else:
            self.client = None
            logger.warning("Storage not configured — using local filesystem fallback at %s", settings.LOCAL_STORAGE_PATH)

        self.bucket = settings.R2_BUCKET_NAME
        self.public_url = settings.R2_PUBLIC_URL
        self.local_root = settings.LOCAL_STORAGE_PATH

    # --- helpers ---------------------------------------------------------

    def _local_path(self, key: str) -> str:
        # Prevent directory traversal; keep key inside local_root
        safe = key.lstrip("/").replace("..", "")
        return os.path.join(self.local_root, safe)

    def _ensure_local_dir(self, path: str):
        os.makedirs(os.path.dirname(path), exist_ok=True)

    # --- public API ------------------------------------------------------

    def upload_file(self, key: str, file_obj: BinaryIO, content_type: str = "application/octet-stream") -> Optional[str]:
        if self.client:
            try:
                self.client.upload_fileobj(
                    file_obj,
                    self.bucket,
                    key,
                    ExtraArgs={"ContentType": content_type},
                )
                return key
            except ClientError as e:
                logger.error(f"Upload failed for {key}: {e}")
                return None
        # local fallback
        try:
            local = self._local_path(key)
            self._ensure_local_dir(local)
            # file_obj may be BytesIO or file
            with open(local, "wb") as f:
                # reset if possible
                try:
                    file_obj.seek(0)
                except Exception:
                    pass
                f.write(file_obj.read() if hasattr(file_obj, "read") else file_obj)
            return key
        except Exception as e:
            logger.error(f"Local upload failed for {key}: {e}")
            return None

    def upload_bytes(self, key: str, data: bytes, content_type: str = "application/octet-stream") -> Optional[str]:
        if self.client:
            try:
                self.client.put_object(
                    Bucket=self.bucket,
                    Key=key,
                    Body=data,
                    ContentType=content_type,
                )
                return key
            except ClientError as e:
                logger.error(f"Upload failed for {key}: {e}")
                return None
        try:
            local = self._local_path(key)
            self._ensure_local_dir(local)
            with open(local, "wb") as f:
                f.write(data)
            return key
        except Exception as e:
            logger.error(f"Local upload failed for {key}: {e}")
            return None

    def get_signed_url(self, key: str, expires_in: int = 3600) -> Optional[str]:
        if self.client:
            try:
                url = self.client.generate_presigned_url(
                    "get_object",
                    Params={"Bucket": self.bucket, "Key": key},
                    ExpiresIn=expires_in,
                )
                return url
            except ClientError as e:
                logger.error(f"Signed URL generation failed for {key}: {e}")
                return None
        # local fallback — serve via the purchases storage endpoint
        # The key is returned as a path that the frontend can fetch directly.
        # Keep it absolute so window.location.href works from any origin.
        # The storage file endpoint is public but the zip path is unguessable
        # (contains bundle id + timestamp) and download availability is still
        # gated by the purchase token at the purchases endpoint.
        from urllib.parse import quote
        # Use production URL when available, otherwise a relative path
        base = (settings.PRODUCTION_URL or "").rstrip("/")
        if base:
            return f"{base}/api/v1/purchases/storage/{quote(key, safe='/')}"
        return f"/api/v1/purchases/storage/{quote(key, safe='/')}"

    def download_file(self, key: str) -> Optional[bytes]:
        if self.client:
            try:
                response = self.client.get_object(Bucket=self.bucket, Key=key)
                return response["Body"].read()
            except ClientError as e:
                logger.error(f"Download failed for {key}: {e}")
                return None
        try:
            local = self._local_path(key)
            if not os.path.exists(local):
                logger.warning(f"Local file not found for {key} at {local}")
                return None
            with open(local, "rb") as f:
                return f.read()
        except Exception as e:
            logger.error(f"Local download failed for {key}: {e}")
            return None

    def delete_file(self, key: str) -> bool:
        if self.client:
            try:
                self.client.delete_object(Bucket=self.bucket, Key=key)
                return True
            except ClientError as e:
                logger.error(f"Delete failed for {key}: {e}")
                return False
        try:
            local = self._local_path(key)
            if os.path.exists(local):
                os.remove(local)
            return True
        except Exception as e:
            logger.error(f"Local delete failed for {key}: {e}")
            return False

    def exists(self, key: str) -> bool:
        if self.client:
            try:
                self.client.head_object(Bucket=self.bucket, Key=key)
                return True
            except Exception:
                return False
        return os.path.exists(self._local_path(key))


storage = StorageService()

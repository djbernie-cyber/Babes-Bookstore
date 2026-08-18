import boto3
from typing import Optional, BinaryIO
from datetime import datetime, timedelta
from botocore.exceptions import ClientError
import logging

from ..config import settings

logger = logging.getLogger(__name__)


class StorageService:
    """Cloudflare R2 / S3-compatible storage service."""

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
            logger.warning("Storage not configured — R2 credentials missing")

        self.bucket = settings.R2_BUCKET_NAME
        self.public_url = settings.R2_PUBLIC_URL

    def upload_file(self, key: str, file_obj: BinaryIO, content_type: str = "application/octet-stream") -> Optional[str]:
        if not self.client:
            return None
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

    def upload_bytes(self, key: str, data: bytes, content_type: str = "application/octet-stream") -> Optional[str]:
        if not self.client:
            return None
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

    def get_signed_url(self, key: str, expires_in: int = 3600) -> Optional[str]:
        if not self.client:
            return f"/local/{key}"
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

    def download_file(self, key: str) -> Optional[bytes]:
        if not self.client:
            return None
        try:
            response = self.client.get_object(Bucket=self.bucket, Key=key)
            return response["Body"].read()
        except ClientError as e:
            logger.error(f"Download failed for {key}: {e}")
            return None

    def delete_file(self, key: str) -> bool:
        if not self.client:
            return False
        try:
            self.client.delete_object(Bucket=self.bucket, Key=key)
            return True
        except ClientError as e:
            logger.error(f"Delete failed for {key}: {e}")
            return False


storage = StorageService()
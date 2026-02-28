import boto3
from app.config import settings
from app.services.base import BaseStorageService


class StorageService(BaseStorageService):
    def _get_client(self):
        kwargs = dict(
            region_name=settings.aws_region,
            aws_access_key_id=settings.aws_access_key_id,
            aws_secret_access_key=settings.aws_secret_access_key,
        )
        if settings.s3_endpoint_url:
            kwargs["endpoint_url"] = settings.s3_endpoint_url
        return boto3.client("s3", **kwargs)

    def upload_text(self, key: str, text: str) -> None:
        self._get_client().put_object(
            Bucket=settings.s3_bucket,
            Key=key,
            Body=text.encode("utf-8"),
            ContentType="text/plain",
        )

    def download_text(self, key: str) -> str:
        obj = self._get_client().get_object(Bucket=settings.s3_bucket, Key=key)
        return obj["Body"].read().decode("utf-8")


storage_service = StorageService()

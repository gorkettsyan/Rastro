import boto3
from app.config import settings


def get_s3_client():
    kwargs = dict(
        region_name=settings.aws_region,
        aws_access_key_id=settings.aws_access_key_id,
        aws_secret_access_key=settings.aws_secret_access_key,
    )
    if settings.s3_endpoint_url:
        kwargs["endpoint_url"] = settings.s3_endpoint_url
    return boto3.client("s3", **kwargs)


def upload_text(key: str, text: str) -> None:
    get_s3_client().put_object(
        Bucket=settings.s3_bucket,
        Key=key,
        Body=text.encode("utf-8"),
        ContentType="text/plain",
    )


def download_text(key: str) -> str:
    obj = get_s3_client().get_object(Bucket=settings.s3_bucket, Key=key)
    return obj["Body"].read().decode("utf-8")

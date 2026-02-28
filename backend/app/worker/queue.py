import json
import boto3
from app.config import settings
from app.services.base import BaseQueueService


class QueueService(BaseQueueService):
    def _get_client(self):
        kwargs = dict(
            region_name=settings.aws_region,
            aws_access_key_id=settings.aws_access_key_id,
            aws_secret_access_key=settings.aws_secret_access_key,
        )
        if settings.sqs_endpoint_url:
            kwargs["endpoint_url"] = settings.sqs_endpoint_url
        return boto3.client("sqs", **kwargs)

    def enqueue(self, job: dict) -> None:
        self._get_client().send_message(
            QueueUrl=settings.sqs_ingest_queue_url,
            MessageBody=json.dumps(job),
        )

    def poll(self, wait_seconds: int = 20) -> list[dict]:
        resp = self._get_client().receive_message(
            QueueUrl=settings.sqs_ingest_queue_url,
            MaxNumberOfMessages=5,
            WaitTimeSeconds=wait_seconds,
        )
        return [
            {"body": json.loads(m["Body"]), "receipt_handle": m["ReceiptHandle"]}
            for m in resp.get("Messages", [])
        ]

    def delete_message(self, receipt_handle: str) -> None:
        self._get_client().delete_message(
            QueueUrl=settings.sqs_ingest_queue_url,
            ReceiptHandle=receipt_handle,
        )


queue_service = QueueService()

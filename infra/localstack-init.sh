#!/bin/bash
set -e

echo "Creating SQS queues..."
awslocal sqs create-queue \
  --queue-name rastro-ingest-dlq \
  --region eu-west-1

awslocal sqs create-queue \
  --queue-name rastro-ingest \
  --attributes '{
    "VisibilityTimeout": "300",
    "RedrivePolicy": "{\"deadLetterTargetArn\":\"arn:aws:sqs:eu-west-1:000000000000:rastro-ingest-dlq\",\"maxReceiveCount\":\"3\"}"
  }' \
  --region eu-west-1

echo "Creating S3 bucket..."
awslocal s3 mb s3://rastro-documents --region eu-west-1

echo "LocalStack init complete."

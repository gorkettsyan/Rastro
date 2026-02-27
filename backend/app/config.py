from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # PRD 1
    database_url: str
    database_url_sync: str
    app_env: str = "development"
    secret_key: str
    jwt_secret: str
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 10080
    google_client_id: str
    google_client_secret: str
    google_redirect_uri: str
    frontend_url: str = "http://localhost:5173"
    # PRD 2
    openai_api_key: str
    aws_access_key_id: str = "test"
    aws_secret_access_key: str = "test"
    aws_region: str = "eu-west-1"
    sqs_endpoint_url: str | None = None
    sqs_ingest_queue_url: str
    sqs_ingest_dlq_url: str | None = None
    s3_endpoint_url: str | None = None
    s3_bucket: str = "rastro-documents"

    class Config:
        env_file = ".env"


settings = Settings()

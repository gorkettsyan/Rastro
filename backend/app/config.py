from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str
    database_url_sync: str
    app_env: str = "development"
    secret_key: str
    jwt_secret: str
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 10080  # 7 days
    google_client_id: str
    google_client_secret: str
    google_redirect_uri: str
    frontend_url: str = "http://localhost:5173"

    class Config:
        env_file = ".env"


settings = Settings()

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    secret_key: str = "quiz-master-dev-secret-change-in-production"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 24 * 7
    database_url: str = "sqlite:///./quiz_master.db"

    class Config:
        env_file = ".env"


settings = Settings()

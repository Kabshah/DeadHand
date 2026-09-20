from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/deadswitch"
    REDIS_URL: str = "redis://localhost:6379/0"

    GOOGLE_CLIENT_ID: str = ""
    GOOGLE_CLIENT_SECRET: str = ""
    GOOGLE_REDIRECT_URI: str = "http://localhost:8000/auth/callback"

    JWT_SECRET: str = "change-me-in-production"
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TTL_MIN: int = 15
    JWT_REFRESH_TTL_DAYS: int = 30

    FERNET_KEY: str = ""

    SMTP_HOST: str = "smtp.gmail.com"
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_FROM: str = ""
    SENDGRID_API_KEY: str = ""

    OTP_TTL_SECONDS: int = 300
    OTP_REQUEST_LIMIT: int = 3
    OTP_REQUEST_WINDOW_SEC: int = 600
    OTP_VERIFY_ATTEMPT_LIMIT: int = 5
    OTP_MAX_FAIL_ATTEMPTS: int = 3
    OTP_LOCKOUT_SECONDS: int = 300
    OTP_RESEND_COOLDOWN_SECONDS: int = 60

    TRUST_PROXY_HEADERS: bool = False
    LOGIN_LIMIT_PER_IP: int = 1
    LOGIN_WINDOW_SEC: int = 60

    # Business rules
    MAX_SWITCHES_PER_USER: int = 5

    # App
    APP_ENV: str = "development"
    APP_BASE_URL: str = "http://localhost:8000"
    FRONTEND_URL: str = "http://localhost:5173"


def get_settings() -> Settings:
    """Return Settings initialized from .env."""
    return Settings()


settings = get_settings()

from pydantic_settings import BaseSettings
from functools import lru_cache
from typing import Literal


class Settings(BaseSettings):
    # Database
    DATABASE_URL: str = "postgresql://compintel:compintel@localhost:5432/compintel"

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"

    # LLM
    LLM_PROVIDER: Literal["openai", "anthropic"] = "openai"
    OPENAI_API_KEY: str = ""
    ANTHROPIC_API_KEY: str = ""
    LLM_MODEL: str = "gpt-4o"

    # S3 / R2
    S3_ENDPOINT_URL: str = ""
    S3_ACCESS_KEY_ID: str = ""
    S3_SECRET_ACCESS_KEY: str = ""
    S3_BUCKET_NAME: str = "compintel-snapshots"
    S3_REGION: str = "auto"

    # Email
    RESEND_API_KEY: str = ""
    EMAIL_FROM: str = "notifications@yourdomain.com"

    # Razorpay
    RAZORPAY_KEY_ID: str = ""
    RAZORPAY_KEY_SECRET: str = ""
    RAZORPAY_WEBHOOK_SECRET: str = ""
    RAZORPAY_STARTER_PLAN_ID: str = ""
    RAZORPAY_PRO_PLAN_ID: str = ""
    RAZORPAY_AGENCY_PLAN_ID: str = ""

    # Billing
    ANNUAL_DISCOUNT_PCT: float = 0.25  # 25% off for annual billing

    # App
    APP_ENV: Literal["development", "staging", "production"] = "development"
    APP_SECRET_KEY: str = "change-me-in-production"
    API_HOST: str = "0.0.0.0"
    API_PORT: int = 8000
    FRONTEND_URL: str = "http://localhost:3000"

    # Capture
    CAPTURE_TIMEOUT_MS: int = 30000
    CAPTURE_VIEWPORT_WIDTH: int = 1440
    CAPTURE_VIEWPORT_HEIGHT: int = 900
    CAPTURE_THROTTLE_SECONDS: float = 2.0
    CAPTURE_MAX_RETRIES: int = 3

    # Diff
    DIFF_MEANINGFUL_THRESHOLD: int = 10  # minimum changed chars to be meaningful

    model_config = {"env_file": (".env", "../.env"), "extra": "ignore"}


@lru_cache
def get_settings() -> Settings:
    return Settings()

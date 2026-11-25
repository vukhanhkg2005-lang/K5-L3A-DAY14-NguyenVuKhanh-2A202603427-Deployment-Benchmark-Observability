"""
Config — 12-Factor: mọi cấu hình đọc từ biến môi trường.
"""
import os
from dataclasses import dataclass, field

from dotenv import load_dotenv

load_dotenv(override=False)


def _get_bool(name: str, default: bool = False) -> bool:
    val = os.getenv(name)
    if val is None:
        return default
    return val.strip().lower() in ("1", "true", "yes", "on")


@dataclass
class Settings:
    port: int = field(default_factory=lambda: int(os.getenv("PORT", "8000")))
    environment: str = field(default_factory=lambda: os.getenv("ENVIRONMENT", "development"))
    debug: bool = field(default_factory=lambda: _get_bool("DEBUG", False))
    agent_api_key: str = field(default_factory=lambda: os.getenv("AGENT_API_KEY", ""))
    redis_url: str = field(default_factory=lambda: os.getenv("REDIS_URL", ""))
    rate_limit_per_minute: int = field(default_factory=lambda: int(os.getenv("RATE_LIMIT_PER_MINUTE", "10")))
    daily_budget_usd: float = field(default_factory=lambda: float(os.getenv("DAILY_BUDGET_USD", "1.0")))
    monthly_budget_usd: float = field(default_factory=lambda: float(os.getenv("MONTHLY_BUDGET_USD", "10.0")))
    log_level: str = field(default_factory=lambda: os.getenv("LOG_LEVEL", "INFO"))


settings = Settings()

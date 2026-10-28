import os
from dataclasses import dataclass
from pathlib import Path


def _load_dotenv(path: Path) -> None:
    """.env を読み込む（すでに環境変数にある値は上書きしない）。"""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip())


_load_dotenv(Path(__file__).resolve().parent.parent / ".env")


@dataclass(frozen=True)
class Settings:
    anthropic_api_key: str = os.getenv("ANTHROPIC_API_KEY", "")
    claude_model: str = os.getenv("CLAUDE_MODEL", "claude-opus-5-5")
    line_channel_secret: str = os.getenv("LINE_CHANNEL_SECRET", "")
    line_access_token: str = os.getenv("LINE_CHANNEL_ACCESS_TOKEN", "")
    stripe_secret_key: str = os.getenv("STRIPE_SECRET_KEY", "")
    stripe_webhook_secret: str = os.getenv("STRIPE_WEBHOOK_SECRET", "")
    stripe_price_id: str = os.getenv("STRIPE_PRICE_ID", "")
    public_url: str = os.getenv("PUBLIC_URL", "http://localhost:8000").rstrip("/")
    free_daily_limit: int = int(os.getenv("FREE_DAILY_LIMIT", "1"))
    premium_daily_limit: int = int(os.getenv("PREMIUM_DAILY_LIMIT", "10"))
    db_path: str = os.getenv("DB_PATH", "uranai.db")

    @property
    def billing_enabled(self) -> bool:
        return bool(self.stripe_secret_key and self.stripe_price_id)


settings = Settings()

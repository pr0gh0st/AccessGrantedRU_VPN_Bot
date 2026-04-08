from __future__ import annotations

from pathlib import Path
from typing import List

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import field_validator


class Settings(BaseSettings):
    """
    Application configuration loaded from environment variables.

    Notes:
    - Sensitive values must come from `.env` (or real environment variables).
    - Defaults are placeholders only to keep imports/linting working; the bot
      validates required fields at startup.
    """

    model_config = SettingsConfigDict(
        env_file=str(Path(__file__).resolve().parents[1] / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Telegram
    BOT_TOKEN: str = Field(default="")
    PAYMENT_TOKEN: str = Field(default="")
    ADMINS: str = Field(default="")  # comma-separated telegram user IDs

    # 3X-UI / XUI API
    XUI_API_URL: str = Field(default="")
    XUI_HOST: str = Field(default="")
    XUI_BASE_PATH: str = Field(default="")
    XUI_SERVER_NAME: str = Field(default="")
    XUI_USERNAME: str = Field(default="")
    XUI_PASSWORD: str = Field(default="")
    INBOUND_ID: int = Field(default=0)

    # Reality parameters for VLESS URL
    REALITY_PUBLIC_KEY: str = Field(default="")
    REALITY_FINGERPRINT: str = Field(default="")
    REALITY_SNI: str = Field(default="")
    REALITY_SHORT_ID: str = Field(default="")
    REALITY_SPIDER_X: str = Field(default="")

    # Subscription policy
    TRIAL_DAYS: int = Field(default=0)

    # Telegram Payments prices (minor currency units, e.g. cents)
    PRICE_1_MONTH: int = Field(default=0)
    PRICE_3_MONTHS: int = Field(default=0)
    PRICE_6_MONTHS: int = Field(default=0)
    PRICE_12_MONTHS: int = Field(default=0)
    CURRENCY: str = Field(default="USD")

    # Database
    DATABASE_URL: str = Field(default="sqlite+aiosqlite:///users.db")

    @field_validator("ADMINS", mode="before")
    @classmethod
    def _strip_admins(cls, v: object) -> str:
        if v is None:
            return ""
        return str(v).strip()

    @property
    def admin_ids(self) -> List[int]:
        if not self.ADMINS:
            return []
        ids: List[int] = []
        for part in self.ADMINS.split(","):
            part = part.strip()
            if not part:
                continue
            ids.append(int(part))
        return ids

    def validate_required(self) -> None:
        """
        Validate that critical configuration is present.

        Called from `app.py` during startup.
        """

        required_str_fields = [
            "BOT_TOKEN",
            "PAYMENT_TOKEN",
            "XUI_API_URL",
            "XUI_HOST",
            "XUI_BASE_PATH",
            "XUI_SERVER_NAME",
            "XUI_USERNAME",
            "XUI_PASSWORD",
            "REALITY_PUBLIC_KEY",
            "REALITY_FINGERPRINT",
            "REALITY_SNI",
            "REALITY_SHORT_ID",
            "REALITY_SPIDER_X",
        ]
        missing = [name for name in required_str_fields if not getattr(self, name)]
        if missing:
            raise RuntimeError(f"Не заполнены обязательные переменные окружения: {', '.join(missing)}")

        required_int_fields = ["INBOUND_ID", "TRIAL_DAYS"]
        for name in required_int_fields:
            if getattr(self, name) <= 0:
                raise RuntimeError(f"Переменная окружения `{name}` должна быть > 0")

        required_price_fields = ["PRICE_1_MONTH", "PRICE_3_MONTHS", "PRICE_6_MONTHS", "PRICE_12_MONTHS"]
        for name in required_price_fields:
            if getattr(self, name) <= 0:
                raise RuntimeError(f"Переменная окружения `{name}` должна быть > 0")

        if not self.CURRENCY:
            raise RuntimeError("Переменная окружения `CURRENCY` не заполнена")


settings = Settings()


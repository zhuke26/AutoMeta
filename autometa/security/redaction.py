from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any

from autometa.config import Settings

SECRET_KEY_PARTS = (
    "api_key",
    "authorization",
    "cookie",
    "password",
    "secret",
    "token",
)


class SecretRedactor:
    def __init__(self, settings: Settings):
        self.settings = settings

    def text(self, value: str) -> str:
        redacted = value
        for configured in (self.settings.llm_api_key, self.settings.pubmed_api_key):
            secret = (
                configured.get_secret_value()
                if hasattr(configured, "get_secret_value")
                else str(configured or "")
            )
            if secret:
                redacted = redacted.replace(secret, "[REDACTED]")
        return redacted

    def payload(self, value: Any) -> Any:
        if isinstance(value, str):
            return self.text(value)
        if isinstance(value, Mapping):
            return {
                str(key): (
                    "[REDACTED]"
                    if self._is_secret_key(str(key))
                    else self.payload(item)
                )
                for key, item in value.items()
            }
        if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
            return [self.payload(item) for item in value]
        return value

    @staticmethod
    def _is_secret_key(key: str) -> bool:
        normalized = re.sub(r"[^a-z0-9]+", "_", key.casefold()).strip("_")
        return any(part in normalized for part in SECRET_KEY_PARTS)

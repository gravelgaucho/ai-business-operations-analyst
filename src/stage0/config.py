from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    model_id: str = "mlx-community/Qwen3.8-27B-4bit"
    base_url: str = "http://127.0.0.1:8080/v1"
    timeout_seconds: float = 600.0

    @classmethod
    def from_environment(cls) -> Settings:
        return cls(
            model_id=os.getenv("MODEL_ID", cls.model_id),
            base_url=os.getenv("BASE_URL", cls.base_url).rstrip("/"),
            timeout_seconds=float(os.getenv("REQUEST_TIMEOUT_SECONDS", cls.timeout_seconds)),
        )

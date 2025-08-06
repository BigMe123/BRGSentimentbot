"""Configuration via environment variables using :mod:`pydantic-settings`."""

from __future__ import annotations

from typing import List

import os
from dataclasses import dataclass, field


try:  # pragma: no cover - optional dependency
    from pydantic_settings import BaseSettings  # type: ignore

    class Settings(BaseSettings):
        """Application settings loaded from environment variables."""

        NEWSAPI_KEY: str = "027e167533f7488bb9935e9ab1874e72"
        RSS_FEEDS: List[str] = [
            "https://feeds.bbci.co.uk/news/world/rss.xml",
            "https://www.aljazeera.com/xml/rss/all.xml",
        ]
        TOPICS: List[str] = ["markets"]
        INTERVAL: int = 30
        DB_PATH: str = "sentiment.db"
        VECTOR_INDEX_PATH: str = "vector.index"
        RULES_PATH: str = "rules.yml"
        SIM_PATH: str = "simulations.csv"
        WEBSOCKET_PORT: int = 8765
        GRADIO_PORT: int = 7860

        class Config:
            env_file = ".env"

    settings = Settings()
except Exception:  # pragma: no cover - fallback without pydantic

    @dataclass
    class Settings:
        NEWSAPI_KEY: str = os.getenv("NEWSAPI_KEY", "027e167533f7488bb9935e9ab1874e72")
        RSS_FEEDS: List[str] = field(
            default_factory=lambda: [
                "https://feeds.bbci.co.uk/news/world/rss.xml",
                "https://www.aljazeera.com/xml/rss/all.xml",
            ]
        )
        TOPICS: List[str] = field(default_factory=lambda: ["markets"])
        INTERVAL: int = int(os.getenv("INTERVAL", 30))
        DB_PATH: str = os.getenv("DB_PATH", "sentiment.db")
        VECTOR_INDEX_PATH: str = os.getenv("VECTOR_INDEX_PATH", "vector.index")
        RULES_PATH: str = os.getenv("RULES_PATH", "rules.yml")
        SIM_PATH: str = os.getenv("SIM_PATH", "simulations.csv")
        WEBSOCKET_PORT: int = int(os.getenv("WEBSOCKET_PORT", 8765))
        GRADIO_PORT: int = int(os.getenv("GRADIO_PORT", 7860))

    settings = Settings()

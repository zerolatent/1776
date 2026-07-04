from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path

from dotenv import load_dotenv


ROOT_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT_DIR / "data"
DB_PATH = DATA_DIR / "1776.sqlite3"

load_dotenv(ROOT_DIR / ".env", override=True)


@dataclass(frozen=True)
class Settings:
    app_name: str = "1776"
    database_path: Path = DB_PATH
    web_dir: Path = ROOT_DIR / "web"
    openai_api_key: str | None = os.getenv("OPENAI_API_KEY")
    openai_base_url: str | None = os.getenv("OPENAI_BASE_URL")
    openai_model: str = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    openstates_api_key: str | None = os.getenv("OPENSTATES_API_KEY")
    cors_origins: tuple[str, ...] = (
        "http://localhost:8000",
        "http://127.0.0.1:8000",
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:19006",
        "http://localhost:8081",
        "http://127.0.0.1:19006",
        "http://127.0.0.1:8081",
    )


settings = Settings()

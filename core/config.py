"""Centralized configuration loaded from environment variables."""
import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env from project root
_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(_ROOT / ".env")


class Settings:
    APP_NAME: str = os.getenv("APP_NAME", "Lingua Nova")
    PHASE: int = int(os.getenv("PHASE", "1"))

    OLLAMA_HOST: str = os.getenv("OLLAMA_HOST", "http://localhost:11434").rstrip("/")
    OLLAMA_MODEL: str = os.getenv("OLLAMA_MODEL", "qwen2.5:14b-instruct-q4_K_M")

    DATABASE_URL: str = os.getenv("DATABASE_URL", f"sqlite:///{_ROOT / 'data' / 'lingua.db'}")
    CEFR_LEVELS: list[str] = [s.strip() for s in os.getenv("CEFR_LEVELS", "A1,A2,B1,B2,C1,C2").split(",")]

    DATA_DIR: Path = _ROOT / "data"
    SEEDS_DIR: Path = DATA_DIR / "seeds"


settings = Settings()

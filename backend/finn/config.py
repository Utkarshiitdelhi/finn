"""All runtime settings come from environment variables (see backend/.env.example)."""
import os
from pathlib import Path

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BACKEND_DIR / ".env")


def env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


DATABASE_URL = env("DATABASE_URL", f"sqlite:///{BACKEND_DIR / 'finn.db'}")
# Supabase gives postgres:// URLs; SQLAlchemy wants postgresql://
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)
# SQLAlchemy 2.1 defaults postgresql:// to psycopg 3; we ship psycopg2-binary
if DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+psycopg2://", 1)

GEMINI_API_KEY = env("GEMINI_API_KEY")
GROQ_API_KEY = env("GROQ_API_KEY")
EXPO_ACCESS_TOKEN = env("EXPO_ACCESS_TOKEN")  # optional; only if push security is enabled in Expo
ADMIN_TOKEN = env("ADMIN_TOKEN", "dev")  # guards /admin/* job triggers

# Model names change often: check them when you create the keys.
MODELS = {
    "groq_small": env("GROQ_SMALL_MODEL", "openai/gpt-oss-20b"),
    "groq_whisper": env("GROQ_WHISPER_MODEL", "whisper-large-v3-turbo"),
    "gemini_small": env("GEMINI_SMALL_MODEL", "gemini-flash-lite-latest"),
    "gemini_mid": env("GEMINI_MID_MODEL", "gemini-flash-latest"),
    "gemini_strong": env("GEMINI_STRONG_MODEL", "gemini-pro-latest"),
}

PORTFOLIO_PATH = Path(env("PORTFOLIO_PATH", str(BACKEND_DIR / "data" / "portfolio.json")))
CACHE_DIR = Path(env("CACHE_DIR", str(BACKEND_DIR / "data" / "cache")))
SNAPSHOT_DIR = BACKEND_DIR / "data" / "snapshots"

# Tier thresholds (first guesses; tune on a real week of filings)
TIER_S, TIER_A, TIER_B = 0.75, 0.50, 0.25

DEFAULT_PRICE_PCT = 5.0
DEFAULT_VOL_RATIO = 2.0

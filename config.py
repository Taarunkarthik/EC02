import os
import json
import secrets
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY") or secrets.token_hex(32)
    DATABASE_URL = os.environ.get("DATABASE_URL") or os.environ.get("SUPABASE_DATABASE_URL")
    DATABASE_PATH = os.environ.get("DATABASE_PATH", str(BASE_DIR / "database" / "exit_code_0.db"))
    SCHEMA_PATH = str(BASE_DIR / "database" / "schema.sql")
    SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
    SUPABASE_ANON_KEY = os.environ.get("SUPABASE_ANON_KEY", "")

    # Static Data Paths
    CONFIG_JSON_PATH = str(BASE_DIR / "data" / "config.json")
    QUESTIONS_JSON_PATH = str(BASE_DIR / "data" / "questions.json")

    # Admin Credentials
    ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "admin")
    ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "exitcode0_admin_2026")

    @classmethod
    def load_event_config(cls):
        try:
            with open(cls.CONFIG_JSON_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {
                "event_name": "EXIT CODE 0",
                "tagline": "Find the Bug. Fix the Code. Exit Clean.",
                "duration_minutes": 40,
                "team_min_size": 2,
                "team_max_size": 3,
                "expected_participants": 60,
                "debug_weight": 1.0,
                "total_questions": 30
            }

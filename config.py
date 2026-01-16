"""
DamaDam Bot - Configuration File
Smart config handling for Local + GitHub Actions
"""

import os
from pathlib import Path
from typing import Optional, Any

# Base paths
BASE_DIR = Path(__file__).resolve().parent
LOG_DIR = BASE_DIR / "logs"
LOG_DIR.mkdir(exist_ok=True)

BASE_URL = "https://damadam.pk"


class Config:
    """Smart configuration with priority: GitHub Secrets > env > .env > default"""

    @staticmethod
    def get(key: str, default: Any = None, required: bool = False) -> Any:
        # 1. GitHub Actions / Environment variable
        value = os.getenv(key)

        # 2. .env file (local development ke liye)
        if not value and (BASE_DIR / ".env").exists():
            from dotenv import load_dotenv
            load_dotenv(BASE_DIR / ".env")
            value = os.getenv(key)

        # 3. Default value
        if value is None:
            value = default

        if required and value is None:
            raise ValueError(f"Missing required configuration: {key}")

        return value

    # ── Authentication ───────────────────────────────────────────────
    LOGIN_NICK     = get("DD_LOGIN_EMAIL",     required=True)
    LOGIN_PASS     = get("DD_LOGIN_PASS",     required=True)
    COOKIE_FILE    = get("DD_COOKIE_FILE",    str(BASE_DIR / "damadam_cookies.pkl"))

    # ── Google Sheets ────────────────────────────────────────────────
    SHEET_ID          = get("DD_SHEET_ID",          required=True)
    PROFILES_SHEET_ID = get("DD_PROFILES_SHEET_ID", "16t-D8dCXFvheHEpncoQ_VnXQKkrEREAup7c1ZLFXvu0")
    CREDENTIALS_FILE  = get("DD_CREDENTIALS_FILE",  str(BASE_DIR / "credentials.json"))

    # ── Bot Behavior ─────────────────────────────────────────────────
    DEBUG           = get("DD_DEBUG",           "0") == "1"
    MAX_PROFILES    = int(get("DD_MAX_PROFILES", "0") or 0)   # 0 = unlimited
    MAX_POST_PAGES  = int(get("DD_MAX_POST_PAGES", "5"))
    AUTO_PUSH       = get("DD_AUTO_PUSH",       "0") == "1"
    WAIT_MIN        = float(get("DD_WAIT_MIN",  "4.5"))
    WAIT_MAX        = float(get("DD_WAIT_MAX",  "9.5"))

    # ── Browser / Selenium ───────────────────────────────────────────
    HEADLESS        = get("DD_HEADLESS",        "1") == "1"
    USE_WEBDRIVER_MANAGER = get("DD_USE_WEBDRIVER_MANAGER", "1") == "1"


# Quick check jab file import ho
if __name__ == "__main__":
    print("Config check:")
    print(f"Login nick     : {Config.LOGIN_NICK}")
    print(f"Sheet ID       : {Config.SHEET_ID}")
    print(f"Debug mode     : {Config.DEBUG}")
    print(f"Headless       : {Config.HEADLESS}")
    print(f"Use webdriver-manager : {Config.USE_WEBDRIVER_MANAGER}")

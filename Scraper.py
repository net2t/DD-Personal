"""
DamaDam Bot v2.0.1
POST MODE (TEST VERSION)
GitHub Actions Compatible
"""

import time
import os
import sys
import re
import pickle
import argparse
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional, Dict, List

import gspread
from google.oauth2.service_account import Credentials

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException

from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.service import Service

from rich.console import Console

console = Console()

# ============================================================================
# CONFIG
# ============================================================================

BASE_URL = "https://damadam.pk"
VERSION = "2.0.1"

class Config:
    LOGIN_EMAIL = os.getenv("DD_LOGIN_EMAIL")
    LOGIN_PASS  = os.getenv("DD_LOGIN_PASS")

    SHEET_ID = os.getenv("DD_SHEET_ID")
    CREDENTIALS_FILE = "credentials.json"

    COOKIE_FILE = "cookies.pkl"

    MAX_POST_PAGES = int(os.getenv("DD_MAX_POST_PAGES", "3"))
    DEBUG = os.getenv("DD_DEBUG", "0") == "1"

# ============================================================================
# LOGGER
# ============================================================================

class Logger:
    def log(self, msg, level="INFO"):
        ts = datetime.utcnow().strftime("%H:%M:%S")
        console.print(f"[{ts}] [{level}] {msg}")

    def info(self, m): self.log(m, "INFO")
    def success(self, m): self.log(m, "SUCCESS")
    def warning(self, m): self.log(m, "WARNING")
    def error(self, m): self.log(m, "ERROR")

logger = Logger()

# ============================================================================
# BROWSER
# ============================================================================

class BrowserManager:
    def __init__(self):
        self.driver = None

    def setup(self):
        opts = Options()
        opts.add_argument("--headless=new")
        opts.add_argument("--no-sandbox")
        opts.add_argument("--disable-dev-shm-usage")
        opts.add_argument("--window-size=1920,1080")

        self.driver = webdriver.Chrome(
            service=Service(ChromeDriverManager().install()),
            options=opts
        )
        self.driver.set_page_load_timeout(40)
        logger.success("Browser ready")
        return self.driver

    def login(self) -> bool:
        self.driver.get(BASE_URL)
        time.sleep(2)

        # Try cookies
        if os.path.exists(Config.COOKIE_FILE):
            try:
                with open(Config.COOKIE_FILE, "rb") as f:
                    cookies = pickle.load(f)
                for c in cookies:
                    self.driver.add_cookie(c)
                self.driver.refresh()
                time.sleep(2)
                if "login" not in self.driver.current_url.lower():
                    logger.success("Login via cookies")
                    return True
            except:
                pass

        # Fresh login
        logger.info("Fresh login")
        self.driver.get(f"{BASE_URL}/login/")
        time.sleep(3)

        try:
            nick = self.driver.find_element(By.NAME, "nick")
            pw   = self.driver.find_element(By.NAME, "pass")

            nick.send_keys(Config.LOGIN_EMAIL)
            pw.send_keys(Config.LOGIN_PASS)
            pw.submit()

            time.sleep(4)
            if "login" not in self.driver.current_url.lower():
                with open(Config.COOKIE_FILE, "wb") as f:
                    pickle.dump(self.driver.get_cookies(), f)
                logger.success("Login successful")
                return True
        except Exception as e:
            logger.error(f"Login failed: {e}")

        return False

    def close(self):
        if self.driver:
            self.driver.quit()

# ============================================================================
# SHEETS
# ============================================================================

class SheetsManager:
    def __init__(self):
        self.client = None

    def connect(self):
        scope = ["https://www.googleapis.com/auth/spreadsheets"]
        creds = Credentials.from_service_account_file(
            Config.CREDENTIALS_FILE, scopes=scope
        )
        self.client = gspread.authorize(creds)
        logger.success("Google Sheets connected")

    def get_sheet(self, name: str):
        wb = self.client.open_by_key(Config.SHEET_ID)
        try:
            return wb.worksheet(name)
        except:
            ws = wb.add_worksheet(title=name, rows=500, cols=10)
            ws.append_row([
                "TYPE","TITLE","CONTENT","IMAGE","TAGS",
                "STATUS","POST_URL","TIMESTAMP","NOTES"
            ])
            return ws

# ============================================================================
# POST BOT (TEST)
# ============================================================================

class PostBot:
    def __init__(self, driver, sheet):
        self.driver = driver
        self.sheet = sheet

    def run(self):
        rows = self.sheet.get_all_values()[1:]
        logger.info(f"Post queue: {len(rows)}")

        for idx, row in enumerate(rows, start=2):
            status = row[5].strip().lower()
            if status == "done":
                continue

            title = row[1]
            content = row[2]

            try:
                self.create_post(title, content)
                self.sheet.update_cell(idx, 6, "DONE")
                self.sheet.update_cell(
                    idx, 8,
                    datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
                )
                logger.success(f"Post done: {title}")
            except Exception as e:
                self.sheet.update_cell(idx, 6, "ERROR")
                self.sheet.update_cell(idx, 9, str(e))
                logger.error(str(e))

    def create_post(self, title, content):
        self.driver.get(f"{BASE_URL}/post/new/")
        WebDriverWait(self.driver, 10).until(
            EC.presence_of_element_located((By.NAME, "title"))
        )

        self.driver.find_element(By.NAME, "title").send_keys(title)
        self.driver.find_element(By.NAME, "content").send_keys(content)
        self.driver.find_element(By.CSS_SELECTOR, "button[type='submit']").click()

        time.sleep(4)

# ============================================================================
# MAIN
# ============================================================================

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", required=True, choices=["post"])
    args = parser.parse_args()

    if not Config.LOGIN_EMAIL or not Config.LOGIN_PASS:
        logger.error("Secrets missing")
        sys.exit(1)

    browser = BrowserManager()
    driver = browser.setup()

    if not browser.login():
        logger.error("Login failed")
        sys.exit(1)

    sheets = SheetsManager()
    sheets.connect()

    if args.mode == "post":
        sheet = sheets.get_sheet("PostQueue")
        PostBot(driver, sheet).run()

    browser.close()

if __name__ == "__main__":
    main()

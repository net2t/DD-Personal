"""
DamaDam Bot v2.0.1 - 2026 Updated
Main file - modular aur stable tareeqa
"""

import time
import pickle
import random
import argparse
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional, Dict, Any

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from webdriver_manager.chrome import ChromeDriverManager

from rich.console import Console

# ── Local files ──────────────────────────────────────────────────────
from config import Config, BASE_URL, LOG_DIR

console = Console()

# ============================================================================
# Logging
# ============================================================================

class Logger:
    def __init__(self, mode: str = "bot"):
        self.mode = mode
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.logfile = LOG_DIR / f"{mode}_{ts}.log"

    def _pkt_time(self):
        return datetime.now(timezone.utc) + timedelta(hours=5)

    def log(self, msg: str, level: str = "INFO"):
        t = self._pkt_time().strftime("%H:%M:%S")
        color = {"INFO":"white", "OK":"green", "WARN":"yellow", "ERROR":"red", "DEBUG":"cyan"}.get(level, "white")
        
        console.print(f"[{t}] [{level}] {msg}", style=color)
        
        with open(self.logfile, "a", encoding="utf-8") as f:
            f.write(f"[{t}] [{level}] {msg}\n")

    def info(self, m):  self.log(m, "INFO")
    def ok(self, m):    self.log(m, "OK")
    def warn(self, m):  self.log(m, "WARN")
    def error(self, m): self.log(m, "ERROR")
    def debug(self, m): 
        if Config.DEBUG: self.log(m, "DEBUG")


# ============================================================================
# Browser Manager
# ============================================================================

class BrowserManager:
    def __init__(self, logger: Logger):
        self.logger = logger
        self.driver: Optional[webdriver.Chrome] = None

    def setup(self) -> bool:
        try:
            options = Options()
            options.add_argument("--no-sandbox")
            options.add_argument("--disable-dev-shm-usage")
            options.add_argument("--disable-blink-features=AutomationControlled")
            options.add_argument("--window-size=1280,900")
            options.add_experimental_option("excludeSwitches", ["enable-automation"])
            options.add_experimental_option('useAutomationExtension', False)

            if Config.HEADLESS:
                options.add_argument("--headless=new")

            if Config.USE_WEBDRIVER_MANAGER:
                service = Service(ChromeDriverManager().install())
                self.driver = webdriver.Chrome(service=service, options=options)
            else:
                self.driver = webdriver.Chrome(options=options)

            self.driver.set_page_load_timeout(45)
            self.driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
            
            self.logger.ok("Browser setup ho gaya")
            return True

        except Exception as e:
            self.logger.error(f"Browser start nahi hua → {e}")
            return False

    def login(self) -> bool:
        if not self.driver:
            return False

        try:
            # Pehle cookies try karte hain
            if self._load_cookies():
                self.driver.get(BASE_URL)
                time.sleep(random.uniform(1.8, 3.2))
                if "login" not in self.driver.current_url.lower():
                    self.logger.ok("Cookies se login ho gaya")
                    return True

            # Fresh login
            self.driver.get(f"{BASE_URL}/login/")
            time.sleep(random.uniform(2.5, 4.0))

            wait = WebDriverWait(self.driver, 12)

            nick_field = wait.until(EC.presence_of_element_located(
                (By.CSS_SELECTOR, "input[name='nick']")))
            
            pass_field = self.driver.find_element(By.CSS_SELECTOR, "input[name='pass']")
            submit_btn = self.driver.find_element(By.CSS_SELECTOR, "button[type='submit']")

            nick_field.clear()
            nick_field.send_keys(Config.LOGIN_NICK)
            time.sleep(0.6)

            pass_field.clear()
            pass_field.send_keys(Config.LOGIN_PASS)
            time.sleep(0.7)

            submit_btn.click()
            time.sleep(random.uniform(4.0, 6.5))

            if "login" not in self.driver.current_url.lower():
                self._save_cookies()
                self.logger.ok("Fresh login successful")
                return True

            self.logger.error("Login fail ho gaya")
            return False

        except Exception as e:
            self.logger.error(f"Login ke doran masla: {e}")
            return False

    def _save_cookies(self):
        try:
            with open(Config.COOKIE_FILE, "wb") as f:
                pickle.dump(self.driver.get_cookies(), f)
            self.logger.debug("Cookies save ho gaye")
        except Exception as e:
            self.logger.warn(f"Cookies save nahi hue: {e}")

    def _load_cookies(self) -> bool:
        try:
            if not Config.COOKIE_FILE.exists():
                return False

            self.driver.get(BASE_URL)
            time.sleep(1.8)

            with open(Config.COOKIE_FILE, "rb") as f:
                cookies = pickle.load(f)

            for cookie in cookies:
                try:
                    self.driver.add_cookie(cookie)
                except:
                    pass

            self.driver.refresh()
            time.sleep(2.0)
            return True

        except:
            return False

    def close(self):
        if self.driver:
            try:
                self.driver.quit()
                self.logger.info("Browser band ho gaya")
            except:
                pass


# ============================================================================
# Very Basic Profile Scraper (example)
# ============================================================================

class ProfileScraper:
    def __init__(self, driver, logger):
        self.driver = driver
        self.logger = logger

    def get_profile_info(self, nick: str) -> Optional[Dict]:
        url = f"{BASE_URL}/users/{nick}/"
        try:
            self.logger.info(f"Profile scrape kar raha hoon: {nick}")
            self.driver.get(url)
            
            wait = WebDriverWait(self.driver, 10)
            wait.until(EC.presence_of_element_located((By.TAG_NAME, "h1")))

            info = {"nick": nick, "status": "Unknown", "city": "", "posts": "0"}

            # Status check (simple tareeqa)
            page = self.driver.page_source.lower()
            if "suspended" in page:
                info["status"] = "Suspended"
            elif "unverified" in page or "tomato" in page:
                info["status"] = "Unverified"
            else:
                info["status"] = "OK"

            self.logger.ok(f"{nick} → {info['status']}")
            return info

        except Exception as e:
            self.logger.error(f"Profile nahi mila ya masla: {e}")
            return None


# ============================================================================
# Main Entry
# ============================================================================

def main():
    parser = argparse.ArgumentParser(description="DamaDam Bot 2026")
    parser.add_argument("--mode", choices=["test", "msg", "post", "inbox"], default="test")
    args = parser.parse_args()

    logger = Logger(mode=args.mode)
    logger.info(f"Bot shuru → Mode: {args.mode} | {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    browser = BrowserManager(logger)
    if not browser.setup():
        return

    if not browser.login():
        browser.close()
        return

    # Test ke liye simple profile check
    if args.mode == "test":
        scraper = ProfileScraper(browser.driver, logger)
        test_nicks = ["testuser", "pakistan", "outlawz"]  # change kar lena
        
        for nick in test_nicks:
            info = scraper.get_profile_info(nick)
            if info:
                logger.ok(str(info))
            time.sleep(random.uniform(3.5, 7.0))

    logger.ok("Kaam mukammal")
    browser.close()


if __name__ == "__main__":
    main()

"""
DamaDam Bot V2.0.0 - Complete Refactored Version (Updated Jan 2026)
Organized, Clean, and Modular Architecture

Modes:
  --mode msg       : Send personal messages (Phase 1)
  --mode post      : Create new posts (Phase 2) 
  --mode inbox     : Monitor & reply to inbox (Phase 3)
"""

import time
import os
import sys
import re
import pickle
import argparse
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import gspread
from google.oauth2.service_account import Credentials
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, WebDriverException, NoSuchElementException
from gspread.exceptions import WorksheetNotFound
from rich.console import Console
from rich.table import Table

console = Console()

# ============================================================================
# CONFIGURATION (same as before)
# ============================================================================

VERSION = "2.0.1"  # updated version
BASE_URL = "https://damadam.pk"

class Config:
    """Centralized Configuration"""
    
    LOGIN_EMAIL = os.getenv("DD_LOGIN_EMAIL", "0utLawZ")
    LOGIN_PASS = os.getenv("DD_LOGIN_PASS", "asdasd")
    COOKIE_FILE = os.getenv("COOKIE_FILE", "damadam_cookies.pkl")
    
    SHEET_ID = os.getenv("DD_SHEET_ID", "1xph0dra5-wPcgMXKubQD7A2CokObpst7o2rWbDA10t8")
    PROFILES_SHEET_ID = os.getenv("DD_PROFILES_SHEET_ID", "16t-D8dCXFvheHEpncoQ_VnXQKkrEREAup7c1ZLFXvu0")
    CREDENTIALS_FILE = os.getenv("CREDENTIALS_FILE", "credentials.json")
    
    CHROMEDRIVER_PATH = os.getenv("CHROMEDRIVER_PATH", "chromedriver.exe")
    
    DEBUG = os.getenv("DD_DEBUG", "0") == "1"
    MAX_PROFILES = int(os.getenv("DD_MAX_PROFILES", "0"))
    MAX_POST_PAGES = int(os.getenv("DD_MAX_POST_PAGES", "4"))
    AUTO_PUSH = os.getenv("DD_AUTO_PUSH", "0") == "1"
    
    LOG_DIR = Path("logs")
    LOG_DIR.mkdir(exist_ok=True)

# ============================================================================
# LOGGING SYSTEM (same)
# ============================================================================

class Logger:
    def __init__(self, mode: str = "general"):
        self.mode = mode
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.log_file = Config.LOG_DIR / f"{mode}_{timestamp}.log"
        
    def log(self, message: str, level: str = "INFO"):
        pkt_time = self._get_pkt_time()
        timestamp = pkt_time.strftime("%H:%M:%S")
        
        color_map = {
            "INFO": "white",
            "SUCCESS": "green",
            "WARNING": "yellow",
            "ERROR": "red",
            "DEBUG": "blue"
        }
        color = color_map.get(level, "white")
        console.print(f"[{timestamp}] [{level}] {message}", style=color)
        
        with open(self.log_file, "a", encoding="utf-8") as f:
            f.write(f"[{timestamp}] [{level}] {message}\n")
    
    def info(self, msg): self.log(msg, "INFO")
    def success(self, msg): self.log(msg, "SUCCESS")
    def warning(self, msg): self.log(msg, "WARNING")
    def error(self, msg): self.log(msg, "ERROR")
    def debug(self, msg): 
        if Config.DEBUG:
            self.log(msg, "DEBUG")
    
    @staticmethod
    def _get_pkt_time():
        return datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(hours=5)

# ============================================================================
# BROWSER MANAGER - Updated with better anti-detection & fallback selectors
# ============================================================================

class BrowserManager:
    def __init__(self, logger: Logger):
        self.logger = logger
        self.driver = None
        
    def setup(self) -> Optional[webdriver.Chrome]:
        try:
            opts = Options()
            opts.add_argument("--headless=new")
            opts.add_argument("--window-size=1920,1080")
            opts.add_argument("--disable-blink-features=AutomationControlled")
            opts.add_argument("--no-sandbox")
            opts.add_argument("--disable-dev-shm-usage")
            opts.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")
            opts.add_experimental_option('excludeSwitches', ['enable-automation'])
            opts.add_experimental_option('useAutomationExtension', False)
            opts.page_load_strategy = "eager"
            
            if Config.CHROMEDRIVER_PATH and os.path.exists(Config.CHROMEDRIVER_PATH):
                self.driver = webdriver.Chrome(service=Service(Config.CHROMEDRIVER_PATH), options=opts)
            else:
                self.driver = webdriver.Chrome(options=opts)
                
            self.driver.set_page_load_timeout(60)  # increased
            self.driver.execute_script("Object.defineProperty(navigator,'webdriver',{get:()=>undefined})")
            self.logger.success("Browser setup complete")
            return self.driver
        except Exception as e:
            self.logger.error(f"Browser setup failed: {e}")
            return None
    
    def login(self) -> bool:
        if not self.driver:
            return False
            
        try:
            # Try cookies first
            if self._load_cookies():
                self.driver.get(BASE_URL)
                time.sleep(3)
                if 'login' not in self.driver.current_url.lower():
                    self.logger.success("Logged in via cookies")
                    return True
            
            # Fresh login with fallback selectors
            self.driver.get(f"{BASE_URL}/login/")
            time.sleep(5)  # increased wait
            
            wait = WebDriverWait(self.driver, 15)
            
            # Nickname / Username field - multiple fallbacks
            nick_selectors = [
                (By.CSS_SELECTOR, "#nick, input[name='nick']"),
                (By.NAME, "nick"),
                (By.NAME, "username"),
                (By.CSS_SELECTOR, "input[type='text'][autocomplete='username']"),
                (By.CSS_SELECTOR, "input[placeholder*='nick' i], input[placeholder*='user' i]")
            ]
            
            nick = None
            for by, value in nick_selectors:
                try:
                    nick = wait.until(EC.presence_of_element_located((by, value)))
                    self.logger.success(f"Nick field mila using: {value}")
                    break
                except:
                    continue
            
            if not nick:
                self.driver.save_screenshot("login_nick_fail.png")
                self.logger.error("Nickname field nahi mila - debug screenshot save ho gaya")
                return False
            
            # Password field fallbacks
            pw_selectors = [
                (By.CSS_SELECTOR, "#pass, input[name='pass']"),
                (By.NAME, "pass"),
                (By.NAME, "password"),
                (By.CSS_SELECTOR, "input[type='password']")
            ]
            
            pw = None
            for by, value in pw_selectors:
                try:
                    pw = self.driver.find_element(by, value)
                    break
                except:
                    continue
            
            if not pw:
                self.logger.error("Password field nahi mila")
                return False
            
            # Submit button fallbacks
            btn_selectors = [
                (By.CSS_SELECTOR, "button[type='submit']"),
                (By.CSS_SELECTOR, "button.btn, button.btn-primary"),
                (By.XPATH, "//button[contains(translate(text(),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'login')]"),
                (By.CSS_SELECTOR, "input[type='submit']")
            ]
            
            btn = None
            for by, value in btn_selectors:
                try:
                    btn = self.driver.find_element(by, value)
                    break
                except:
                    continue
            
            if not btn:
                self.logger.error("Submit button nahi mila")
                return False
            
            # Fill and submit
            nick.clear()
            nick.send_keys(Config.LOGIN_EMAIL)
            time.sleep(0.7)
            
            pw.clear()
            pw.send_keys(Config.LOGIN_PASS)
            time.sleep(0.7)
            
            btn.click()
            time.sleep(6)
            
            if 'login' not in self.driver.current_url.lower():
                self._save_cookies()
                self.logger.success("Login successful")
                return True
            
            self.logger.error("Login failed - wrong credentials ya page change?")
            return False
            
        except Exception as e:
            self.logger.error(f"Login error: {e}")
            return False
    
    def _save_cookies(self):
        try:
            with open(Config.COOKIE_FILE, 'wb') as f:
                pickle.dump(self.driver.get_cookies(), f)
            self.logger.success("Cookies saved")
        except Exception as e:
            self.logger.warning(f"Cookie save failed: {e}")
    
    def _load_cookies(self) -> bool:
        try:
            if not os.path.exists(Config.COOKIE_FILE):
                return False
            
            self.driver.get(BASE_URL)
            time.sleep(3)
            
            with open(Config.COOKIE_FILE, 'rb') as f:
                cookies = pickle.load(f)
            
            for c in cookies:
                try:
                    self.driver.add_cookie(c)
                except:
                    pass
            
            self.driver.refresh()
            time.sleep(3)
            return True
        except:
            return False
    
    def close(self):
        if self.driver:
            self.driver.quit()
            self.logger.info("Browser closed")

# ============================================================================
# Baqi classes same hain (SheetsManager, MessageRecorder, ProfileScraper etc)
# Sirf BrowserManager mein changes kiye hain
# ============================================================================

# Agar baqi parts bhi chahiye to bata dena, warna yeh file ab login ke liye bohot strong hai

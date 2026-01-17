# ============================================================================
# bot_config.py - Centralized Configuration
# ============================================================================

import os
from pathlib import Path

class Config:
    """Centralized bot configuration"""
    
    # Authentication
    LOGIN_EMAIL = os.getenv("DD_LOGIN_EMAIL", "0utLawZ")
    LOGIN_PASS = os.getenv("DD_LOGIN_PASS", "asdasd")
    COOKIE_FILE = os.getenv("COOKIE_FILE", "damadam_cookies.pkl")
    
    # Google Sheets
    SHEET_ID = os.getenv("DD_SHEET_ID", "1xph0dra5-wPcgMXKubQD7A2CokObpst7o2rWbDA10t8")
    PROFILES_SHEET_ID = os.getenv("DD_PROFILES_SHEET_ID", "16t-D8dCXFvheHEpncoQ_VnXQKkrEREAup7c1ZLFXvu0")
    CREDENTIALS_FILE = os.getenv("CREDENTIALS_FILE", "credentials.json")
    
    # Browser
    CHROMEDRIVER_PATH = os.getenv("CHROMEDRIVER_PATH", "chromedriver.exe")
    
    # Bot Settings
    DEBUG = os.getenv("DD_DEBUG", "0") == "1"
    MAX_PROFILES = int(os.getenv("DD_MAX_PROFILES", "0"))
    MAX_POST_PAGES = int(os.getenv("DD_MAX_POST_PAGES", "4"))
    AUTO_PUSH = os.getenv("DD_AUTO_PUSH", "0") == "1"
    
    # URLs
    BASE_URL = "https://damadam.pk"
    LOGIN_URL = f"{BASE_URL}/login/"
    HOME_URL = BASE_URL
    
    # Logging
    LOG_DIR = Path("logs")
    LOG_DIR.mkdir(exist_ok=True)

# ============================================================================
# bot_logger.py - Enhanced Logging System
# ============================================================================

from datetime import datetime, timedelta, timezone
from rich.console import Console

console = Console()

class Logger:
    """Enhanced logger with file and console output"""
    
    def __init__(self, mode: str = "general"):
        self.mode = mode
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.log_file = Config.LOG_DIR / f"{mode}_{timestamp}.log"
        
        # Create log file
        with open(self.log_file, "w", encoding="utf-8") as f:
            f.write(f"DamaDam Bot - {mode.upper()} Mode\n")
            f.write(f"Started: {datetime.now()}\n")
            f.write("="*70 + "\n\n")
    
    def _log(self, message: str, level: str = "INFO"):
        """Internal log method"""
        pkt_time = self._get_pkt_time()
        timestamp = pkt_time.strftime("%H:%M:%S")
        
        # Console output with colors
        color_map = {
            "INFO": "white",
            "SUCCESS": "green",
            "WARNING": "yellow",
            "ERROR": "red",
            "DEBUG": "cyan"
        }
        color = color_map.get(level, "white")
        
        if level == "INFO":
            console.print(f"[{timestamp}] {message}")
        else:
            console.print(f"[{timestamp}] [{level}] {message}", style=color)
        
        # File output
        with open(self.log_file, "a", encoding="utf-8") as f:
            f.write(f"[{timestamp}] [{level}] {message}\n")
    
    def info(self, msg: str):
        self._log(msg, "INFO")
    
    def success(self, msg: str):
        self._log(msg, "SUCCESS")
    
    def warning(self, msg: str):
        self._log(msg, "WARNING")
    
    def error(self, msg: str):
        self._log(msg, "ERROR")
    
    def debug(self, msg: str):
        if Config.DEBUG:
            self._log(msg, "DEBUG")
    
    @staticmethod
    def _get_pkt_time():
        """Get Pakistan time"""
        return datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(hours=5)

# ============================================================================
# bot_browser.py - Browser Management
# ============================================================================

import time
import pickle
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

class BrowserManager:
    """Manages browser setup and authentication"""
    
    def __init__(self, logger):
        self.logger = logger
        self.driver = None
    
    def setup(self):
        """Setup headless Chrome browser"""
        try:
            opts = Options()
            opts.add_argument("--headless=new")
            opts.add_argument("--window-size=1920,1080")
            opts.add_argument("--disable-blink-features=AutomationControlled")
            opts.add_experimental_option('excludeSwitches', ['enable-automation'])
            opts.add_experimental_option('useAutomationExtension', False)
            opts.add_argument("--no-sandbox")
            opts.add_argument("--disable-dev-shm-usage")
            opts.add_argument("--disable-gpu")
            opts.page_load_strategy = "eager"
            
            # Try to use specified chromedriver
            if Config.CHROMEDRIVER_PATH and os.path.exists(Config.CHROMEDRIVER_PATH):
                service = Service(Config.CHROMEDRIVER_PATH)
                self.driver = webdriver.Chrome(service=service, options=opts)
            else:
                self.driver = webdriver.Chrome(options=opts)
            
            self.driver.set_page_load_timeout(45)
            self.driver.execute_script(
                "Object.defineProperty(navigator,'webdriver',{get:()=>undefined})"
            )
            
            self.logger.debug("Browser setup complete")
            return self.driver
            
        except Exception as e:
            self.logger.error(f"Browser setup failed: {e}")
            return None
    
    def login(self) -> bool:
        """Login to DamaDam"""
        if not self.driver:
            return False
        
        try:
            # Try loading cookies first
            if self._load_cookies():
                self.driver.get(Config.HOME_URL)
                time.sleep(2)
                
                # Check if still logged in
                current_url = self.driver.current_url.lower()
                if 'login' not in current_url and 'signup' not in current_url:
                    self.logger.debug("Logged in via cookies")
                    return True
                else:
                    self.logger.debug("Cookies expired, fresh login needed")
            
            # Fresh login
            self.logger.debug("Performing fresh login...")
            self.driver.get(Config.LOGIN_URL)
            time.sleep(3)
            
            # Find and fill login form
            nick_input = WebDriverWait(self.driver, 8).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "#nick, input[name='nick']"))
            )
            pass_input = self.driver.find_element(By.CSS_SELECTOR, "#pass, input[name='pass']")
            submit_btn = self.driver.find_element(By.CSS_SELECTOR, "button[type='submit']")
            
            nick_input.clear()
            nick_input.send_keys(Config.LOGIN_EMAIL)
            time.sleep(0.5)
            
            pass_input.clear()
            pass_input.send_keys(Config.LOGIN_PASS)
            time.sleep(0.5)
            
            submit_btn.click()
            time.sleep(4)
            
            # Verify login
            if 'login' not in self.driver.current_url.lower():
                self._save_cookies()
                self.logger.debug("Fresh login successful")
                return True
            
            self.logger.error("Login failed - check credentials")
            return False
            
        except Exception as e:
            self.logger.error(f"Login error: {e}")
            return False
    
    def _save_cookies(self):
        """Save cookies to file"""
        try:
            with open(Config.COOKIE_FILE, 'wb') as f:
                pickle.dump(self.driver.get_cookies(), f)
            self.logger.debug("Cookies saved")
        except Exception as e:
            self.logger.warning(f"Cookie save failed: {e}")
    
    def _load_cookies(self) -> bool:
        """Load cookies from file"""
        try:
            if not os.path.exists(Config.COOKIE_FILE):
                return False
            
            self.driver.get(Config.HOME_URL)
            time.sleep(2)
            
            with open(Config.COOKIE_FILE, 'rb') as f:
                cookies = pickle.load(f)
            
            for cookie in cookies:
                try:
                    self.driver.add_cookie(cookie)
                except:
                    pass
            
            self.driver.refresh()
            time.sleep(2)
            self.logger.debug("Cookies loaded")
            return True
            
        except Exception as e:
            self.logger.debug(f"Cookie load failed: {e}")
            return False
    
    def close(self):
        """Close browser"""
        if self.driver:
            try:
                self.driver.quit()
                self.logger.debug("Browser closed")
            except:
                pass

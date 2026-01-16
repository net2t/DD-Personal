"""
DamaDam Bot V2.0.0 - Complete Refactored Version
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
# CONFIGURATION
# ============================================================================

VERSION = "2.0.0"
BASE_URL = "https://damadam.pk"

class Config:
    """Centralized Configuration"""
    
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
    
    # Logging
    LOG_DIR = Path("logs")
    LOG_DIR.mkdir(exist_ok=True)

# ============================================================================
# LOGGING SYSTEM
# ============================================================================

class Logger:
    """Enhanced logging with file support"""
    
    def __init__(self, mode: str = "general"):
        self.mode = mode
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.log_file = Config.LOG_DIR / f"{mode}_{timestamp}.log"
        
    def log(self, message: str, level: str = "INFO"):
        """Log message to console and file"""
        pkt_time = self._get_pkt_time()
        timestamp = pkt_time.strftime("%H:%M:%S")
        
        # Console output
        color_map = {
            "INFO": "white",
            "SUCCESS": "green",
            "WARNING": "yellow",
            "ERROR": "red",
            "DEBUG": "blue"
        }
        color = color_map.get(level, "white")
        console.print(f"[{timestamp}] [{level}] {message}", style=color)
        
        # File output
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
# BROWSER MANAGER
# ============================================================================

class BrowserManager:
    """Manages browser setup and authentication"""
    
    def __init__(self, logger: Logger):
        self.logger = logger
        self.driver = None
        
    def setup(self) -> Optional[webdriver.Chrome]:
        """Setup headless Chrome browser"""
        try:
            opts = Options()
            opts.add_argument("--headless=new")
            opts.add_argument("--window-size=1920,1080")
            opts.add_argument("--disable-blink-features=AutomationControlled")
            opts.add_experimental_option('excludeSwitches', ['enable-automation'])
            opts.add_argument("--no-sandbox")
            opts.add_argument("--disable-dev-shm-usage")
            opts.page_load_strategy = "eager"
            
            if Config.CHROMEDRIVER_PATH and os.path.exists(Config.CHROMEDRIVER_PATH):
                self.driver = webdriver.Chrome(service=Service(Config.CHROMEDRIVER_PATH), options=opts)
            else:
                self.driver = webdriver.Chrome(options=opts)
                
            self.driver.set_page_load_timeout(45)
            self.driver.execute_script("Object.defineProperty(navigator,'webdriver',{get:()=>undefined})")
            self.logger.success("Browser setup complete")
            return self.driver
        except Exception as e:
            self.logger.error(f"Browser setup failed: {e}")
            return None
    
    def login(self) -> bool:
        """Login to DamaDam"""
        if not self.driver:
            return False
            
        try:
            # Try cookies first
            if self._load_cookies():
                self.driver.get(BASE_URL)
                time.sleep(2)
                if 'login' not in self.driver.current_url.lower():
                    self.logger.success("Logged in via cookies")
                    return True
            
            # Fresh login
            self.driver.get(f"{BASE_URL}/login/")
            time.sleep(3)
            
            nick = WebDriverWait(self.driver, 8).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "#nick, input[name='nick']"))
            )
            pw = self.driver.find_element(By.CSS_SELECTOR, "#pass, input[name='pass']")
            btn = self.driver.find_element(By.CSS_SELECTOR, "button[type='submit']")
            
            nick.clear()
            nick.send_keys(Config.LOGIN_EMAIL)
            time.sleep(0.5)
            pw.clear()
            pw.send_keys(Config.LOGIN_PASS)
            time.sleep(0.5)
            btn.click()
            time.sleep(4)
            
            if 'login' not in self.driver.current_url.lower():
                self._save_cookies()
                self.logger.success("Login successful")
                return True
            
            self.logger.error("Login failed")
            return False
            
        except Exception as e:
            self.logger.error(f"Login error: {e}")
            return False
    
    def _save_cookies(self):
        """Save cookies to file"""
        try:
            with open(Config.COOKIE_FILE, 'wb') as f:
                pickle.dump(self.driver.get_cookies(), f)
        except Exception as e:
            self.logger.warning(f"Cookie save failed: {e}")
    
    def _load_cookies(self) -> bool:
        """Load cookies from file"""
        try:
            if not os.path.exists(Config.COOKIE_FILE):
                return False
            
            self.driver.get(BASE_URL)
            time.sleep(2)
            
            with open(Config.COOKIE_FILE, 'rb') as f:
                cookies = pickle.load(f)
            
            for c in cookies:
                try:
                    self.driver.add_cookie(c)
                except:
                    pass
            
            self.driver.refresh()
            time.sleep(2)
            return True
        except:
            return False
    
    def close(self):
        """Close browser"""
        if self.driver:
            self.driver.quit()
            self.logger.info("Browser closed")

# ============================================================================
# GOOGLE SHEETS MANAGER
# ============================================================================

class SheetsManager:
    """Manages Google Sheets operations"""
    
    def __init__(self, logger: Logger):
        self.logger = logger
        self.client = None
        self.api_calls = 0
        
    def connect(self) -> bool:
        """Connect to Google Sheets"""
        try:
            if not os.path.exists(Config.CREDENTIALS_FILE):
                self.logger.error(f"{Config.CREDENTIALS_FILE} not found")
                return False
            
            scope = ["https://www.googleapis.com/auth/spreadsheets"]
            creds = Credentials.from_service_account_file(Config.CREDENTIALS_FILE, scopes=scope)
            self.client = gspread.authorize(creds)
            self.logger.success("Connected to Google Sheets")
            return True
        except Exception as e:
            self.logger.error(f"Sheets connection failed: {e}")
            return False
    
    def get_sheet(self, sheet_id: str, sheet_name: str):
        """Get or create worksheet"""
        try:
            workbook = self.client.open_by_key(sheet_id)
            try:
                return workbook.worksheet(sheet_name)
            except WorksheetNotFound:
                self.logger.warning(f"Sheet '{sheet_name}' not found, creating...")
                return self._create_sheet(workbook, sheet_name)
        except Exception as e:
            self.logger.error(f"Failed to get sheet '{sheet_name}': {e}")
            return None
    
    def _create_sheet(self, workbook, sheet_name: str):
        """Create new worksheet with headers"""
        headers_map = {
            "MsgList": ["MODE", "NAME", "NICK/URL", "CITY", "POSTS", "FOLLOWERS", 
                       "MESSAGE", "STATUS", "NOTES", "RESULT URL"],
            "PostQueue": ["TYPE", "TITLE", "CONTENT", "IMAGE_PATH", "TAGS", 
                         "STATUS", "POST_URL", "TIMESTAMP", "NOTES"],
            "InboxQueue": ["NICK", "NAME", "LAST_MSG", "MY_REPLY", "STATUS", 
                          "TIMESTAMP", "NOTES", "CONVERSATION_LOG"],
            "MsgHistory": ["TIMESTAMP", "NICK", "NAME", "MESSAGE", "POST_URL", 
                          "STATUS", "RESULT_URL"],
        }
        
        headers = headers_map.get(sheet_name, ["DATA"])
        sheet = workbook.add_worksheet(title=sheet_name, rows=1000, cols=len(headers))
        sheet.insert_row(headers, 1)
        self.logger.success(f"Created sheet '{sheet_name}'")
        return sheet
    
    def update_cell(self, sheet, row: int, col: int, value, retries: int = 3):
        """Update cell with retry logic"""
        for attempt in range(retries):
            try:
                self.api_calls += 1
                sheet.update_cell(row, col, value)
                return True
            except Exception as e:
                if attempt == retries - 1:
                    self.logger.error(f"Cell update failed: {e}")
                    return False
                time.sleep(2 ** attempt)
        return False
    
    def append_row(self, sheet, values: List, retries: int = 3):
        """Append row with retry logic"""
        for attempt in range(retries):
            try:
                self.api_calls += 1
                sheet.append_row(values)
                return True
            except Exception as e:
                if attempt == retries - 1:
                    self.logger.error(f"Row append failed: {e}")
                    return False
                time.sleep(2 ** attempt)
        return False

# ============================================================================
# MESSAGE RECORDER
# ============================================================================

class MessageRecorder:
    """Records message history by nickname"""
    
    def __init__(self, sheets_manager: SheetsManager, logger: Logger):
        self.sheets = sheets_manager
        self.logger = logger
        self.history_sheet = None
        
    def initialize(self) -> bool:
        """Initialize MsgHistory sheet"""
        self.history_sheet = self.sheets.get_sheet(Config.SHEET_ID, "MsgHistory")
        return self.history_sheet is not None
    
    def record_message(self, nick: str, name: str, message: str, 
                      post_url: str, status: str, result_url: str = ""):
        """Record a message in history"""
        if not self.history_sheet:
            return
        
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        values = [timestamp, nick, name, message, post_url, status, result_url]
        
        self.sheets.append_row(self.history_sheet, values)
        self.logger.debug(f"Recorded message for {nick}")
    
    def get_history(self, nick: str) -> List[Dict]:
        """Get message history for a nickname"""
        if not self.history_sheet:
            return []
        
        try:
            self.sheets.api_calls += 1
            all_rows = self.history_sheet.get_all_values()
            history = []
            
            for row in all_rows[1:]:  # Skip header
                if len(row) >= 7 and row[1].lower() == nick.lower():
                    history.append({
                        "timestamp": row[0],
                        "nick": row[1],
                        "name": row[2],
                        "message": row[3],
                        "post_url": row[4],
                        "status": row[5],
                        "result_url": row[6]
                    })
            
            return history
        except Exception as e:
            self.logger.error(f"Failed to get history for {nick}: {e}")
            return []

# ============================================================================
# PROFILE SCRAPER
# ============================================================================

class ProfileScraper:
    """Handles profile scraping and data extraction"""
    
    def __init__(self, driver: webdriver.Chrome, logger: Logger):
        self.driver = driver
        self.logger = logger
    
    def scrape_profile(self, nickname: str) -> Optional[Dict]:
        """Scrape user profile data"""
        url = f"{BASE_URL}/users/{nickname}/"
        try:
            self.logger.info(f"Scraping profile: {nickname}")
            self.driver.get(url)
            WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "h1.cxl"))
            )
            
            data = {
                "NICK": nickname,
                "NAME": nickname,
                "CITY": "",
                "GENDER": "",
                "POSTS": "0",
                "FOLLOWERS": "0",
                "STATUS": "Unknown",
                "PROFILE_URL": url
            }
            
            # Check status
            page_source = self.driver.page_source.lower()
            if 'account suspended' in page_source:
                data['STATUS'] = "Suspended"
                return data
            elif 'background:tomato' in page_source:
                data['STATUS'] = "Unverified"
            else:
                data['STATUS'] = "Verified"
            
            # Extract fields
            fields = {
                'City:': 'CITY',
                'Gender:': 'GENDER',
                'Posts': 'POSTS',
                'Followers': 'FOLLOWERS'
            }
            
            for label, key in fields.items():
                try:
                    if key in ['POSTS', 'FOLLOWERS']:
                        elem = self.driver.find_element(By.XPATH, f"//*[contains(text(), '{label}')]")
                        match = re.search(r'(\d+)', elem.text)
                        if match:
                            data[key] = match.group(1)
                    else:
                        elem = self.driver.find_element(
                            By.XPATH, 
                            f"//b[contains(text(), '{label}')]/following-sibling::span[1]"
                        )
                        data[key] = elem.text.strip()
                except:
                    continue
            
            self.logger.success(f"Profile scraped: {data['GENDER']}, {data['CITY']}, Posts: {data['POSTS']}")
            return data
            
        except Exception as e:
            self.logger.error(f"Profile scrape failed for {nickname}: {e}")
            return None
    
    def find_open_post(self, nickname: str, post_type: str = "any") -> Optional[str]:
        """
        Find first open post (text or image)
        post_type: 'text', 'image', or 'any'
        """
        url = f"{BASE_URL}/profile/public/{nickname}/"
        try:
            self.logger.info(f"Finding open post for: {nickname}")
            
            for page in range(1, Config.MAX_POST_PAGES + 1):
                self.driver.get(url)
                time.sleep(3)
                
                posts = self.driver.find_elements(By.CSS_SELECTOR, "article.mbl")
                self.logger.debug(f"Page {page}: Found {len(posts)} posts")
                
                for idx, post in enumerate(posts, 1):
                    try:
                        # Look for comment links (both text and image)
                        selectors = []
                        if post_type in ['text', 'any']:
                            selectors.append("a[href*='/comments/text/']")
                        if post_type in ['image', 'any']:
                            selectors.append("a[href*='/comments/image/']")
                        
                        href = ""
                        found_type = ""
                        for sel in selectors:
                            try:
                                a = post.find_element(By.CSS_SELECTOR, sel)
                                href = a.get_attribute("href") or ""
                                if href:
                                    found_type = "text" if "/comments/text/" in href else "image"
                                    break
                            except:
                                continue
                        
                        if not href:
                            # Try reply button
                            try:
                                reply_btn = post.find_element(
                                    By.XPATH, 
                                    ".//a[button[@itemprop='discussionUrl']]"
                                )
                                href = reply_btn.get_attribute("href") or ""
                            except:
                                continue
                        
                        if href:
                            clean_href = self._clean_url(href)
                            self.logger.success(f"Found open {found_type} post: {clean_href}")
                            return clean_href
                            
                    except:
                        continue
                
                # Try next page
                try:
                    next_link = self.driver.find_element(By.CSS_SELECTOR, "a[rel='next']")
                    url = next_link.get_attribute("href") or ""
                    if not url:
                        break
                except:
                    break
            
            self.logger.warning(f"No open posts found for {nickname}")
            return None
            
        except Exception as e:
            self.logger.error(f"Error finding posts: {e}")
            return None
    
    @staticmethod
    def _clean_url(url: str) -> str:
        """Clean and normalize URLs"""
        if not url:
            return ""
        
        url = str(url).strip()
        
        # Extract clean post URLs
        text_match = re.search(r"/comments/text/(\d+)"

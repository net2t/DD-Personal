"""
DamaDam Bot V2.0.0 - Single File Complete Version
Clean, Organized, Multi-Mode Bot

Usage:
    python main.py --mode msg --max-profiles 10
    python main.py --mode post
    python main.py --mode inbox

Modes:
    msg   - Send personal messages (Phase 1)
    post  - Create new posts (Phase 2)
    inbox - Monitor inbox & reply (Phase 3)
"""

import time
import os
import sys
import re
import pickle
import argparse
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional
from urllib.parse import quote

import gspread
from dotenv import load_dotenv
from google.oauth2.service_account import Credentials
from gspread.exceptions import WorksheetNotFound
from gspread.utils import rowcol_to_a1

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException

from rich.console import Console

load_dotenv()

console = Console()
VERSION = "2.0.0"

# ============================================================================
# CONFIGURATION
# ============================================================================

class Config:
    """Centralized bot configuration"""

    # Authentication
    LOGIN_EMAIL = os.getenv("DD_LOGIN_EMAIL", "0utLawZ")
    LOGIN_PASS = os.getenv("DD_LOGIN_PASS", "asdasd")
    COOKIE_FILE = os.getenv("COOKIE_FILE", "damadam_cookies.pkl")

    # Google Sheets
    SHEET_ID = os.getenv("DD_SHEET_ID", "1xph0dra5-wPcgMXKubQD7A2CokObpst7o2rWbDA10t8")
    PROFILES_SHEET_ID = os.getenv("DD_PROFILES_SHEET_ID", "")
    CREDENTIALS_FILE = os.getenv("CREDENTIALS_FILE", "credentials.json")

    # Browser
    CHROMEDRIVER_PATH = os.getenv("CHROMEDRIVER_PATH", "chromedriver.exe")

    # Bot Settings
    DEBUG = os.getenv("DD_DEBUG", "0") == "1"
    MAX_PROFILES = int(os.getenv("DD_MAX_PROFILES", "0"))
    MAX_POST_PAGES = int(os.getenv("DD_MAX_POST_PAGES", "4"))

    # URLs
    BASE_URL = "https://damadam.pk"
    LOGIN_URL = f"{BASE_URL}/login/"
    HOME_URL = BASE_URL

    # Logging
    LOG_DIR = Path("logs")
    LOG_DIR.mkdir(exist_ok=True)

# ============================================================================
# LOGGER
# ============================================================================

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
            f.write("=" * 70 + "\n\n")

    def _log(self, message: str, level: str = "INFO"):
        """Internal log method"""
        pkt_time = self._get_pkt_time()
        timestamp = pkt_time.strftime("%H:%M:%S")
        safe_message = self._sanitize_message(message)

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
            console.print(f"[{timestamp}] {safe_message}")
        else:
            console.print(f"[{timestamp}] [{level}] {safe_message}", style=color)

        # File output
        with open(self.log_file, "a", encoding="utf-8") as f:
            f.write(f"[{timestamp}] [{level}] {safe_message}\n")

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

    @staticmethod
    def _sanitize_message(message: str) -> str:
        """Strip non-ASCII characters for Windows console compatibility."""
        if not isinstance(message, str):
            message = str(message)
        return message.encode("ascii", "ignore").decode("ascii")

# ============================================================================
# BROWSER MANAGER
# ============================================================================

class BrowserManager:
    """Manages browser setup and authentication"""

    def __init__(self, logger: Logger):
        self.logger = logger
        self.driver = None

    def setup(self):
        """Setup headless Chrome browser"""
        try:
            opts = Options()
            opts.add_argument("--headless=new")
            opts.add_argument("--window-size=1920,1080")
            opts.add_argument("--disable-blink-features=AutomationControlled")
            opts.add_experimental_option("excludeSwitches", ["enable-automation"])
            opts.add_experimental_option("useAutomationExtension", False)
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
                if "login" not in current_url and "signup" not in current_url:
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
            if "login" not in self.driver.current_url.lower():
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
            with open(Config.COOKIE_FILE, "wb") as f:
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

            with open(Config.COOKIE_FILE, "rb") as f:
                cookies = pickle.load(f)

            for cookie in cookies:
                try:
                    self.driver.add_cookie(cookie)
                except Exception:
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
            except Exception:
                pass

# ============================================================================
# SHEETS MANAGER
# ============================================================================

class SheetsManager:
    """Manages Google Sheets operations with retry logic"""

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
            creds = Credentials.from_service_account_file(
                Config.CREDENTIALS_FILE,
                scopes=scope
            )
            self.client = gspread.authorize(creds)
            self.logger.debug("Connected to Google Sheets API")
            return True

        except Exception as e:
            self.logger.error(f"Sheets connection failed: {e}")
            return False

    def get_sheet(self, sheet_id: str, sheet_name: str):
        """Get or create worksheet"""
        try:
            workbook = self.client.open_by_key(sheet_id)

            # Try to get existing sheet
            try:
                sheet = workbook.worksheet(sheet_name)
                self.logger.debug(f"Found sheet: {sheet_name}")
                return sheet
            except WorksheetNotFound:
                # Create new sheet
                self.logger.warning(f"Sheet '{sheet_name}' not found, creating...")
                return self._create_sheet(workbook, sheet_name)

        except Exception as e:
            self.logger.error(f"Failed to get sheet '{sheet_name}': {e}")
            return None

    def _create_sheet(self, workbook, sheet_name: str):
        """Create new worksheet with appropriate headers"""

        # Define headers for each sheet type
        headers_map = {
            "MsgList": [
                "MODE", "NAME", "NICK/URL", "CITY", "POSTS", "FOLLOWERS",
                "MESSAGE", "STATUS", "NOTES", "RESULT URL"
            ],
            "PostQueue": [
                "TYPE", "TITLE", "CONTENT", "IMAGE_PATH", "TAGS",
                "STATUS", "POST_URL", "TIMESTAMP", "NOTES"
            ],
            "InboxQueue": [
                "NICK", "NAME", "LAST_MSG", "MY_REPLY", "STATUS",
                "TIMESTAMP", "NOTES", "CONVERSATION_LOG"
            ],
            "MsgHistory": [
                "TIMESTAMP", "NICK", "NAME", "MESSAGE", "POST_URL",
                "STATUS", "RESULT_URL"
            ],
        }

        headers = headers_map.get(sheet_name, ["DATA"])

        try:
            sheet = workbook.add_worksheet(
                title=sheet_name,
                rows=1000,
                cols=len(headers)
            )
            sheet.insert_row(headers, 1)
            self._format_headers(sheet, len(headers))
            self.logger.success(f"Created sheet: {sheet_name}")
            return sheet
        except Exception as e:
            self.logger.error(f"Failed to create sheet '{sheet_name}': {e}")
            return None

    def _format_headers(self, sheet, col_count: int):
        """Freeze header row and apply basic formatting."""
        try:
            sheet.freeze(rows=1)
            header_range = f"A1:{rowcol_to_a1(1, col_count)}"
            sheet.format(
                header_range,
                {
                    "textFormat": {"bold": True},
                    "horizontalAlignment": "CENTER",
                    "backgroundColor": {"red": 0.91, "green": 0.94, "blue": 0.98}
                }
            )
        except Exception as e:
            self.logger.debug(f"Header formatting failed: {e}")

    def update_cell(self, sheet, row: int, col: int, value, retries: int = 3):
        """Update cell with retry logic"""
        for attempt in range(retries):
            try:
                self.api_calls += 1
                sheet.update_cell(row, col, value)
                return True
            except Exception as e:
                if attempt == retries - 1:
                    self.logger.error(f"Cell update failed ({row},{col}): {e}")
                    return False
                self.logger.debug(f"Retry {attempt+1}/{retries} for cell ({row},{col})")
                time.sleep(2 ** attempt)
        return False

    def append_row(self, sheet, values: list, retries: int = 3):
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
                self.logger.debug(f"Retry {attempt+1}/{retries} for append")
                time.sleep(2 ** attempt)
        return False

# ============================================================================
# PROFILE SCRAPER
# ============================================================================

class ProfileScraper:
    """Handles profile scraping and post finding"""

    def __init__(self, driver, logger: Logger):
        self.driver = driver
        self.logger = logger

    def scrape_profile(self, nickname: str) -> Optional[Dict]:
        """Scrape user profile data"""
        safe_nick = quote(str(nickname).strip(), safe="+")
        url = f"{Config.BASE_URL}/users/{safe_nick}/"

        try:
            self.logger.debug(f"Scraping: {nickname}")
            self.driver.get(url)
            WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "h1.cxl, h1"))
            )

            # Initialize profile data
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

            page_source = self.driver.page_source.lower()

            # Check account status
            if "account suspended" in page_source:
                data["STATUS"] = "Suspended"
                self.logger.warning(f"Account suspended: {nickname}")
                return data
            elif "background:tomato" in page_source or "style=\"background:tomato\"" in page_source:
                data["STATUS"] = "Unverified"
            else:
                data["STATUS"] = "Verified"

            # Extract profile fields
            fields_map = {
                "City:": "CITY",
                "Gender:": "GENDER",
            }

            for label, key in fields_map.items():
                try:
                    elem = self.driver.find_element(
                        By.XPATH,
                        f"//b[contains(text(), '{label}')]/following-sibling::span[1]"
                    )
                    value = elem.text.strip()

                    if key == "GENDER":
                        low = value.lower()
                        data[key] = "🚺" if low == "female" else "🚹" if low == "male" else value
                    else:
                        data[key] = value
                except Exception:
                    continue

            # Extract posts count
            try:
                posts_elem = self.driver.find_element(
                    By.CSS_SELECTOR,
                    "a[href*='/profile/public/'] button div:first-child"
                )
                match = re.search(r"(\d+)", posts_elem.text)
                if match:
                    data["POSTS"] = match.group(1)
            except Exception:
                pass

            # Extract followers count
            try:
                followers_elem = self.driver.find_element(
                    By.CSS_SELECTOR,
                    "span.cl.sp.clb"
                )
                match = re.search(r"(\d+)", followers_elem.text)
                if match:
                    data["FOLLOWERS"] = match.group(1)
            except Exception:
                pass

            self.logger.debug(
                f"Profile: {data['GENDER']}, {data['CITY']}, "
                f"Posts: {data['POSTS']}, Status: {data['STATUS']}"
            )

            return data

        except TimeoutException:
            self.logger.error(f"Timeout scraping {nickname}")
            return None
        except Exception as e:
            self.logger.error(f"Scrape error for {nickname}: {e}")
            return None

    def find_open_post(self, nickname: str, post_type: str = "any") -> Optional[str]:
        """
        Find first open post (text or image)

        Args:
            nickname: User nickname
            post_type: 'text', 'image', or 'any'

        Returns:
            Post URL or None
        """
        safe_nick = quote(str(nickname).strip(), safe="+")
        url = f"{Config.BASE_URL}/profile/public/{safe_nick}/"

        try:
            self.logger.debug(f"Finding open post for: {nickname}")

            max_pages = Config.MAX_POST_PAGES if Config.MAX_POST_PAGES > 0 else 4

            for page_num in range(1, max_pages + 1):
                self.driver.get(url)
                time.sleep(3)

                # Scroll to load dynamic content
                self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(1)

                # Find all posts on page
                posts = self.driver.find_elements(
                    By.CSS_SELECTOR,
                    "article.mbl, article, div[class*='post'], div[class*='content']"
                )
                self.logger.debug(f"Page {page_num}: Found {len(posts)} posts")

                next_href = ""
                try:
                    next_link = self.driver.find_element(By.CSS_SELECTOR, "a[rel='next']")
                    next_href = next_link.get_attribute("href") or ""
                except Exception:
                    next_href = ""

                for idx, post in enumerate(posts, 1):
                    try:
                        # Look for comment links (both text and image)
                        selectors = []

                        if post_type in ["text", "any"]:
                            selectors.append("a[href*='/comments/text/']")
                        if post_type in ["image", "any"]:
                            selectors.append("a[href*='/comments/image/']")

                        href = ""
                        found_type = ""

                        for sel in selectors:
                            try:
                                link = post.find_element(By.CSS_SELECTOR, sel)
                                href = link.get_attribute("href") or ""
                                if href:
                                    found_type = "text" if "/comments/text/" in href else "image"
                                    break
                            except Exception:
                                continue

                        # Fallback: try reply button
                        if not href:
                            try:
                                reply_btn = post.find_element(
                                    By.XPATH,
                                    ".//a[button[@itemprop='discussionUrl']]"
                                )
                                href = reply_btn.get_attribute("href") or ""
                            except Exception:
                                continue

                        if href:
                            clean_href = self.clean_url(href)
                            self.logger.debug(f"Found {found_type} post #{idx}: {clean_href}")
                            return clean_href

                    except Exception as e:
                        self.logger.debug(f"Post #{idx} check failed: {e}")
                        continue

                # Fallback: search for comment/content links globally
                fallback_selectors = []
                if post_type in ["text", "any"]:
                    fallback_selectors.append("a[href*='/comments/text/']")
                if post_type in ["image", "any"]:
                    fallback_selectors.append("a[href*='/comments/image/']")
                fallback_selectors.append("a[href*='/content/']")

                for sel in fallback_selectors:
                    try:
                        links = self.driver.find_elements(By.CSS_SELECTOR, sel)
                        for link in links:
                            href = link.get_attribute("href") or ""
                            if href:
                                clean_href = self.clean_url(href)
                                self.logger.debug(f"Fallback found post: {clean_href}")
                                return clean_href
                    except Exception:
                        continue

                # JS fallback to collect all matching hrefs
                try:
                    hrefs = self.driver.execute_script(
                        "return Array.from(document.querySelectorAll(\"a[href*='/comments/'], a[href*='/content/']\"))"
                        ".map(a => a.href).filter(Boolean);"
                    )
                    for href in hrefs:
                        clean_href = self.clean_url(href)
                        if clean_href:
                            self.logger.debug(f"JS fallback found post: {clean_href}")
                            return clean_href
                except Exception:
                    pass

                # ID fallback: some profiles don't expose /comments/ links on profile page
                candidate_ids: List[str] = []
                try:
                    for post in posts[:30]:
                        outer = self.driver.execute_script("return arguments[0].outerHTML", post)
                        nums = re.findall(r"\b\d{7,10}\b", outer)
                        for n in nums:
                            try:
                                iv = int(n)
                            except Exception:
                                continue
                            if iv >= 1_000_000_000:
                                continue
                            if iv < 1_000_000:
                                continue

                            # Heuristic: prefer likely post IDs (usually 8-9 digits) over user IDs (often 7 digits)
                            if len(n) < 8:
                                continue
                            if n not in candidate_ids:
                                candidate_ids.append(n)
                except Exception:
                    candidate_ids = []

                if candidate_ids:
                    kinds: List[str]
                    if post_type == "text":
                        kinds = ["text"]
                    elif post_type == "image":
                        kinds = ["image"]
                    else:
                        kinds = ["text", "image"]

                    for pid in candidate_ids[:20]:
                        for kind in kinds:
                            try:
                                cand_url = f"{Config.BASE_URL}/comments/{kind}/{pid}"
                                self.driver.get(cand_url)
                                time.sleep(2)
                                src = self.driver.page_source.lower()
                                if "404" in src or "page not found" in src:
                                    continue

                                forms = self.driver.find_elements(
                                    By.CSS_SELECTOR,
                                    "form[action*='direct-response/send']"
                                )
                                if forms:
                                    # Don't rely on is_displayed() in headless; just validate the textarea exists.
                                    for f in forms:
                                        try:
                                            f.find_element(By.CSS_SELECTOR, "textarea[name='direct_response']")
                                            self.logger.debug(f"ID fallback found {kind} post: {cand_url}")
                                            return self.clean_url(self.driver.current_url)
                                        except Exception:
                                            continue

                            except Exception:
                                continue

                # Try next page
                if not next_href:
                    break
                url = next_href

            self.logger.warning(f"No open posts found for {nickname}")
            return None

        except Exception as e:
            self.logger.error(f"Error finding posts: {e}")
            return None

    @staticmethod
    def clean_url(url: str) -> str:
        """Clean and normalize post URLs"""
        if not url:
            return ""

        url = str(url).strip()

        # Extract clean post ID
        text_match = re.search(r"/comments/text/(\d+)", url)
        if text_match:
            return f"{Config.BASE_URL}/comments/text/{text_match.group(1)}"

        image_match = re.search(r"/comments/image/(\d+)", url)
        if image_match:
            return f"{Config.BASE_URL}/comments/image/{image_match.group(1)}"

        # Remove reply fragments
        url = re.sub(r"/\d+/#reply$", "", url)
        url = re.sub(r"/#reply$", "", url)
        url = url.rstrip("/")

        return url

    @staticmethod
    def is_valid_url(url: str) -> bool:
        """Check if URL is valid DamaDam post URL"""
        if not url:
            return False
        return (
            "damadam.pk" in url
            and ("/comments/text/" in url or "/comments/image/" in url or "/content/" in url)
        )

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
        if self.history_sheet:
            self.logger.debug("Message history tracking enabled")
            return True
        return False

    def record_message(self, nick: str, name: str, message: str,
                       post_url: str, status: str, result_url: str = ""):
        """Record a sent message"""
        if not self.history_sheet:
            return

        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        values = [timestamp, nick, name, message, post_url, status, result_url]

        self.sheets.append_row(self.history_sheet, values)
        self.logger.debug(f"Recorded message history for: {nick}")

# ============================================================================
# MESSAGE SENDER
# ============================================================================

class MessageSender:
    """Handles sending messages to posts"""

    def __init__(self, driver, logger: Logger, scraper: ProfileScraper, recorder: MessageRecorder):
        self.driver = driver
        self.logger = logger
        self.scraper = scraper
        self.recorder = recorder

    def send_message(self, post_url: str, message: str, nick: str = "") -> Dict:
        """Send message to a post and verify"""
        try:
            self.logger.debug(f"Opening post: {post_url}")
            self.driver.get(post_url)
            time.sleep(3)

            page_source = self.driver.page_source

            # Check for blocks
            if "FOLLOW TO REPLY" in page_source.upper():
                self.logger.warning("Must follow user first")
                return {"status": "Not Following", "url": post_url}

            if "comments are closed" in page_source.lower() or "comments closed" in page_source.lower():
                self.logger.warning("Comments closed")
                return {"status": "Comments Closed", "url": post_url}

            # Find visible comment form
            forms = self.driver.find_elements(
                By.CSS_SELECTOR,
                "form[action*='direct-response/send']"
            )

            form = None
            for f in forms:
                if f.is_displayed():
                    try:
                        f.find_element(By.CSS_SELECTOR, "textarea[name='direct_response']")
                        form = f
                        break
                    except Exception:
                        continue

            if not form:
                self.logger.warning("No visible comment form found")
                return {"status": "No Form", "url": post_url}

            # Find textarea and submit button
            textarea = form.find_element(
                By.CSS_SELECTOR,
                "textarea[name='direct_response']"
            )
            send_btn = form.find_element(
                By.CSS_SELECTOR,
                "button[type='submit']"
            )

            # Limit message to 350 chars
            if len(message) > 350:
                message = message[:350]
                self.logger.debug("Message truncated to 350 chars")

            # Type message
            textarea.clear()
            time.sleep(0.5)
            textarea.send_keys(message)
            self.logger.debug(f"Message entered: {len(message)} chars")
            time.sleep(1)

            # Submit
            self.logger.debug("Submitting message...")
            self.driver.execute_script("arguments[0].click();", send_btn)
            time.sleep(3)

            # Verify by refreshing and checking
            self.logger.debug("Verifying message...")
            self.driver.get(post_url)
            time.sleep(2)

            fresh_page = self.driver.page_source

            # Check multiple verification methods
            verifications = {
                "username": Config.LOGIN_EMAIL in fresh_page,
                "message": message in fresh_page,
                "recent": any(x in fresh_page.lower() for x in ["sec ago", "secs ago", "just now"])
            }

            if Config.DEBUG:
                for check, result in verifications.items():
                    self.logger.debug(f"Verify {check}: {'✓' if result else '✗'}")

            if verifications["username"] and verifications["message"]:
                self.logger.success("Message verified!")

                # Record to history
                if nick:
                    self.recorder.record_message(
                        nick=nick,
                        name=nick,
                        message=message,
                        post_url=post_url,
                        status="Posted",
                        result_url=post_url
                    )

                return {"status": "Posted", "url": post_url}
            else:
                self.logger.warning("Message sent but not verified")
                return {"status": "Pending Verification", "url": post_url}

        except NoSuchElementException as e:
            self.logger.error(f"Form element not found: {e}")
            return {"status": "Form Error", "url": post_url}
        except Exception as e:
            self.logger.error(f"Send error: {e}")
            return {"status": f"Error: {str(e)[:50]}", "url": post_url}

    def process_template(self, template: str, profile: Dict) -> str:
        """Process message template with profile data"""
        message = template

        replacements = {
            "{{name}}": profile.get("NAME", "Unknown"),
            "{{nick}}": profile.get("NICK", "Unknown"),
            "{{city}}": profile.get("CITY", "Unknown"),
            "{{posts}}": str(profile.get("POSTS", "0")),
            "{{followers}}": str(profile.get("FOLLOWERS", "0")),
        }

        for placeholder, value in replacements.items():
            message = message.replace(placeholder, value)

        return message

# ============================================================================
# POST CREATOR
# ============================================================================

class PostCreator:
    """Handles creating new posts (text/image)"""

    def __init__(self, driver, logger: Logger):
        self.driver = driver
        self.logger = logger

    def create_text_post(self, title: str, content: str, tags: str = "") -> Dict:
        """Create a text post"""
        try:
            self.logger.info("Creating text post...")
            self.driver.get(f"{Config.BASE_URL}/share/text/")
            time.sleep(3)

            try:
                # Find form elements
                title_input = self.driver.find_element(
                    By.CSS_SELECTOR,
                    "input[name='title'], #id_title, input[name='heading']"
                )
                content_area = self.driver.find_element(
                    By.CSS_SELECTOR,
                    "textarea[name='text'], #id_text, textarea[name='content'], #id_content"
                )
                submit_btn = self.driver.find_element(
                    By.CSS_SELECTOR,
                    "button[type='submit'], input[type='submit'], button.btn-primary"
                )

                # Fill form
                self.logger.debug(f"Title: {title[:50]}...")
                title_input.clear()
                title_input.send_keys(title)
                time.sleep(0.5)

                self.logger.debug(f"Content: {len(content)} chars")
                content_area.clear()
                content_area.send_keys(content)
                time.sleep(0.5)

                # Tags if available
                if tags:
                    try:
                        tags_input = self.driver.find_element(
                            By.CSS_SELECTOR,
                            "input[name='tags'], #id_tags"
                        )
                        tags_input.clear()
                        tags_input.send_keys(tags)
                        self.logger.debug(f"Tags: {tags}")
                    except Exception:
                        self.logger.debug("Tags field not found")

                # Submit
                self.logger.info("Submitting text post...")
                submit_btn.click()
                time.sleep(4)

                # Get result URL
                post_url = self.driver.current_url

                if "damadam.pk" in post_url and "/comments/text/" in post_url:
                    self.logger.success(f"Text post created: {post_url}")
                    return {"status": "Posted", "url": post_url}
                else:
                    self.logger.warning("Post submitted but URL unclear")
                    return {"status": "Pending Verification", "url": post_url}

            except NoSuchElementException as e:
                self.logger.error(f"Form element not found: {e}")
                return {"status": "Form Error", "url": ""}

        except Exception as e:
            self.logger.error(f"Text post error: {e}")
            return {"status": f"Error: {str(e)[:50]}", "url": ""}

    def create_image_post(self, image_path: str, title: str = "", tags: str = "") -> Dict:
        """Create an image post from local file"""
        try:
            self.logger.info("Creating image post...")

            # Verify file exists
            if not os.path.exists(image_path):
                self.logger.error(f"Image not found: {image_path}")
                return {"status": "File Not Found", "url": ""}

            self.logger.debug(f"Image: {image_path}")
            self.driver.get(f"{Config.BASE_URL}/share/photo/upload/")
            time.sleep(3)

            try:
                # Find file input
                file_input = self.driver.find_element(
                    By.CSS_SELECTOR,
                    "input[type='file'], input[name='file'], input[name='image']"
                )

                # Upload file
                abs_path = os.path.abspath(image_path)
                file_input.send_keys(abs_path)
                self.logger.debug("Image uploaded")
                time.sleep(2)

                # Title if available
                if title:
                    try:
                        title_input = self.driver.find_element(
                            By.CSS_SELECTOR,
                            "input[name='title'], #id_title"
                        )
                        title_input.clear()
                        title_input.send_keys(title)
                        self.logger.debug(f"Title: {title}")
                    except Exception:
                        self.logger.debug("Title field not found")

                # Tags if available
                if tags:
                    try:
                        tags_input = self.driver.find_element(
                            By.CSS_SELECTOR,
                            "input[name='tags'], #id_tags"
                        )
                        tags_input.clear()
                        tags_input.send_keys(tags)
                        self.logger.debug(f"Tags: {tags}")
                    except Exception:
                        self.logger.debug("Tags field not found")

                # Submit
                submit_btn = self.driver.find_element(
                    By.CSS_SELECTOR,
                    "button[type='submit'], input[type='submit'], button.btn-primary"
                )
                self.logger.info("Submitting image post...")
                submit_btn.click()
                time.sleep(5)  # Images take longer to process

                # Get result URL
                post_url = self.driver.current_url

                if "damadam.pk" in post_url and ("/comments/image/" in post_url or "/content/" in post_url):
                    self.logger.success(f"Image post created: {post_url}")
                    return {"status": "Posted", "url": post_url}
                else:
                    self.logger.warning("Post submitted but URL unclear")
                    return {"status": "Pending Verification", "url": post_url}

            except NoSuchElementException as e:
                self.logger.error(f"Upload form element not found: {e}")
                return {"status": "Form Error", "url": ""}

        except Exception as e:
            self.logger.error(f"Image post error: {e}")
            return {"status": f"Error: {str(e)[:50]}", "url": ""}

# ============================================================================
# INBOX MONITOR
# ============================================================================

class InboxMonitor:
    """Monitors inbox and manages replies"""

    def __init__(self, driver, logger: Logger):
        self.driver = driver
        self.logger = logger

    def fetch_inbox(self) -> List[Dict]:
        """Fetch all inbox messages"""
        try:
            self.logger.info("Fetching inbox...")
            self.driver.get(f"{Config.BASE_URL}/inbox/")
            time.sleep(3)

            messages = []

            # Find conversation items
            conversations = self.driver.find_elements(
                By.CSS_SELECTOR,
                "article, .conversation-item, div[class*='inbox'], li"
            )

            if not conversations:
                self.logger.warning("No inbox items found (check page structure)")
                return []

            self.logger.debug(f"Found {len(conversations)} potential inbox items")

            for conv in conversations:
                try:
                    # Extract nickname
                    nick_elem = conv.find_element(
                        By.CSS_SELECTOR,
                        "a[href*='/users/'], b, strong"
                    )
                    nick = nick_elem.text.strip()
                    if not nick:
                        continue

                    # Extract last message preview
                    msg_elem = conv.find_element(
                        By.CSS_SELECTOR,
                        "span, .message-preview, bdi, p"
                    )
                    last_msg = msg_elem.text.strip()

                    # Extract timestamp
                    try:
                        time_elem = conv.find_element(
                            By.CSS_SELECTOR,
                            "time, span.time, .timestamp, small"
                        )
                        timestamp = time_elem.text.strip()
                    except Exception:
                        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

                    # Get conversation URL
                    link_elem = conv.find_element(
                        By.CSS_SELECTOR,
                        "a[href*='/inbox/'], a[href*='/users/']"
                    )
                    conv_url = link_elem.get_attribute("href")

                    messages.append({
                        "nick": nick,
                        "last_msg": last_msg,
                        "timestamp": timestamp,
                        "conv_url": conv_url
                    })

                    self.logger.debug(f"Inbox: {nick} - {last_msg[:30]}...")

                except Exception as e:
                    self.logger.debug(f"Skipped inbox item: {e}")
                    continue

            self.logger.success(f"Found {len(messages)} conversations")
            return messages

        except Exception as e:
            self.logger.error(f"Inbox fetch error: {e}")
            return []

    def send_reply(self, conv_url: str, reply_text: str) -> bool:
        """Send reply in a conversation"""
        try:
            self.logger.debug(f"Opening conversation: {conv_url}")
            self.driver.get(conv_url)
            time.sleep(3)

            # Find reply form
            textarea = self.driver.find_element(
                By.CSS_SELECTOR,
                "textarea[name='message'], textarea"
            )
            send_btn = self.driver.find_element(
                By.CSS_SELECTOR,
                "button[type='submit']"
            )

            # Type and send
            textarea.clear()
            textarea.send_keys(reply_text)
            self.logger.debug(f"Typed reply: {len(reply_text)} chars")
            time.sleep(0.5)

            send_btn.click()
            self.logger.info("Reply sent")
            time.sleep(3)

            # Verify
            self.driver.refresh()
            time.sleep(2)

            if reply_text in self.driver.page_source:
                self.logger.success("Reply verified")
                return True
            else:
                self.logger.warning("Reply sent but not verified")
                return True  # Assume success

        except Exception as e:
            self.logger.error(f"Reply error: {e}")
            return False

    def get_conversation_log(self, conv_url: str) -> str:
        """Get full conversation history as text"""
        try:
            self.driver.get(conv_url)
            time.sleep(2)

            # Find all messages
            messages = self.driver.find_elements(
                By.CSS_SELECTOR,
                ".message, article, div[class*='msg']"
            )

            log_lines = []
            for msg in messages:
                try:
                    sender = msg.find_element(
                        By.CSS_SELECTOR,
                        "b, .sender, strong"
                    ).text.strip()

                    text = msg.find_element(
                        By.CSS_SELECTOR,
                        "bdi, .text, span, p"
                    ).text.strip()

                    if sender and text:
                        log_lines.append(f"{sender}: {text}")
                except Exception:
                    continue

            return "\n".join(log_lines)

        except Exception as e:
            self.logger.error(f"Conversation log error: {e}")
            return ""

# ============================================================================
# PHASE 1: MESSAGE MODE
# ============================================================================

def run_message_mode(args):
    """Phase 1: Send personal messages to targets"""
    logger = Logger("msg")
    logger.info("=" * 70)
    logger.info(f"DamaDam Bot V{VERSION} - MESSAGE MODE")
    logger.info("=" * 70 + "\n")

    browser_mgr = BrowserManager(logger)
    driver = browser_mgr.setup()
    if not driver:
        logger.error("Browser setup failed")
        return

    try:
        # Login
        logger.info("🔐 Authenticating...")
        if not browser_mgr.login():
            logger.error("Login failed - check credentials")
            return
        logger.success("✅ Login successful\n")

        # Connect to Google Sheets
        logger.info("📊 Connecting to Google Sheets...")
        sheets_mgr = SheetsManager(logger)
        if not sheets_mgr.connect():
            logger.error("Sheets connection failed")
            return
        logger.success("✅ Sheets connected\n")

        # Initialize components
        scraper = ProfileScraper(driver, logger)
        recorder = MessageRecorder(sheets_mgr, logger)
        if not recorder.initialize():
            logger.warning("Message history tracking unavailable")
        sender = MessageSender(driver, logger, scraper, recorder)

        # Get MsgList sheet
        msglist = sheets_mgr.get_sheet(Config.SHEET_ID, "MsgList")
        if not msglist:
            logger.error("MsgList sheet not found")
            return

        # Load pending targets
        logger.info("📋 Loading pending targets...")
        sheets_mgr.api_calls += 1
        all_rows = msglist.get_all_values()

        pending = []
        for i, row in enumerate(all_rows[1:], start=2):
            if len(row) >= 8:
                mode = row[0].strip().lower()
                name = row[1].strip()
                nick_or_url = row[2].strip()
                city = row[3].strip() if len(row) > 3 else ""
                posts = row[4].strip() if len(row) > 4 else ""
                followers = row[5].strip() if len(row) > 5 else ""
                message = row[6].strip()
                status = row[7].strip().lower()
                notes = row[8].strip() if len(row) > 8 else ""

                if nick_or_url and message and status.startswith("pending"):
                    pending.append({
                        "row": i,
                        "mode": mode,
                        "name": name,
                        "nick_or_url": nick_or_url,
                        "city": city,
                        "posts": posts,
                        "followers": followers,
                        "message": message,
                        "notes": notes
                    })

        if not pending:
            logger.warning("⚠️ No pending targets found in MsgList")
            logger.info("Add targets with STATUS='pending' in MsgList sheet")
            return

        # Apply max limit
        if Config.MAX_PROFILES > 0:
            pending = pending[:Config.MAX_PROFILES]
            logger.info(f"📌 Limited to {Config.MAX_PROFILES} targets")

        logger.success(f"✅ Found {len(pending)} pending targets\n")
        logger.info("=" * 70 + "\n")

        # Process each target
        success_count = 0
        failed_count = 0

        for idx, target in enumerate(pending, 1):
            logger.info("\n" + "─" * 70)
            logger.info(f"[{idx}/{len(pending)}] 👤 Processing: {target['name']}")
            logger.info("─" * 70)

            try:
                mode = target["mode"]
                name = target["name"]
                nick_or_url = target["nick_or_url"]
                message = target["message"]
                row_num = target["row"]

                post_url = None
                profile = {
                    "NAME": name,
                    "NICK": nick_or_url,
                    "CITY": target.get("city", ""),
                    "POSTS": target.get("posts", "0"),
                    "FOLLOWERS": target.get("followers", "0")
                }

                # Handle MODE
                if mode == "url":
                    # Direct URL mode
                    post_url = ProfileScraper.clean_url(nick_or_url)
                    if not ProfileScraper.is_valid_url(post_url):
                        raise ValueError(f"Invalid URL: {nick_or_url}")
                    logger.info("🌐 Mode: Direct URL")
                    logger.info(f"   Target: {post_url}")

                else:
                    # Nick mode - scrape profile first
                    logger.info("👤 Mode: Nickname")
                    logger.info(f"   Target: {nick_or_url}")

                    profile = scraper.scrape_profile(nick_or_url)
                    if not profile:
                        logger.error("❌ Profile scrape failed")
                        sheets_mgr.update_cell(msglist, row_num, 8, "Failed")
                        sheets_mgr.update_cell(msglist, row_num, 9, "Profile scrape failed")
                        failed_count += 1
                        continue

                    # Check if suspended
                    if profile.get("STATUS") == "Suspended":
                        logger.warning("⚠️ Account suspended")
                        sheets_mgr.update_cell(msglist, row_num, 8, "Skipped")
                        sheets_mgr.update_cell(msglist, row_num, 9, "Account suspended")
                        failed_count += 1
                        continue

                    # Update sheet with profile data
                    if profile.get("CITY"):
                        sheets_mgr.update_cell(msglist, row_num, 4, profile["CITY"])
                    if profile.get("POSTS"):
                        sheets_mgr.update_cell(msglist, row_num, 5, profile["POSTS"])
                    if profile.get("FOLLOWERS"):
                        sheets_mgr.update_cell(msglist, row_num, 6, profile["FOLLOWERS"])

                    # Check post count
                    post_count = int(profile.get("POSTS", "0"))
                    if post_count == 0:
                        logger.warning("⚠️ No posts available")
                        sheets_mgr.update_cell(msglist, row_num, 8, "Skipped")
                        sheets_mgr.update_cell(msglist, row_num, 9, "No posts")
                        failed_count += 1
                        continue

                    # Find open post (text or image)
                    logger.info("🔍 Finding open post...")
                    post_url = scraper.find_open_post(nick_or_url, post_type="any")
                    if not post_url:
                        logger.error("❌ No open posts found")

                        max_pages = Config.MAX_POST_PAGES if Config.MAX_POST_PAGES > 0 else 4
                        sheets_mgr.update_cell(msglist, row_num, 8, "Failed")
                        sheets_mgr.update_cell(
                            msglist,
                            row_num,
                            9,
                            f"No open posts found (scanned up to {max_pages} pages)"
                        )

                        failed_count += 1
                        continue

                # Process message template
                processed_msg = sender.process_template(message, profile)
                logger.info(f"💬 Message: '{processed_msg}' ({len(processed_msg)} chars)")

                # Send message
                result = sender.send_message(post_url, processed_msg, nick_or_url)

                # Update sheet based on result
                timestamp = datetime.now().strftime("%I:%M %p")
                if "Posted" in result["status"]:
                    logger.success("✅ SUCCESS - Message posted!")
                    logger.info(f"🔗 URL: {result['url']}")
                    sheets_mgr.update_cell(msglist, row_num, 8, "Done")
                    sheets_mgr.update_cell(msglist, row_num, 9, f"Posted @ {timestamp}")
                    sheets_mgr.update_cell(msglist, row_num, 10, result["url"])
                    success_count += 1

                elif "Verification" in result["status"]:
                    logger.warning("⚠️ Needs manual verification")
                    logger.info(f"🔗 Check: {result['url']}")
                    sheets_mgr.update_cell(msglist, row_num, 8, "Done")
                    sheets_mgr.update_cell(msglist, row_num, 9, f"Verify @ {timestamp}")
                    sheets_mgr.update_cell(msglist, row_num, 10, result["url"])
                    success_count += 1

                else:
                    logger.error(f"❌ FAILED - {result['status']}")
                    sheets_mgr.update_cell(msglist, row_num, 8, "Failed")
                    sheets_mgr.update_cell(msglist, row_num, 9, result["status"])
                    if result.get("url"):
                        sheets_mgr.update_cell(msglist, row_num, 10, result["url"])
                    failed_count += 1

                # Rate limiting
                time.sleep(2)

            except Exception as e:
                error_msg = str(e)[:60]
                logger.error(f"❌ Error: {error_msg}")
                sheets_mgr.update_cell(msglist, target["row"], 8, "Failed")
                sheets_mgr.update_cell(msglist, target["row"], 9, error_msg)
                failed_count += 1

        # Summary
        logger.info("\n" + "=" * 70)
        logger.info("📊 MESSAGE MODE SUMMARY")
        logger.info("=" * 70)
        logger.success(f"✅ Success: {success_count}/{len(pending)}")
        logger.error(f"❌ Failed: {failed_count}/{len(pending)}")
        logger.info(f"📞 API Calls: {sheets_mgr.api_calls}")
        logger.info(f"📝 Log: {logger.log_file}")
        logger.info("=" * 70 + "\n")

    except KeyboardInterrupt:
        logger.warning("\n⚠️ Interrupted by user")
    except Exception as e:
        logger.error(f"Fatal error: {e}")
    finally:
        browser_mgr.close()

# ============================================================================
# PHASE 2: POST MODE
# ============================================================================

def run_post_mode(args):
    """Phase 2: Create new posts (text/image)"""
    logger = Logger("post")
    logger.info("=" * 70)
    logger.info(f"DamaDam Bot V{VERSION} - POST MODE")
    logger.info("=" * 70 + "\n")

    browser_mgr = BrowserManager(logger)
    driver = browser_mgr.setup()
    if not driver:
        return

    try:
        if not browser_mgr.login():
            return

        sheets_mgr = SheetsManager(logger)
        if not sheets_mgr.connect():
            return

        creator = PostCreator(driver, logger)
        post_queue = sheets_mgr.get_sheet(Config.SHEET_ID, "PostQueue")
        if not post_queue:
            return

        logger.info("📋 Loading pending posts...")
        sheets_mgr.api_calls += 1
        all_rows = post_queue.get_all_values()

        pending = []
        for i, row in enumerate(all_rows[1:], start=2):
            if len(row) >= 6:
                post_type = row[0].strip().lower()
                title = row[1].strip()
                content = row[2].strip()
                image_path = row[3].strip()
                tags = row[4].strip()
                status = row[5].strip().lower()

                if status.startswith("pending"):
                    pending.append({
                        "row": i,
                        "type": post_type,
                        "title": title,
                        "content": content,
                        "image_path": image_path,
                        "tags": tags
                    })

        if not pending:
            logger.warning("No pending posts in PostQueue")
            return

        if Config.MAX_PROFILES > 0:
            pending = pending[:Config.MAX_PROFILES]

        logger.success(f"Found {len(pending)} pending posts\n")

        success = 0
        failed = 0

        for idx, post in enumerate(pending, 1):
            logger.info(f"\n[{idx}/{len(pending)}] 📝 {post['type'].upper()}: {post['title'] or 'Untitled'}")
            logger.info("─" * 50)

            try:
                result = None

                if post["type"] == "text":
                    result = creator.create_text_post(
                        title=post["title"],
                        content=post["content"],
                        tags=post["tags"]
                    )
                elif post["type"] == "image":
                    result = creator.create_image_post(
                        image_path=post["image_path"],
                        title=post["title"],
                        tags=post["tags"]
                    )
                else:
                    logger.error(f"Unknown type: {post['type']}")
                    sheets_mgr.update_cell(post_queue, post["row"], 6, "Failed")
                    sheets_mgr.update_cell(post_queue, post["row"], 9, "Invalid type")
                    failed += 1
                    continue

                timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                if result and "Posted" in result["status"]:
                    sheets_mgr.update_cell(post_queue, post["row"], 6, "Done")
                    sheets_mgr.update_cell(post_queue, post["row"], 7, result["url"])
                    sheets_mgr.update_cell(post_queue, post["row"], 8, timestamp)
                    sheets_mgr.update_cell(post_queue, post["row"], 9, result["status"])
                    success += 1
                else:
                    sheets_mgr.update_cell(post_queue, post["row"], 6, "Failed")
                    sheets_mgr.update_cell(post_queue, post["row"], 9, result.get("status", "Error"))
                    failed += 1

                time.sleep(3)

            except Exception as e:
                logger.error(f"Error: {e}")
                sheets_mgr.update_cell(post_queue, post["row"], 6, "Failed")
                sheets_mgr.update_cell(post_queue, post["row"], 9, str(e)[:50])
                failed += 1

        logger.info("\n" + "=" * 70)
        logger.success(f"✅ Success: {success}/{len(pending)}")
        logger.error(f"❌ Failed: {failed}/{len(pending)}")
        logger.info("=" * 70 + "\n")

    finally:
        browser_mgr.close()

# ============================================================================
# PHASE 3: INBOX MODE
# ============================================================================

def run_inbox_mode(args):
    """Phase 3: Monitor inbox and send replies"""
    logger = Logger("inbox")
    logger.info("=" * 70)
    logger.info(f"DamaDam Bot V{VERSION} - INBOX MODE")
    logger.info("=" * 70 + "\n")

    browser_mgr = BrowserManager(logger)
    driver = browser_mgr.setup()
    if not driver:
        return

    try:
        if not browser_mgr.login():
            return

        sheets_mgr = SheetsManager(logger)
        if not sheets_mgr.connect():
            return

        monitor = InboxMonitor(driver, logger)
        inbox_queue = sheets_mgr.get_sheet(Config.SHEET_ID, "InboxQueue")
        if not inbox_queue:
            return

        logger.info("📥 Fetching inbox...")
        inbox_messages = monitor.fetch_inbox()
        logger.success(f"Found {len(inbox_messages)} conversations\n")

        sheets_mgr.api_calls += 1
        existing_rows = inbox_queue.get_all_values()
        existing_nicks = {row[0].strip().lower() for row in existing_rows[1:] if row}

        new_count = 0
        for msg in inbox_messages:
            if msg["nick"].lower() not in existing_nicks:
                values = [
                    msg["nick"], msg["nick"], msg["last_msg"], "",
                    "pending", msg["timestamp"], "", ""
                ]
                sheets_mgr.append_row(inbox_queue, values)
                logger.info(f"➕ New: {msg['nick']}")
                new_count += 1

        if new_count:
            logger.success(f"Added {new_count} new conversations\n")

        sheets_mgr.api_calls += 1
        all_rows = inbox_queue.get_all_values()

        pending_replies = []
        for i, row in enumerate(all_rows[1:], start=2):
            if len(row) >= 5 and row[3].strip() and row[4].strip().lower().startswith("pending"):
                pending_replies.append({
                    "row": i,
                    "nick": row[0].strip(),
                    "reply": row[3].strip()
                })

        if not pending_replies:
            logger.info("No pending replies")
            return

        logger.info(f"📤 Sending {len(pending_replies)} replies...\n")

        success = 0
        for idx, reply in enumerate(pending_replies, 1):
            logger.info(f"[{idx}/{len(pending_replies)}] {reply['nick']}")

            try:
                conv_url = None
                for msg in inbox_messages:
                    if msg["nick"].lower() == reply["nick"].lower():
                        conv_url = msg["conv_url"]
                        break

                if not conv_url:
                    conv_url = f"{Config.BASE_URL}/inbox/{reply['nick']}/"

                if monitor.send_reply(conv_url, reply["reply"]):
                    conv_log = monitor.get_conversation_log(conv_url)
                    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    sheets_mgr.update_cell(inbox_queue, reply["row"], 5, "sent")
                    sheets_mgr.update_cell(inbox_queue, reply["row"], 6, timestamp)
                    if conv_log:
                        sheets_mgr.update_cell(inbox_queue, reply["row"], 8, conv_log)
                    success += 1

                time.sleep(2)
            except Exception as e:
                logger.error(f"Error: {e}")

        logger.info("\n" + "=" * 70)
        logger.success(f"✅ Sent: {success}/{len(pending_replies)}")
        logger.info("=" * 70 + "\n")

    finally:
        browser_mgr.close()

# ============================================================================
# MAIN
# ============================================================================

def main():
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except Exception:
        pass

    parser = argparse.ArgumentParser(
        description=f"DamaDam Bot V{VERSION}",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )

    parser.add_argument(
        "--mode",
        choices=["msg", "post", "inbox"],
        default="msg",
        help="Operation mode"
    )

    parser.add_argument(
        "--max-profiles",
        type=int,
        default=None,
        help="Max targets to process"
    )

    args = parser.parse_args()

    if args.max_profiles is not None:
        Config.MAX_PROFILES = args.max_profiles

    try:
        if args.mode == "msg":
            run_message_mode(args)
        elif args.mode == "post":
            run_post_mode(args)
        elif args.mode == "inbox":
            run_inbox_mode(args)
    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted[/yellow]")
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        sys.exit(1)

if __name__ == "__main__":
    main()

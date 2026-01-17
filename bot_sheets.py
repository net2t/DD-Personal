# ============================================================================
# bot_sheets.py - Google Sheets Manager
# ============================================================================

import time
import gspread
from google.oauth2.service_account import Credentials
from gspread.exceptions import WorksheetNotFound
from bot_config import Config

class SheetsManager:
    """Manages Google Sheets operations with retry logic"""
    
    def __init__(self, logger):
        self.logger = logger
        self.client = None
        self.api_calls = 0
    
    def connect(self) -> bool:
        """Connect to Google Sheets"""
        try:
            import os
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
            self.logger.success(f"Created sheet: {sheet_name}")
            return sheet
        except Exception as e:
            self.logger.error(f"Failed to create sheet '{sheet_name}': {e}")
            return None
    
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
# bot_scraper.py - Profile Scraper
# ============================================================================

import re
import time
from datetime import datetime, timedelta, timezone
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from bot_config import Config

class ProfileScraper:
    """Handles profile scraping and post finding"""
    
    def __init__(self, driver, logger):
        self.driver = driver
        self.logger = logger
    
    def scrape_profile(self, nickname: str) -> dict:
        """Scrape user profile data"""
        url = f"{Config.BASE_URL}/users/{nickname}/"
        
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
            if 'account suspended' in page_source:
                data['STATUS'] = "Suspended"
                self.logger.warning(f"Account suspended: {nickname}")
                return data
            elif 'background:tomato' in page_source or 'style="background:tomato"' in page_source:
                data['STATUS'] = "Unverified"
            else:
                data['STATUS'] = "Verified"
            
            # Extract profile fields
            fields_map = {
                'City:': 'CITY',
                'Gender:': 'GENDER',
            }
            
            for label, key in fields_map.items():
                try:
                    elem = self.driver.find_element(
                        By.XPATH,
                        f"//b[contains(text(), '{label}')]/following-sibling::span[1]"
                    )
                    value = elem.text.strip()
                    
                    if key == 'GENDER':
                        low = value.lower()
                        data[key] = "🚺" if low == 'female' else "🚹" if low == 'male' else value
                    else:
                        data[key] = value
                except:
                    continue
            
            # Extract posts count
            try:
                posts_elem = self.driver.find_element(
                    By.CSS_SELECTOR,
                    "a[href*='/profile/public/'] button div:first-child"
                )
                match = re.search(r'(\d+)', posts_elem.text)
                if match:
                    data['POSTS'] = match.group(1)
            except:
                pass
            
            # Extract followers count
            try:
                followers_elem = self.driver.find_element(
                    By.CSS_SELECTOR,
                    "span.cl.sp.clb"
                )
                match = re.search(r'(\d+)', followers_elem.text)
                if match:
                    data['FOLLOWERS'] = match.group(1)
            except:
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
    
    def find_open_post(self, nickname: str, post_type: str = "any") -> str:
        """
        Find first open post (text or image)
        
        Args:
            nickname: User nickname
            post_type: 'text', 'image', or 'any'
        
        Returns:
            Post URL or None
        """
        url = f"{Config.BASE_URL}/profile/public/{nickname}/"
        
        try:
            self.logger.debug(f"Finding open post for: {nickname}")
            
            for page_num in range(1, Config.MAX_POST_PAGES + 1):
                self.driver.get(url)
                time.sleep(3)
                
                # Find all posts on page
                posts = self.driver.find_elements(By.CSS_SELECTOR, "article.mbl, article")
                self.logger.debug(f"Page {page_num}: Found {len(posts)} posts")
                
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
                                link = post.find_element(By.CSS_SELECTOR, sel)
                                href = link.get_attribute("href") or ""
                                if href:
                                    found_type = "text" if "/comments/text/" in href else "image"
                                    break
                            except:
                                continue
                        
                        # Fallback: try reply button
                        if not href:
                            try:
                                reply_btn = post.find_element(
                                    By.XPATH,
                                    ".//a[button[@itemprop='discussionUrl']]"
                                )
                                href = reply_btn.get_attribute("href") or ""
                            except:
                                continue
                        
                        if href:
                            clean_href = self.clean_url(href)
                            self.logger.debug(f"Found {found_type} post #{idx}: {clean_href}")
                            return clean_href
                            
                    except Exception as e:
                        self.logger.debug(f"Post #{idx} check failed: {e}")
                        continue
                
                # Try next page
                try:
                    next_link = self.driver.find_element(By.CSS_SELECTOR, "a[rel='next']")
                    next_href = next_link.get_attribute("href") or ""
                    if not next_href:
                        break
                    url = next_href
                except:
                    break
            
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
        url = re.sub(r'/\d+/#reply$', '', url)
        url = re.sub(r'/#reply$', '', url)
        url = url.rstrip('/')
        
        return url
    
    @staticmethod
    def is_valid_url(url: str) -> bool:
        """Check if URL is valid DamaDam post URL"""
        if not url:
            return False
        return ("damadam.pk" in url and 
                ("/comments/text/" in url or "/comments/image/" in url or "/content/" in url))
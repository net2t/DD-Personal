# ============================================================================
# bot_messenger.py - Message Sender & Recorder
# ============================================================================

import time
from datetime import datetime
from selenium.webdriver.common.by import By
from selenium.common.exceptions import NoSuchElementException
from bot_config import Config

class MessageRecorder:
    """Records message history by nickname"""
    
    def __init__(self, sheets_manager, logger):
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
    
    def get_history(self, nick: str) -> list:
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


class MessageSender:
    """Handles sending messages to posts"""
    
    def __init__(self, driver, logger, scraper, recorder):
        self.driver = driver
        self.logger = logger
        self.scraper = scraper
        self.recorder = recorder
    
    def send_message(self, post_url: str, message: str, nick: str = "") -> dict:
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
                    except:
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
                "recent": any(x in fresh_page.lower() for x in ['sec ago', 'secs ago', 'just now'])
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
    
    def process_template(self, template: str, profile: dict) -> str:
        """Process message template with profile data"""
        message = template
        
        replacements = {
            '{{name}}': profile.get('NAME', 'Unknown'),
            '{{nick}}': profile.get('NICK', 'Unknown'),
            '{{city}}': profile.get('CITY', 'Unknown'),
            '{{posts}}': str(profile.get('POSTS', '0')),
            '{{followers}}': str(profile.get('FOLLOWERS', '0')),
        }
        
        for placeholder, value in replacements.items():
            message = message.replace(placeholder, value)
        
        return message

# ============================================================================
# bot_poster.py - Post Creator
# ============================================================================

import os
import time
from selenium.webdriver.common.by import By
from selenium.common.exceptions import NoSuchElementException
from bot_config import Config

class PostCreator:
    """Handles creating new posts (text/image)"""
    
    def __init__(self, driver, logger):
        self.driver = driver
        self.logger = logger
    
    def create_text_post(self, title: str, content: str, tags: str = "") -> dict:
        """Create a text post"""
        try:
            self.logger.info("Creating text post...")
            self.driver.get(f"{Config.BASE_URL}/share/text/")
            time.sleep(3)
            
            try:
                # Find form elements
                title_input = self.driver.find_element(
                    By.CSS_SELECTOR,
                    "input[name='title'], #id_title"
                )
                content_area = self.driver.find_element(
                    By.CSS_SELECTOR,
                    "textarea[name='text'], #id_text"
                )
                submit_btn = self.driver.find_element(
                    By.CSS_SELECTOR,
                    "button[type='submit']"
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
                    except:
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
    
    def create_image_post(self, image_path: str, title: str = "", tags: str = "") -> dict:
        """Create an image post from local file"""
        try:
            self.logger.info(f"Creating image post...")
            
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
                    "input[type='file']"
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
                    except:
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
                    except:
                        self.logger.debug("Tags field not found")
                
                # Submit
                submit_btn = self.driver.find_element(
                    By.CSS_SELECTOR,
                    "button[type='submit'], input[type='submit']"
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
# bot_inbox.py - Inbox Monitor
# ============================================================================

import time
from datetime import datetime
from selenium.webdriver.common.by import By
from bot_config import Config

class InboxMonitor:
    """Monitors inbox and manages replies"""
    
    def __init__(self, driver, logger):
        self.driver = driver
        self.logger = logger
    
    def fetch_inbox(self) -> list:
        """Fetch all inbox messages"""
        try:
            self.logger.info("Fetching inbox...")
            self.driver.get(f"{Config.BASE_URL}/inbox/")
            time.sleep(3)
            
            messages = []
            
            # Find conversation items
            # Note: Selectors may need adjustment based on actual page structure
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
                    except:
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
                except:
                    continue
            
            return "\n".join(log_lines)
            
        except Exception as e:
            self.logger.error(f"Conversation log error: {e}")
            return ""
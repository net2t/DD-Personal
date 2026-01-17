"""
DamaDam Bot V2.0.0 - Complete Main File
Clean, Organized, Multi-Mode Bot

Usage:
    python bot_main.py --mode msg --max-profiles 10
    python bot_main.py --mode post
    python bot_main.py --mode inbox
"""

import time
import os
import sys
import argparse
from datetime import datetime
from pathlib import Path
from rich.console import Console

# Import bot modules
from bot_config import Config
from bot_logger import Logger
from bot_browser import BrowserManager
from bot_sheets import SheetsManager
from bot_scraper import ProfileScraper
from bot_messenger import MessageSender, MessageRecorder
from bot_poster import PostCreator
from bot_inbox import InboxMonitor

console = Console()
VERSION = "2.0.0"

# ============================================================================
# PHASE 1: MESSAGE MODE
# ============================================================================

def run_message_mode(args):
    """Phase 1: Send personal messages to targets"""
    logger = Logger("msg")
    logger.info(f"{'='*70}")
    logger.info(f"DamaDam Bot V{VERSION} - MESSAGE MODE")
    logger.info(f"{'='*70}\n")
    
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
                
                if nick_or_url and message and status == "pending":
                    pending.append({
                        'row': i,
                        'mode': mode,
                        'name': name,
                        'nick_or_url': nick_or_url,
                        'city': city,
                        'posts': posts,
                        'followers': followers,
                        'message': message
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
        logger.info(f"{'='*70}\n")
        
        # Process each target
        success_count = 0
        failed_count = 0
        
        for idx, target in enumerate(pending, 1):
            logger.info(f"\n{'─'*70}")
            logger.info(f"[{idx}/{len(pending)}] 👤 Processing: {target['name']}")
            logger.info(f"{'─'*70}")
            
            try:
                mode = target['mode']
                name = target['name']
                nick_or_url = target['nick_or_url']
                message = target['message']
                row_num = target['row']
                
                post_url = None
                profile = {
                    'NAME': name,
                    'NICK': nick_or_url,
                    'CITY': target.get('city', ''),
                    'POSTS': target.get('posts', '0'),
                    'FOLLOWERS': target.get('followers', '0')
                }
                
                # Handle MODE
                if mode == "url":
                    # Direct URL mode
                    post_url = ProfileScraper.clean_url(nick_or_url)
                    if not ProfileScraper.is_valid_url(post_url):
                        raise ValueError(f"Invalid URL: {nick_or_url}")
                    logger.info(f"🌐 Mode: Direct URL")
                    logger.info(f"   Target: {post_url}")
                    
                else:
                    # Nick mode - scrape profile first
                    logger.info(f"👤 Mode: Nickname")
                    logger.info(f"   Target: {nick_or_url}")
                    
                    profile = scraper.scrape_profile(nick_or_url)
                    if not profile:
                        logger.error("❌ Profile scrape failed")
                        sheets_mgr.update_cell(msglist, row_num, 8, "Failed")
                        sheets_mgr.update_cell(msglist, row_num, 9, "Profile scrape failed")
                        failed_count += 1
                        continue
                    
                    # Check if suspended
                    if profile.get('STATUS') == 'Suspended':
                        logger.warning("⚠️ Account suspended")
                        sheets_mgr.update_cell(msglist, row_num, 8, "Skipped")
                        sheets_mgr.update_cell(msglist, row_num, 9, "Account suspended")
                        failed_count += 1
                        continue
                    
                    # Update sheet with profile data
                    if profile.get('CITY'):
                        sheets_mgr.update_cell(msglist, row_num, 4, profile['CITY'])
                    if profile.get('POSTS'):
                        sheets_mgr.update_cell(msglist, row_num, 5, profile['POSTS'])
                    if profile.get('FOLLOWERS'):
                        sheets_mgr.update_cell(msglist, row_num, 6, profile['FOLLOWERS'])
                    
                    # Check post count
                    post_count = int(profile.get('POSTS', '0'))
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
                        sheets_mgr.update_cell(msglist, row_num, 8, "Failed")
                        sheets_mgr.update_cell(msglist, row_num, 9, "No open posts")
                        failed_count += 1
                        continue
                
                # Process message template
                processed_msg = sender.process_template(message, profile)
                logger.info(f"💬 Message: '{processed_msg}' ({len(processed_msg)} chars)")
                
                # Send message
                result = sender.send_message(post_url, processed_msg, nick_or_url)
                
                # Update sheet based on result
                timestamp = datetime.now().strftime("%I:%M %p")
                if "Posted" in result['status']:
                    logger.success(f"✅ SUCCESS - Message posted!")
                    logger.info(f"🔗 URL: {result['url']}")
                    sheets_mgr.update_cell(msglist, row_num, 8, "Done")
                    sheets_mgr.update_cell(msglist, row_num, 9, f"Posted @ {timestamp}")
                    sheets_mgr.update_cell(msglist, row_num, 10, result['url'])
                    success_count += 1
                    
                elif "Verification" in result['status']:
                    logger.warning(f"⚠️ Needs manual verification")
                    logger.info(f"🔗 Check: {result['url']}")
                    sheets_mgr.update_cell(msglist, row_num, 8, "Done")
                    sheets_mgr.update_cell(msglist, row_num, 9, f"Verify @ {timestamp}")
                    sheets_mgr.update_cell(msglist, row_num, 10, result['url'])
                    success_count += 1
                    
                else:
                    logger.error(f"❌ FAILED - {result['status']}")
                    sheets_mgr.update_cell(msglist, row_num, 8, "Failed")
                    sheets_mgr.update_cell(msglist, row_num, 9, result['status'])
                    if result.get('url'):
                        sheets_mgr.update_cell(msglist, row_num, 10, result['url'])
                    failed_count += 1
                
                # Rate limiting
                time.sleep(2)
                
            except Exception as e:
                error_msg = str(e)[:60]
                logger.error(f"❌ Error: {error_msg}")
                sheets_mgr.update_cell(msglist, target['row'], 8, "Failed")
                sheets_mgr.update_cell(msglist, target['row'], 9, error_msg)
                failed_count += 1
        
        # Summary
        logger.info(f"\n{'='*70}")
        logger.info("📊 MESSAGE MODE SUMMARY")
        logger.info(f"{'='*70}")
        logger.success(f"✅ Success: {success_count}/{len(pending)}")
        logger.error(f"❌ Failed: {failed_count}/{len(pending)}")
        logger.info(f"📞 API Calls: {sheets_mgr.api_calls}")
        logger.info(f"📝 Log: {logger.log_file}")
        logger.info(f"{'='*70}\n")
        
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
    logger.info(f"{'='*70}")
    logger.info(f"DamaDam Bot V{VERSION} - POST MODE")
    logger.info(f"{'='*70}\n")
    
    browser_mgr = BrowserManager(logger)
    driver = browser_mgr.setup()
    if not driver:
        return
    
    try:
        # Login
        if not browser_mgr.login():
            return
        
        # Connect sheets
        sheets_mgr = SheetsManager(logger)
        if not sheets_mgr.connect():
            return
        
        # Initialize post creator
        creator = PostCreator(driver, logger)
        
        # Get PostQueue sheet
        post_queue = sheets_mgr.get_sheet(Config.SHEET_ID, "PostQueue")
        if not post_queue:
            return
        
        # Load pending posts
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
                
                if status == "pending":
                    pending.append({
                        'row': i,
                        'type': post_type,
                        'title': title,
                        'content': content,
                        'image_path': image_path,
                        'tags': tags
                    })
        
        if not pending:
            logger.warning("No pending posts in PostQueue")
            return
        
        if Config.MAX_PROFILES > 0:
            pending = pending[:Config.MAX_PROFILES]
        
        logger.success(f"Found {len(pending)} pending posts\n")
        
        # Process posts
        success = 0
        failed = 0
        
        for idx, post in enumerate(pending, 1):
            logger.info(f"\n[{idx}/{len(pending)}] 📝 {post['type'].upper()}: {post['title'] or 'Untitled'}")
            logger.info("─" * 50)
            
            try:
                result = None
                
                if post['type'] == "text":
                    result = creator.create_text_post(
                        title=post['title'],
                        content=post['content'],
                        tags=post['tags']
                    )
                elif post['type'] == "image":
                    result = creator.create_image_post(
                        image_path=post['image_path'],
                        title=post['title'],
                        tags=post['tags']
                    )
                else:
                    logger.error(f"Unknown type: {post['type']}")
                    sheets_mgr.update_cell(post_queue, post['row'], 6, "Failed")
                    sheets_mgr.update_cell(post_queue, post['row'], 9, "Invalid type")
                    failed += 1
                    continue
                
                # Update sheet
                timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                if result and "Posted" in result['status']:
                    sheets_mgr.update_cell(post_queue, post['row'], 6, "Done")
                    sheets_mgr.update_cell(post_queue, post['row'], 7, result['url'])
                    sheets_mgr.update_cell(post_queue, post['row'], 8, timestamp)
                    sheets_mgr.update_cell(post_queue, post['row'], 9, result['status'])
                    success += 1
                else:
                    sheets_mgr.update_cell(post_queue, post['row'], 6, "Failed")
                    sheets_mgr.update_cell(post_queue, post['row'], 9, result.get('status', 'Error'))
                    failed += 1
                
                time.sleep(3)
                
            except Exception as e:
                logger.error(f"Error: {e}")
                sheets_mgr.update_cell(post_queue, post['row'], 6, "Failed")
                sheets_mgr.update_cell(post_queue, post['row'], 9, str(e)[:50])
                failed += 1
        
        # Summary
        logger.info(f"\n{'='*70}")
        logger.success(f"✅ Success: {success}/{len(pending)}")
        logger.error(f"❌ Failed: {failed}/{len(pending)}")
        logger.info(f"{'='*70}\n")
        
    finally:
        browser_mgr.close()

# ============================================================================
# PHASE 3: INBOX MODE
# ============================================================================

def run_inbox_mode(args):
    """Phase 3: Monitor inbox and send replies"""
    logger = Logger("inbox")
    logger.info(f"{'='*70}")
    logger.info(f"DamaDam Bot V{VERSION} - INBOX MODE")
    logger.info(f"{'='*70}\n")
    
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
        
        # Fetch inbox
        logger.info("📥 Fetching inbox...")
        inbox_messages = monitor.fetch_inbox()
        logger.success(f"Found {len(inbox_messages)} conversations\n")
        
        # Update queue with new messages
        sheets_mgr.api_calls += 1
        existing_rows = inbox_queue.get_all_values()
        existing_nicks = {row[0].strip().lower() for row in existing_rows[1:] if row}
        
        new_count = 0
        for msg in inbox_messages:
            if msg['nick'].lower() not in existing_nicks:
                values = [
                    msg['nick'], msg['nick'], msg['last_msg'], "",
                    "pending", msg['timestamp'], "", ""
                ]
                sheets_mgr.append_row(inbox_queue, values)
                logger.info(f"➕ New: {msg['nick']}")
                new_count += 1
        
        if new_count:
            logger.success(f"Added {new_count} new conversations\n")
        
        # Process pending replies
        sheets_mgr.api_calls += 1
        all_rows = inbox_queue.get_all_values()
        
        pending_replies = []
        for i, row in enumerate(all_rows[1:], start=2):
            if len(row) >= 5 and row[3].strip() and row[4].strip().lower() == "pending":
                pending_replies.append({
                    'row': i,
                    'nick': row[0].strip(),
                    'reply': row[3].strip()
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
                    if msg['nick'].lower() == reply['nick'].lower():
                        conv_url = msg['conv_url']
                        break
                
                if not conv_url:
                    conv_url = f"https://damadam.pk/inbox/{reply['nick']}/"
                
                if monitor.send_reply(conv_url, reply['reply']):
                    conv_log = monitor.get_conversation_log(conv_url)
                    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    sheets_mgr.update_cell(inbox_queue, reply['row'], 5, "sent")
                    sheets_mgr.update_cell(inbox_queue, reply['row'], 6, timestamp)
                    if conv_log:
                        sheets_mgr.update_cell(inbox_queue, reply['row'], 8, conv_log)
                    success += 1
                    
                time.sleep(2)
            except Exception as e:
                logger.error(f"Error: {e}")
        
        logger.info(f"\n{'='*70}")
        logger.success(f"✅ Sent: {success}/{len(pending_replies)}")
        logger.info(f"{'='*70}\n")
        
    finally:
        browser_mgr.close()

# ============================================================================
# MAIN
# ============================================================================

def main():
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except:
        pass
    
    parser = argparse.ArgumentParser(
        description=f"DamaDam Bot V{VERSION}",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    parser.add_argument('--mode', choices=['msg', 'post', 'inbox'],
                       default='msg', h

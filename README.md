# DamaDam Bot V2.0 - Complete Documentation

## 🎯 Overview

Clean, modular, multi-mode automation bot for DamaDam.pk with three complete modes:

- **MSG Mode** (Phase 1): Send personal messages to targets
- **POST Mode** (Phase 2): Create new text/image posts
- **INBOX Mode** (Phase 3): Monitor inbox and send replies

## File Structure

```text
damadam-bot/
├── main.py               # Single-file implementation (all logic)
├── requirements.txt      # Python dependencies
├── .env                  # Environment variables (create this)
├── credentials.json      # Google service account (create this)
├── chromedriver.exe      # ChromeDriver binary (place in repo root)
└── logs/                 # Auto-created log directory
```

Notes:

- **Security**: `.env` and `credentials.json` are intentionally ignored by Git.
- **Local binary**: `chromedriver.exe` is intentionally ignored by Git.

## Installation

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

**requirements.txt:**

```text
gspread>=5.8.0
google-auth>=2.20.0
google-auth-oauthlib>=1.0.0
selenium==4.27.1
python-dotenv>=1.0.0
rich>=13.0.0
```

### 2. Setup Google Sheets

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project
3. Enable **Google Sheets API**
4. Create **Service Account**
5. Download JSON key as `credentials.json`
6. Share your Google Sheet with the service account email

### 3. Create .env File

```text
# DamaDam Credentials
DD_LOGIN_EMAIL=your_username
DD_LOGIN_PASS=your_password

# Secondary login (optional fallback)
DD_LOGIN_EMAIL2=backup_username
DD_LOGIN_PASS2=backup_password

# Google Sheets
DD_SHEET_ID=your_main_sheet_id
DD_PROFILES_SHEET_ID=your_profiles_sheet_id
CREDENTIALS_FILE=credentials.json

# Browser
CHROMEDRIVER_PATH=chromedriver.exe

# Bot Settings
DD_DEBUG=0
DD_MAX_PROFILES=0
DD_MAX_POST_PAGES=4
DD_AUTO_PUSH=0
```

## Google Sheets Structure

### Sheet 1: MsgList (Message Targets)

Example rows:

```text
MODE | NAME | NICK/URL | CITY | POSTS | FOLLOWERS | MESSAGE | STATUS | NOTES | RESULT URL
nick | John | john123  | Karachi | 50 | 100 | Hello {{name}}! | pending | | 
url  | Sara | https://damadam.pk/comments/text/12345 |  |  |  | Hi there! | pending | |
```

**Columns:**

- **MODE**: `nick` or `url`
- **NAME**: Display name
- **NICK/URL**: Nickname (nick mode) or direct post URL (url mode)
- **CITY/POSTS/FOLLOWERS**: Auto-filled from profile
- **MESSAGE**: Template message (supports: {{name}}, {{city}}, {{posts}}, {{followers}})
- **STATUS**: `pending` → `Done/Failed/Skipped`
- **NOTES**: Error details
- **RESULT URL**: Final post URL

### Sheet 2: PostQueue (Create Posts)

Example rows:

```text
TYPE  | CONTENT | IMAGE_PATH       | STATUS  | POST_URL | TIMESTAMP | NOTES
text  | This is my content... |  | pending |  |  | 
image | My caption | C:\images\pic.jpg | pending |  |  | 
```

**Columns:**

- **TYPE**: `text` or `image`
- **CONTENT**: Text content (for text posts) / caption (for image posts)
- **IMAGE_PATH**: Full path to image file (for image posts)
- **STATUS**: `pending` → `Done/Failed`
- **POST_URL**: Created post URL
- **TIMESTAMP**: Creation time
- **NOTES**: Status/errors

Compatibility:

- If your existing sheet still has `TITLE` and `TAGS` columns (older layout), the bot will still work.

Image posts:

- **Caption**: Uses `CONTENT` (caption textarea on DamaDam).
- **Expiry**: Defaults to `Never expire post`.
- **Turn Off Replies**: Defaults to `Yes`.

### Sheet 3: InboxQueue (Inbox Replies)

Example rows:

```text
NICK | NAME | LAST_MSG | MY_REPLY | STATUS | TIMESTAMP | NOTES | CONVERSATION_LOG
user123 | User | Hi there! | Hello! How are you? | pending | 2025-01-16 10:30:00 | |
```

**Workflow:**

1. Bot fetches inbox → adds new conversations with STATUS=`pending`
2. You manually fill **MY_REPLY** column
3. Run bot again → it sends replies
4. STATUS changes to `sent`, full conversation saved in CONVERSATION_LOG

### Sheet 4: MsgHistory (Auto-created)

Records all sent messages by nickname for tracking.

```text
TIMESTAMP | NICK | NAME | MESSAGE | POST_URL | STATUS | RESULT_URL
```

## Usage

### MSG Mode (Send Personal Messages)

```bash
# Send messages to all pending targets
python main.py --mode msg

# Limit to 10 targets
python main.py --mode msg --max-profiles 10

# Debug mode
DD_DEBUG=1 python main.py --mode msg --max-profiles 1
```

**How it works:**

1. Reads pending targets from `MsgList` sheet
2. For **nick mode**: Scrapes profile → finds open post → sends message
3. For **url mode**: Uses direct URL → sends message
4. Processes template placeholders ({{name}}, {{city}}, etc.)
5. Verifies message posted
6. Updates sheet with result
7. Records to `MsgHistory`

### POST Mode (Create Posts)

```bash
# Create all pending posts
python main.py --mode post

# Limit to 5 posts
python main.py --mode post --max-profiles 5
```

**How it works:**

1. Reads pending posts from `PostQueue`
2. For **text posts**: Opens text creation form → fills → submits
3. For **image posts**: Opens upload form → uploads local file → submits
4. Updates sheet with post URL and status

### INBOX Mode (Monitor & Reply)

```bash
# Check inbox and send replies
python main.py --mode inbox
```

**How it works:**

1. Fetches all inbox conversations
2. Adds new conversations to `InboxQueue` with STATUS=`pending`
3. Finds rows where MY_REPLY is filled and STATUS=`pending`
4. Sends those replies
5. Updates STATUS to `sent`
6. Records full conversation log

## Logs

All logs saved to `logs/` folder:

```text
logs/
├── msg_20250116_143022.log      # Message mode logs
├── post_20250116_143523.log     # Post mode logs
└── inbox_20250116_144012.log    # Inbox mode logs
```

Each log contains:

- Timestamps in Pakistan time
- Operation details
- Success/failure status
- Error messages
- API call counts

## Configuration Options

**Environment Variables:**

- `DD_LOGIN_EMAIL`: DamaDam username (required)
- `DD_LOGIN_PASS`: DamaDam password (required)
- `DD_SHEET_ID`: Main Google Sheet ID (required)
- `DD_PROFILES_SHEET_ID`: Profiles sheet ID (optional)
- `CREDENTIALS_FILE`: Google credentials file (default: `credentials.json`)
- `CHROMEDRIVER_PATH`: ChromeDriver path (default: `chromedriver.exe`)
- `DD_DEBUG`: Enable debug logging (default: `0`)
- `DD_MAX_PROFILES`: Max targets to process (default: `0` = unlimited)
- `DD_MAX_POST_PAGES`: Max pages to search for open posts (default: `4`)
- `DD_AUTO_PUSH`: Auto git push after run (default: `0`)

## Message Templates

Use these placeholders in your messages:

```text
Hello {{name}}!

I see you're from {{city}} and have {{posts}} posts!
You have {{followers}} followers - impressive!

Best regards!
```

**Available Placeholders:**

- `{{name}}` - User's display name
- `{{nick}}` - User's nickname
- `{{city}}` - User's city
- `{{posts}}` - Number of posts
- `{{followers}}` - Number of followers

## Troubleshooting

### Login Fails

```bash
# Delete old cookies and try again
rm damadam_cookies.pkl
python main.py --mode msg --max-profiles 1
```

### No Open Posts Found

- User's posts might have comments disabled
- Increase search depth: `DD_MAX_POST_PAGES=10`
- Try direct URL mode instead

### Form Not Found

- Enable debug mode: `DD_DEBUG=1`
- Check logs for detailed error
- Page structure might have changed

### Sheets Connection Failed

- Verify `credentials.json` is correct
- Check if sheet is shared with service account
- Verify sheet ID in `.env`

## Example Workflows

### Workflow 1: Mass Personal Messaging

1. Add targets to `MsgList`:

```text
MODE: nick
NAME: User1
NICK/URL: user1
MESSAGE: Hi {{name}}! Love your posts!
STATUS: pending
```

1. Run bot:

```bash
python main.py --mode msg --max-profiles 20
```

1. Check results in `MsgList` (STATUS, NOTES, RESULT URL)
1. Review history in `MsgHistory` sheet

### Workflow 2: Daily Content Posting

1. Prepare posts in `PostQueue`:

```text
TYPE: text
TITLE: Daily Tip
CONTENT: Today's tip: Stay positive!
TAGS: motivation,tips
STATUS: pending
```

1. Run bot:

```bash
python main.py --mode post
```

1. Post URLs saved in `PostQueue`

### Workflow 3: Inbox Management

1. Run to fetch new messages:

```bash
python main.py --mode inbox
```

1. New conversations appear in `InboxQueue`

1. Add your replies in MY_REPLY column

1. Run again to send:

```bash
python main.py --mode inbox
```

1. Full conversation saved in CONVERSATION_LOG

## Security

- Never commit `.env` or `credentials.json`
- Use `.gitignore` to exclude sensitive files
- Rotate credentials regularly
- Use strong passwords

## Performance Tips

1. **Rate Limiting**: Bot includes 2-3 second delays between actions
2. **Batch Processing**: Use `--max-profiles` to limit targets
3. **Error Recovery**: Failed items stay as `pending` for retry
4. **API Efficiency**: Batched sheet updates minimize API calls

## Support

For issues:

1. Check logs in `logs/` folder
2. Enable debug mode: `DD_DEBUG=1`
3. Review error in NOTES column
4. Check this documentation

## License

MIT License - Use responsibly and ethically.

---

**Version:** 2.0.0  
**Last Updated:** January 2025
# World Cup 2026 Telegram Bot

Automatically notifies a Telegram group 1 hour before every FIFA World Cup 2026 match. All times shown in PT.

## Commands

| Command | Description |
|---|---|
| `/upcoming` | Next 3 upcoming matches |
| `/next` | The very next match |
| `/today` | All matches today |
| `/tomorrow` | All matches tomorrow |
| `/group A` | Full schedule for a group (A–L) |
| `/schedule Mexico` | All matches for a specific team |
| `/help` | List all commands |

## Setup

### 1. Clone and install

```bash
git clone https://github.com/JCMtz55/paloma-fifera-wc2026-bot
cd paloma-fifera-wc2026-bot
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Configure environment

Create a `.env` file:

```
BOT_TOKEN=your_telegram_bot_token
CHAT_ID=your_group_chat_id
```

- Get a bot token from [@BotFather](https://t.me/BotFather)
- Get your group chat ID by adding the bot to the group, sending a message, and visiting `https://api.telegram.org/botYOUR_TOKEN/getUpdates`

### 3. Run locally

```bash
python bot.py
```

## Deployment (Railway)

1. Push to GitHub
2. Create a new project on [Railway](https://railway.app) → Deploy from GitHub repo
3. Add `BOT_TOKEN` and `CHAT_ID` in the service's Variables tab
4. Railway will build and run automatically using the `Procfile`

## Adding knockout stage matches

Once the group stage ends (July 2), add the bracket matches to `schedule.py` following the same format, then push to GitHub. Railway will redeploy automatically.

## Project structure

```
bot.py          — Main bot logic, commands, and scheduler
schedule.py     — Full match schedule (72 group stage matches)
requirements.txt
Procfile        — Tells Railway to run: python bot.py
.env            — Local secrets (not committed)
.gitignore
```

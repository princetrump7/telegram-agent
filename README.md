# 🤖 Telegram AI Agent

A **Claude-powered** AI chat companion for Telegram. Conversational, context-aware, and deployable in minutes.

## Quick Start

### 1. Prerequisites

- Python 3.11+
- A [Telegram bot token](https://t.me/BotFather) from @BotFather
- An [Anthropic API key](https://console.anthropic.com/)

### 2. Setup

```bash
cd telegram-agent
python -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
```

Edit `.env` and fill in your `TELEGRAM_BOT_TOKEN` and `ANTHROPIC_API_KEY`.

### 3. Run (development)

```bash
python main.py
```

Message your bot on Telegram. It responds in polling mode — no public URL needed.

### 4. Deploy (production)

**Option A — Render.com**

1. Push this repo to GitHub
2. On Render, create a **New Web Service** (not static site)
3. Connect your repo
4. Settings:
   - **Runtime:** Docker
   - **Port:** 8080
   - **Environment variables:**
     - `TELEGRAM_BOT_TOKEN` ← your token
     - `ANTHROPIC_API_KEY` ← your key
     - `WEBHOOK_URL` ← `https://your-app.onrender.com`
5. Deploy

**Option B — Railway.app**

1. Push to GitHub
2. Create new project → Deploy from GitHub repo
3. Add the same environment variables
4. Railway auto-detects the Dockerfile

## Commands

| Command | Description |
|---|---|
| `/start` | Welcome & intro |
| `/help` | List commands |
| `/clear` | Reset conversation |
| `/stats` | Show token usage |
| `/new` | Start fresh |

## Architecture

```
Telegram → Webhook/Polling → Bot Handlers
  → Conversation Memory (per-user)
  → Claude API (Anthropic)
  → Response back to Telegram
```

- **Memory:** Last N message pairs per conversation (default: 20, configurable)
- **Rate limiting:** 1-second cooldown between messages (configurable)
- **Splitting:** Long responses auto-split into 4000-char chunks
- **Error handling:** Graceful failures with user-friendly messages

## Environment Variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `TELEGRAM_BOT_TOKEN` | ✅ | — | From @BotFather |
| `ANTHROPIC_API_KEY` | ✅ | — | From console.anthropic.com |
| `CLAUDE_MODEL` | ❌ | `claude-sonnet-4-20250514` | Model ID |
| `MAX_TOKENS` | ❌ | `1024` | Max response tokens |
| `MEMORY_SIZE` | ❌ | `20` | Message pairs to remember |
| `WEBHOOK_URL` | ❌ | — | Set for production deployment |
| `LOG_LEVEL` | ❌ | `INFO` | `DEBUG`, `INFO`, `WARNING` |

## License

MIT

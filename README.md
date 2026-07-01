# 🤖 Telegram AI Agent

An **AI-powered** chat companion for Telegram. Runs on OpenCode Zen (free models) or any OpenAI-compatible API. Conversational, context-aware, and deployable in minutes.

## Quick Start

### 1. Prerequisites

- Python 3.11+
- A [Telegram bot token](https://t.me/BotFather) from @BotFather
- An API key — get one free at [opencode.ai](https://opencode.ai)

### 2. Setup

```bash
cd telegram-agent
python -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
```

Edit `.env` and fill in your `TELEGRAM_BOT_TOKEN` and `OPENCODE_API_KEY`.

### 3. Run (development)

```bash
python main.py
```

Message your bot on Telegram. It responds in polling mode — no public URL needed.

### 4. Deploy (production)

**Option A — Render.com (via render.yaml)**

1. Push this repo to GitHub
2. On Render, create a **New Web Service** (not static site)
3. Connect your repo — `render.yaml` is auto-detected
4. Set `TELEGRAM_BOT_TOKEN` and `OPENCODE_API_KEY` as secret env vars
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
  → AI API (OpenCode Zen / OpenRouter / any OpenAI-compatible)
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
| `OPENCODE_API_KEY` | ✅ | — | From opencode.ai (free) |
| `OPENCODE_BASE_URL` | ❌ | `https://opencode.ai/zen/v1` | OpenAI-compatible API endpoint |
| `AI_MODEL` | ❌ | `deepseek-v4-flash-free` | Model ID (falls back through 4 models on empty response) |
| `MAX_TOKENS` | ❌ | `1024` | Max response tokens |
| `MEMORY_SIZE` | ❌ | `20` | Message pairs to remember |
| `WEBHOOK_URL` | ❌ | — | Set for production deployment |
| `LOG_LEVEL` | ❌ | `INFO` | `DEBUG`, `INFO`, `WARNING` |

## License

MIT

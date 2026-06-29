# Birthday Notifier Bot

**English** | [Русский](README.ru.md)

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![CI](https://github.com/renkagod/birthday-notifier-bot/actions/workflows/ci.yml/badge.svg)](https://github.com/renkagod/birthday-notifier-bot/actions/workflows/ci.yml)

Telegram bot for automatic birthday notifications with a modern interface and flexible settings.

## Features

- **Smart Textual Add**: add birthdays in a single natural language message (e.g., `John @john_tag 15.08.1990` or `Mary 3 August`).
- **Interactive UI**: manage the list, edit contact details, select dates, and delete contacts entirely through inline buttons with pagination (pages of 8 contacts).
- **Yearless Dates Support**: skip the birth year (lists will display `DD.MM` format without age).
- **Contact Import**: add contacts from your Telegram address book in a single click.
- **Telegram Tags**: automatic `@username` mapping for mentions in notifications.
- **Flexible Notifications**:
  - Scheduled: a month, a week, 3 days, tomorrow, or today at a chosen time.
  - Urgent: 30 minutes and 5 minutes before the event.
  - Midnight: greeting exactly at 00:00 (`-1.0` flag in settings).
- **List Sorting**: sort by name (alphabetically) or by upcoming occurrence.
- **Backups**: export all birthdays to JSON and import them back.
- **Docker**: ready-to-use Docker image, Compose configuration, resource limits, and timezone settings.

## Quick Start (Docker)

1. Clone the repository:

   ```bash
   git clone https://github.com/renkagod/birthday-notifier-bot.git
   cd birthday-notifier-bot
   ```

2. Configure environment:

   ```bash
   cp .env.example .env
   # Set your BOT_TOKEN in .env
   ```

3. Run:

   ```bash
   docker compose up -d --build
   ```

## Usage

After starting the bot, send `/start`.

- **📅 My List** — interactive menu to view birthdays with page navigation, quick rename, date edit, or deletion.
- **➕ Add** — add manually, share a contact from Telegram, or use step-by-step interactive calendar.
- **🔥 Upcoming** — see birthdays in the next 30 days.
- **⚙️ Settings** — configure the daily reminder time and active intervals (with quick presets).
- **💾 Backup** — export list to JSON file or restore from file.

## Development & Local Run

For development, you will need Python 3.10+:

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt -r requirements-dev.txt
cp .env.example .env        # specify your BOT_TOKEN

# Run linter and tests
ruff check bot tests
pytest -v

# Run bot
python -m bot.main
```

## Configuration

| Variable | Description |
|---|---|
| `BOT_TOKEN` | Bot token from [@BotFather](https://t.me/BotFather) |

For local development, you can set the `BIRTHDAY_BOT_DB_PATH` variable to change the path to the SQLite database (defaults to `data/birthdays.db`).

## License

[MIT](LICENSE) — Copyright (c) 2026 [renkagod](https://github.com/renkagod).

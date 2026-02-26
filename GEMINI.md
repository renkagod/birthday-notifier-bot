# GEMINI.md - Birthday Notifier Bot

This project is a Telegram bot designed to provide automated birthday reminders. It allows users to add, list, and delete birthday entries, with a scheduler that sends notifications at specific intervals before each event.

## Project Overview

*   **Type:** Telegram Bot (Python)
*   **Main Technologies:**
    *   **Bot Framework:** [aiogram](https://docs.aiogram.dev/) (v3+)
    *   **Scheduler:** [APScheduler](https://apscheduler.agronholm.info/) (AsyncIO version)
    *   **Database:** SQLite (local file-based storage)
    *   **Containerization:** Docker & Docker Compose
*   **Architecture:**
    *   `bot/main.py`: Entry point, initializes the bot, dispatcher, and scheduler. Contains command handlers (`/start`, `/add`, `/list`, `/delete`).
    *   `bot/database.py`: Simple CRUD operations for the SQLite database.
    *   `bot/scheduler.py`: Contains the `check_birthdays` job that runs every minute to verify if any notifications need to be sent.
    *   `data/`: Directory where the `birthdays.db` file is stored (persistent via Docker volumes).

## Building and Running

### Prerequisites
*   Docker and Docker Compose installed.
*   A Telegram Bot Token from [@BotFather](https://t.me/BotFather).

### Commands
1.  **Configuration:**
    Copy the example environment file and add your `BOT_TOKEN`:
    ```powershell
    cp .env.example .env
    ```
2.  **Start with Docker:**
    ```powershell
    docker compose up -d --build
    ```
3.  **Stop:**
    ```powershell
    docker compose down
    ```
4.  **Local Run (without Docker):**
    ```powershell
    pip install -r requirements.txt
    python -m bot.main
    ```

## Development Conventions

*   **Concurrency:** The project heavily uses `asyncio` (via `aiogram` and `AsyncIOScheduler`).
*   **Data Storage:** SQLite is used for simplicity. The database schema is initialized automatically on startup if it doesn't exist.
*   **Environment Variables:** Configuration is managed via `.env` file and loaded using `python-dotenv`.
*   **Scheduling Logic:** Notifications are sent at the following intervals before the birthday:
    *   1 week
    *   3 days
    *   1 day
    *   30 minutes
    *   5 minutes
*   **Formatting:** Dates are expected in `DD.MM.YYYY` format.

## Key Files

*   `Dockerfile`: Multi-stage-like simple build for Python 3.11-slim.
*   `docker-compose.yml`: Defines the `bot` service and data volume.
*   `bot/main.py`: The heart of the bot's interaction logic.
*   `bot/scheduler.py`: Logic for calculating birthday proximities and sending alerts.

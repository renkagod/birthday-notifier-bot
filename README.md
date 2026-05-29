# Birthday Notifier Bot

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![CI](https://github.com/renkagod/birthday-notifier-bot/actions/workflows/ci.yml/badge.svg)](https://github.com/renkagod/birthday-notifier-bot/actions/workflows/ci.yml)

Telegram-бот для автоматических напоминаний о днях рождения с современным интерфейсом и гибкими настройками.

## Особенности

- **Интерактивный UI**: управление через inline-кнопки и пошаговый календарь (десятилетие → год → месяц → день).
- **Умное добавление**: вручную или контакт из записной книжки.
- **Telegram-теги**: привязка `@username` для упоминаний в уведомлениях.
- **Гибкие уведомления**:
  - плановые: за месяц, неделю, 3 дня, завтра или сегодня в выбранное время;
  - оперативные: за 30 и 5 минут до события;
  - полночные: поздравление в 00:00 (флаг `-1.0` в настройках).
- **Сортировка списка**: по имени или по дате наступления.
- **Бэкапы**: экспорт и импорт списка в JSON.
- **Docker**: готовый образ, Compose, лимиты CPU/RAM, часовой пояс.

## Быстрый старт (Docker)

1. Склонируйте репозиторий:

   ```bash
   git clone https://github.com/renkagod/birthday-notifier-bot.git
   cd birthday-notifier-bot
   ```

2. Настройте конфигурацию:

   ```bash
   cp .env.example .env
   # Укажите BOT_TOKEN в .env
   ```

3. Запустите:

   ```bash
   docker compose up -d --build
   ```

## Использование

После запуска отправьте боту `/start`.

- **Мой список** — просмотр дат, сортировка, удаление и редактирование.
- **Настройки** — время ежедневных напоминаний и интервалы.
- **Бэкап** — экспорт/импорт JSON.

## Конфигурация

| Переменная   | Описание                          |
| ------------ | --------------------------------- |
| `BOT_TOKEN`  | Токен от [@BotFather](https://t.me/BotFather) |

Для локальной разработки и тестов можно задать `BIRTHDAY_BOT_DB_PATH` — путь к файлу SQLite (по умолчанию `data/birthdays.db`).

## Разработка

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt -r requirements-dev.txt
cp .env.example .env        # и укажите BOT_TOKEN

ruff check bot tests
pytest -v
python -m bot.main
```

## Структура проекта

| Путь                 | Назначение                              |
| -------------------- | --------------------------------------- |
| `bot/main.py`        | Telegram UI и команды                   |
| `bot/scheduler.py`   | Планировщик (APScheduler)               |
| `bot/database.py`    | SQLite                                  |
| `bot/dates.py`       | Расчёт дат и сортировка (unit-тесты)    |
| `bot/notifications.py` | Тексты уведомлений (unit-тесты)       |
| `tests/`             | Pytest                                  |

## Лицензия

[MIT](LICENSE) — Copyright (c) 2026 [renkagod](https://github.com/renkagod).

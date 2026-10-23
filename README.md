# Birthday Notifier Bot

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![CI](https://github.com/renkagod/birthday-notifier-bot/actions/workflows/ci.yml/badge.svg)](https://github.com/renkagod/birthday-notifier-bot/actions/workflows/ci.yml)
[![Donate](https://img.shields.io/badge/Donate-crypto-ea4aaa?logo=githubsponsors&logoColor=white)](https://github.com/renkagod/.github/blob/main/DONATE.md)

Telegram-бот для автоматических напоминаний о днях рождения с современным интерфейсом и гибкими настройками.

## Особенности

- Интерфейс на rich-сообщениях Telegram (Bot API 10.3) — экраны свёрстаны на Rich Markdown, а кнопки встроены прямо в текст: имена в таблицах кликабельны, переключатели стоят рядом с пунктами; нужна версия Telegram с поддержкой rich-сообщений
- Добавление одним сообщением — `Маша 3 августа` или `Иван @ivan 15.08.1990` сохраняется сразу, ошибку можно отменить кнопкой «Отменить»
- Поиск по имени — напишите имя или его часть, и бот откроет карточку
- Главная со сводкой ближайших дней рождения и полный список, сгруппированный по месяцам
- Даты без года рождения — такие записи показываются в формате `ДД.ММ` без возраста
- Выбор человека из чатов Telegram — имя и `@username` подставляются сами
- Гибкие уведомления: за месяц, неделю, 3 дня, накануне или в день события в выбранное время, за 30 и 5 минут до полуночи, а также ровно в полночь; в уведомлении есть кнопка «Поздравить»
- Экспорт всех записей в JSON и импорт обратно
- Готовый Docker-образ с лимитами ресурсов и настройкой часового пояса

## Быстрый старт

1. Клонируйте репозиторий:

   ```bash
   git clone https://github.com/renkagod/birthday-notifier-bot.git
   cd birthday-notifier-bot
   ```

2. Настройте окружение:

   ```bash
   cp .env.example .env
   # укажите BOT_TOKEN в .env
   ```

3. Запуск:

   ```bash
   docker compose up -d --build
   ```

## Использование

После запуска отправьте боту `/start`.

- **Главная** — ближайшие дни рождения и кнопки «➕ Добавить», «📋 Все», «⚙️»
- **Любой текст** — `Имя дата` добавляет человека, просто имя ищет его
- **Карточка** — дата, возраст, тег; изменить и удалить можно прямо из неё
- **⚙️ Настройки** — время напоминаний, интервалы и резервная копия на одном экране
- Команды: `/add`, `/list`, `/settings`, `/help`, `/cancel`

## Конфигурация (`.env`)

| Переменная | Обязательна | Описание |
|------------|--------------|----------|
| `BOT_TOKEN` | да | Токен бота от [@BotFather](https://t.me/BotFather) |
| `BIRTHDAY_BOT_DB_PATH` | нет | Путь к файлу базы SQLite (по умолчанию `data/birthdays.db`) |

## Docker

`docker-compose.yml` монтирует `./data` в `/app/data` для базы SQLite, фиксирует часовой пояс контейнера (`TZ=Europe/Moscow` — влияет на время срабатывания напоминаний), проверяет доступность базы через `healthcheck` и ограничивает контейнер до 256 MB / 0.30 CPU (резерв — 64 MB / 0.10 CPU).

```bash
docker compose up -d --build   # запуск
docker compose logs -f         # логи
docker compose down            # остановка
```

## Разработка и локальный запуск

Для разработки нужен Python 3.11+:

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt -r requirements-dev.txt
cp .env.example .env        # укажите BOT_TOKEN

# Линтер и тесты
ruff check bot tests
pytest -v

# Запуск бота
python -m bot.main
```

## Поддержать проект

Если проект оказался полезен, можно поддержать его криптой: [адреса для доната](https://github.com/renkagod/.github/blob/main/DONATE.md).

## Лицензия

[MIT](LICENSE) — Copyright (c) 2026 [renkagod](https://github.com/renkagod).

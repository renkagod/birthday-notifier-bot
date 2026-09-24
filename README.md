# Birthday Notifier Bot

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![CI](https://github.com/renkagod/birthday-notifier-bot/actions/workflows/ci.yml/badge.svg)](https://github.com/renkagod/birthday-notifier-bot/actions/workflows/ci.yml)

Telegram-бот для автоматических напоминаний о днях рождения с современным интерфейсом и гибкими настройками.

## Особенности

- Умное текстовое добавление — имя, тег и дата разбираются из одного сообщения на естественном языке (например, `Иван 15.08.1990` или `Маша 3 августа`)
- Интерактивный UI — список, редактирование, выбор даты и удаление контактов через inline-кнопки с пагинацией (по 8 контактов на странице)
- Даты без года рождения — в списке такие записи показываются в формате `ДД.ММ` без возраста
- Импорт контакта из адресной книги Telegram в один клик
- Автоматическая привязка `@username` для упоминаний в уведомлениях
- Гибкие уведомления: за месяц, неделю, 3 дня, накануне или в день события в выбранное время, за 30 и 5 минут до наступления, а также ровно в полночь
- Сортировка списка по имени или по дате ближайшего дня рождения
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

- **📅 Мой список** — интерактивное меню просмотра контактов с постраничной навигацией, быстрым переименованием, изменением даты или удалением
- **➕ Добавить** — добавление вручную, через контакт из Telegram или пошаговый inline-календарь
- **🔥 Ближайшие** — именинники в следующие 30 дней
- **⚙️ Настройки** — время ежедневных напоминаний и активные интервалы (с быстрыми пресетами)
- **💾 Бэкап** — экспорт списка в JSON или восстановление из файла

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

## Лицензия

[MIT](LICENSE) — Copyright (c) 2026 [renkagod](https://github.com/renkagod).

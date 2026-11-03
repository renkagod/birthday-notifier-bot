# Birthday Notifier Bot

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![CI](https://github.com/renkagod/birthday-notifier-bot/actions/workflows/ci.yml/badge.svg)](https://github.com/renkagod/birthday-notifier-bot/actions/workflows/ci.yml)
[![Donate](https://img.shields.io/badge/Donate-crypto-ea4aaa?logo=githubsponsors&logoColor=white)](https://github.com/renkagod/.github/blob/main/DONATE.md)

Telegram-бот для автоматических напоминаний о днях рождения с современным интерфейсом и гибкими настройками.

## Особенности

- Чат и есть интерфейс — короткие rich-сообщения Telegram (Bot API 10.3) с кнопками прямо в тексте; нужна версия Telegram с поддержкой rich-сообщений
- Одна сводка вместо пачки уведомлений — в выбранное время приходит одно сообщение: кому сегодня, завтра, через неделю; `/start` показывает ту же сводку на ближайший месяц
- Добавление одним сообщением — `Маша 3 августа` или `Иван @ivan 15.08.1990` сохраняется сразу, ошибку можно отменить
- Поиск по имени — напишите имя или его часть, и бот пришлёт карточку человека
- Правка ответом — ответьте на карточку датой, новым именем или `@тегом`; изменение можно вернуть
- Заметки к человеку — идея подарка или что угодно ещё; заметка видна в карточке и приходит вместе с напоминанием
- Удаление без лишних вопросов, с кнопкой «Вернуть»
- Напоминания за месяц, неделю, 3 дня, за день и в сам день, а также за любое число дней: ответьте на «Напоминания» числом, например `14`; ночные — ровно в полночь и за 30 или 5 минут до неё
- Даты без года рождения — возраст для таких записей не считается
- Выбор человека из контактов Telegram — имя и `@username` подставляются сами
- Резервная копия в JSON и загрузка обратно
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

- **Сводка** — ближайшие дни рождения и ссылки «Все», «Напоминания», «Помощь»
- **Любой текст** — `Имя дата` добавляет человека, просто имя находит его
- **Карточка** — дата и возраст; чтобы исправить, ответьте на неё: `13.11.1988`, `Дмитрий`, `@dima` или `без тега`; заметку добавляет кнопка «Добавить заметку» или ответ `заметка: книга про горы`
- **Напоминания** — нажатие на строку включает или выключает её; ответ `08:30` меняет время, ответ `14` добавляет напоминание за 14 дней
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

import asyncio
import calendar
import datetime
import io
import json
import logging
import os
import re
import sqlite3

from aiogram import Bot, Dispatcher, F
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    BotCommand,
    BufferedInputFile,
    CallbackQuery,
    DisabledButton,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InputRichMessage,
    KeyboardButton,
    KeyboardButtonRequestUsers,
    Message,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
)
from aiogram.utils.callback_answer import CallbackAnswer, CallbackAnswerMiddleware
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from dotenv import load_dotenv

from bot import screens
from bot.database import (
    add_birthday,
    delete_birthday_by_id,
    find_birthday_id,
    get_birthdays_for_user,
    get_user_birthday,
    get_user_settings,
    init_db,
    update_birthday_date_by_id,
    update_birthday_info_by_id,
    update_user_settings,
)
from bot.dates import (
    YEARLESS_YEAR,
    extract_name_and_date,
    normalize_notify_time,
    parse_birth_date,
    parse_natural_date,
    sort_by_name,
    sort_by_upcoming,
)
from bot.scheduler import check_birthdays

load_dotenv()

TOKEN = os.getenv("BOT_TOKEN")
if not TOKEN:
    raise ValueError("No BOT_TOKEN provided in .env file")

# No default parse_mode: every screen is a rich message with Markdown content.
bot = Bot(token=TOKEN)
dp = Dispatcher()
# Answers every callback query after its handler, so buttons never hang in "loading".
dp.callback_query.middleware(CallbackAnswerMiddleware())

ITEMS_PER_PAGE = 8
CANCEL_TEXT = "❌ Отмена"
TIME_PRESETS = ["07:00", "08:00", "09:00", "10:00", "12:00", "18:00", "20:00", "21:00"]
MONTHS_SHORT = ["Янв", "Фев", "Мар", "Апр", "Май", "Июн", "Июл", "Авг", "Сен", "Окт", "Ноя", "Дек"]
TAG_RE = re.compile(r"@\w{1,32}")

BOT_COMMANDS = [
    BotCommand(command="start", description="Главное меню"),
    BotCommand(command="add", description="Добавить день рождения"),
    BotCommand(command="list", description="Мой список"),
    BotCommand(command="upcoming", description="Ближайшие дни рождения"),
    BotCommand(command="settings", description="Настройки уведомлений"),
    BotCommand(command="help", description="Как пользоваться"),
    BotCommand(command="cancel", description="Отменить действие"),
]


class AppStates(StatesGroup):
    waiting_for_name = State()
    waiting_for_decade = State()
    waiting_for_year = State()
    waiting_for_month = State()
    waiting_for_day = State()
    waiting_for_edit_data = State()
    waiting_for_edit_date = State()
    waiting_for_notify_time = State()
    waiting_for_import = State()
    waiting_for_confirm_add = State()
    waiting_for_contact_date = State()


# --- Rendering helpers ---

def btn(text, data=None, *, url=None, style=None):
    return InlineKeyboardButton(text=text, callback_data=data, url=url, style=style)


def label(text):
    """Non-clickable button used as a caption inside keyboards."""
    return InlineKeyboardButton(text=text, disabled=DisabledButton())


def kb(*rows):
    return InlineKeyboardMarkup(inline_keyboard=[list(row) for row in rows if row])


async def show(target: Message | CallbackQuery, text: str, markup=None) -> None:
    """Edit the screen a button was pressed on, or send a new rich message."""
    rich = InputRichMessage(markdown=text)
    if isinstance(target, CallbackQuery):
        if isinstance(target.message, Message):
            try:
                await target.message.edit_text(rich_message=rich, reply_markup=markup)
                return
            except TelegramBadRequest as e:
                if "not modified" in str(e):
                    return
                # Old plain-text screens or documents can't become rich messages: send anew.
                logging.debug("Falling back to a new message: %s", e)
        await bot.send_rich_message(target.from_user.id, rich, reply_markup=markup)
    else:
        await target.answer_rich(rich, reply_markup=markup)


def now_today():
    return datetime.datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)


def parse_date_input(text: str) -> tuple[int, int, int | None] | None:
    date_tuple = parse_natural_date(text)
    if not date_tuple:
        _, _, date_tuple = extract_name_and_date(text)
    return date_tuple


def date_error(date_tuple) -> str | None:
    if date_tuple is None:
        return "❌ Не получилось распознать дату. Попробуйте `15.08.1990`, `22.10` или `3 августа`."
    year = date_tuple[2]
    if year is not None and not 1900 <= year <= datetime.date.today().year:
        return f"❌ Год {year} выглядит странно. Проверьте дату или укажите её без года."
    return None


def name_error(name: str) -> str | None:
    if not name:
        return "❌ Не вижу имени. Напишите, например, `Маша 3 августа`."
    if len(name) > screens.MAX_NAME_LENGTH:
        return f"❌ Имя слишком длинное: не больше {screens.MAX_NAME_LENGTH} символов."
    return None


# --- Keyboards ---

def main_menu():
    return kb(
        [btn("➕ Добавить", "menu_add", style="primary"), btn("📅 Мой список", "menu_list")],
        [btn("🔥 Ближайшие", "menu_upcoming"), btn("⚙️ Настройки", "menu_settings")],
        [btn("💾 Бэкап", "menu_backup"), btn("❓ Помощь", "menu_help")],
    )


def back_to_menu_kb():
    return kb([btn("🏠 Меню", "menu_start")])


def cancel_kb(data="menu_start"):
    return kb([btn("❌ Отмена", data)])


def get_sorted_birthdays(user_id, sort_by="name"):
    birthdays = get_birthdays_for_user(user_id)
    if sort_by == "name":
        return sort_by_name(birthdays)
    return sort_by_upcoming(birthdays, now_today())


def list_screen(user_id, page=0, sort_by="name"):
    birthdays = get_sorted_birthdays(user_id, sort_by)
    if not birthdays:
        return screens.render_empty_list(), kb(
            [btn("➕ Добавить", "menu_add", style="primary"), btn("🏠 Меню", "menu_start")]
        )

    total_pages = (len(birthdays) + ITEMS_PER_PAGE - 1) // ITEMS_PER_PAGE
    page = max(0, min(page, total_pages - 1))
    page_items = birthdays[page * ITEMS_PER_PAGE:(page + 1) * ITEMS_PER_PAGE]
    text = screens.render_list(
        page_items, now=now_today(), sort_by=sort_by,
        page=page, total_pages=total_pages, total=len(birthdays),
    )

    rows = []
    for i in range(0, len(page_items), 2):
        rows.append([
            btn(f"👤 {name[:28]}", f"view_bday:{b_id}:{page}:{sort_by}")
            for b_id, name, _date, _tag in page_items[i:i + 2]
        ])
    if total_pages > 1:
        rows.append([
            btn("◀️", f"list_page:{page - 1}:{sort_by}") if page > 0 else label(" "),
            label(f"{page + 1} / {total_pages}"),
            btn("▶️", f"list_page:{page + 1}:{sort_by}") if page < total_pages - 1 else label(" "),
        ])
    next_sort = "date" if sort_by == "name" else "name"
    sort_label = "🔄 По дате" if sort_by == "name" else "🔄 По имени"
    rows.append([
        btn(sort_label, f"list_page:0:{next_sort}"),
        btn("➕", "menu_add"),
        btn("🏠 Меню", "menu_start"),
    ])
    return text, kb(*rows)


def card_kb(b_id, page, sort_by, tag=None, after_add=False):
    rows = [
        [btn("✏️ Имя и тег", f"edit_info:{b_id}:{page}:{sort_by}"),
         btn("📅 Дата", f"edit_date:{b_id}:{page}:{sort_by}")],
    ]
    if tag:
        rows.append([btn("💬 Написать", url=f"https://t.me/{tag.lstrip('@')}")])
    if after_add:
        rows.append([btn("➕ Добавить ещё", "menu_add", style="primary")])
    rows.append([btn("🗑 Удалить", f"delete_confirm:{b_id}:{page}:{sort_by}", style="danger")])
    rows.append([btn("📅 К списку", f"list_page:{page}:{sort_by}"), btn("🏠 Меню", "menu_start")])
    return kb(*rows)


async def show_card(target, b_id, page=0, sort_by="name", notice=None, after_add=False):
    row = get_user_birthday(b_id, target.from_user.id)
    if not row:
        text, markup = list_screen(target.from_user.id, page, sort_by)
        return await show(target, text, markup)
    _, _, name, b_date, tag = row
    await show(
        target,
        screens.render_card(name, b_date, tag, now_today(), notice=notice),
        card_kb(b_id, page, sort_by, tag, after_add=after_add),
    )


async def show_home(target, notice=None):
    user_id = target.from_user.id
    settings = get_user_settings(user_id)
    text = screens.render_home(
        get_birthdays_for_user(user_id), now_today(), settings["notify_time"],
        notice=notice, reminders_on=bool(settings["intervals"]),
    )
    await show(target, text, main_menu())


def parse_nav(data: str) -> tuple[int, int, str]:
    _, b_id, page, sort_by = data.split(":")
    return int(b_id), int(page), sort_by


# --- Commands ---

@dp.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    await show_home(message)


@dp.message(Command("help"))
async def cmd_help(message: Message):
    await show(message, screens.render_help(), back_to_menu_kb())


@dp.message(Command("add"))
async def cmd_add(message: Message, state: FSMContext):
    await state.clear()
    await show(message, screens.render_add_menu(), add_menu_kb())


@dp.message(Command("list"))
async def cmd_list(message: Message, state: FSMContext):
    await state.clear()
    await show(message, *list_screen(message.from_user.id, 0, "name"))


@dp.message(Command("upcoming"))
async def cmd_upcoming(message: Message, state: FSMContext):
    await state.clear()
    await show(message, *list_screen(message.from_user.id, 0, "date"))


@dp.message(Command("settings"))
async def cmd_settings(message: Message, state: FSMContext):
    await state.clear()
    await show(message, *settings_screen(message.from_user.id))


@dp.message(Command("cancel"))
@dp.message(F.text == CANCEL_TEXT)
async def cmd_cancel(message: Message, state: FSMContext):
    had_state = await state.get_state() is not None
    await state.clear()
    await message.answer_rich(
        InputRichMessage(markdown="❌ Действие отменено." if had_state else "Отменять нечего."),
        reply_markup=ReplyKeyboardRemove(),
    )
    await show_home(message)


@dp.callback_query(F.data == "menu_start")
async def back_to_menu(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await show_home(callback)


@dp.callback_query(F.data == "menu_help")
async def menu_help(callback: CallbackQuery):
    await show(callback, screens.render_help(), back_to_menu_kb())


# --- SETTINGS ---

def settings_screen(user_id, notice=None):
    s = get_user_settings(user_id)
    return screens.render_settings(s["notify_time"], s["intervals"], notice=notice), kb(
        [btn("⏰ Время", "set_time"), btn("🔔 Когда напоминать", "set_intervals")],
        [btn("🏠 Меню", "menu_start")],
    )


def intervals_screen(user_id):
    s = get_user_settings(user_id)
    current = s["intervals"]

    def toggle(value, text):
        return btn(f"{'✅' if value in current else '▫️'} {text}", f"toggle_int:{value}")

    timed = [toggle(v, t) for v, t in screens.TIMED_INTERVALS]
    exact = [toggle(v, t) for v, t in screens.EXACT_INTERVALS]
    return screens.render_intervals(current, s["notify_time"]), kb(
        [label(f"В {s['notify_time']}")],
        timed[0:2], timed[2:4], timed[4:],
        [label("Ровно к началу дня")],
        *[[b] for b in exact],
        [btn("🔔 Всё", "preset_int:all"), btn("⭐ Стандарт", "preset_int:default"),
         btn("🔕 Ничего", "preset_int:none")],
        [btn("🔙 Настройки", "menu_settings")],
    )


@dp.callback_query(F.data == "menu_settings")
async def settings_main(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await show(callback, *settings_screen(callback.from_user.id))


@dp.callback_query(F.data == "set_time")
async def process_set_time_start(callback: CallbackQuery, state: FSMContext):
    await state.set_state(AppStates.waiting_for_notify_time)
    current = get_user_settings(callback.from_user.id)["notify_time"]
    presets = [
        btn(f"• {t} •" if t == current else t, f"time_preset:{t}") for t in TIME_PRESETS
    ]
    await show(
        callback,
        screens.render_time_prompt(current),
        kb(presets[:4], presets[4:], [btn("🔙 Настройки", "menu_settings")]),
    )


@dp.callback_query(F.data.startswith("time_preset:"))
async def process_time_preset(callback: CallbackQuery, state: FSMContext, callback_answer: CallbackAnswer):
    time_str = callback.data.split(":", 1)[1]
    if not normalize_notify_time(time_str):
        return
    update_user_settings(callback.from_user.id, notify_time=time_str)
    await state.clear()
    callback_answer.text = f"⏰ Напоминаю в {time_str}"
    await show(callback, *settings_screen(callback.from_user.id, notice=f"✅ Время напоминаний: **{time_str}**"))


@dp.message(AppStates.waiting_for_notify_time, F.text)
async def process_notify_time(message: Message, state: FSMContext):
    time_str = normalize_notify_time(message.text)
    if not time_str:
        return await show(
            message,
            "❌ Не понял время. Пришлите его в формате `ЧЧ:ММ`, например `09:00` или `18:30`.",
            cancel_kb("menu_settings"),
        )
    update_user_settings(message.from_user.id, notify_time=time_str)
    await state.clear()
    await show(message, *settings_screen(message.from_user.id, notice=f"✅ Время напоминаний: **{time_str}**"))


@dp.callback_query(F.data == "set_intervals")
async def set_intervals_menu(callback: CallbackQuery):
    await show(callback, *intervals_screen(callback.from_user.id))


@dp.callback_query(F.data.startswith("toggle_int:"))
async def process_toggle_int(callback: CallbackQuery, callback_answer: CallbackAnswer):
    val = float(callback.data.split(":")[1])
    if val not in screens.INTERVAL_LABELS:
        return
    current = get_user_settings(callback.from_user.id)["intervals"]
    if val in current:
        current.remove(val)
        callback_answer.text = f"🔕 Выключено: {screens.INTERVAL_LABELS[val]}"
    else:
        current.append(val)
        callback_answer.text = f"🔔 Включено: {screens.INTERVAL_LABELS[val]}"
    update_user_settings(callback.from_user.id, intervals=current)
    await show(callback, *intervals_screen(callback.from_user.id))


@dp.callback_query(F.data.startswith("preset_int:"))
async def process_preset_int(callback: CallbackQuery, callback_answer: CallbackAnswer):
    preset = callback.data.split(":")[1]
    if preset == "all":
        intervals = list(screens.ALL_INTERVALS)
        callback_answer.text = "🔔 Включены все напоминания"
    elif preset == "none":
        intervals = []
        callback_answer.text = "🔕 Все напоминания выключены"
    else:
        intervals = list(screens.STANDARD_INTERVALS)
        callback_answer.text = "⭐ Стандарт: за день, в день рождения и в полночь"
    update_user_settings(callback.from_user.id, intervals=intervals)
    await show(callback, *intervals_screen(callback.from_user.id))


# --- BACKUP ---

def normalize_import_item(item) -> tuple[str, str, str | None] | None:
    """(name, stored date, tag) for a valid backup entry, else None."""
    if not isinstance(item, dict):
        return None
    name = " ".join(str(item.get("name") or "").split())
    raw_date = str(item.get("date") or "").strip()
    if name_error(name) or not raw_date:
        return None
    if re.fullmatch(r"\d{2}\.\d{2}", raw_date):
        raw_date = f"{raw_date}.{YEARLESS_YEAR}"
    try:
        parse_birth_date(raw_date)
    except ValueError:
        return None
    tag = item.get("tag")
    tag = tag if isinstance(tag, str) and TAG_RE.fullmatch(tag) else None
    return name, raw_date, tag


@dp.callback_query(F.data == "menu_backup")
async def backup_menu(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    total = len(get_birthdays_for_user(callback.from_user.id))
    await show(callback, screens.render_backup(total), kb(
        [btn("📤 Экспорт", "backup_export"), btn("📥 Импорт", "backup_import")],
        [btn("🏠 Меню", "menu_start")],
    ))


@dp.callback_query(F.data == "backup_export")
async def backup_export(callback: CallbackQuery, callback_answer: CallbackAnswer):
    birthdays = get_birthdays_for_user(callback.from_user.id)
    if not birthdays:
        callback_answer.text = "Список пуст, экспортировать нечего"
        callback_answer.show_alert = True
        return
    user_data = []
    for _id, name, b_date, tag in sort_by_name(birthdays):
        date_out = b_date[:5] if b_date.endswith(f".{YEARLESS_YEAR}") else b_date
        user_data.append({"name": name, "date": date_out, "tag": tag})
    json_data = json.dumps(user_data, ensure_ascii=False, indent=2)
    stamp = datetime.date.today().isoformat()
    file = BufferedInputFile(json_data.encode("utf-8"), filename=f"birthdays_{stamp}.json")
    await callback.message.answer_document(file, caption=f"💾 Бэкап: {len(user_data)} записей")
    callback_answer.text = "Файл отправлен"


@dp.callback_query(F.data == "backup_import")
async def backup_import_start(callback: CallbackQuery, state: FSMContext):
    await state.set_state(AppStates.waiting_for_import)
    await show(callback, screens.render_import_prompt(), cancel_kb("menu_backup"))


@dp.message(AppStates.waiting_for_import, F.document)
async def process_import(message: Message, state: FSMContext):
    if message.document.file_size and message.document.file_size > 1024 * 1024:
        return await show(message, "❌ Файл больше 1 МБ. Это точно бэкап?", cancel_kb("menu_backup"))
    content = await bot.download(message.document, io.BytesIO())
    try:
        data = json.loads(content.getvalue().decode("utf-8"))
        if not isinstance(data, list):
            raise ValueError
    except (UnicodeDecodeError, ValueError):
        return await show(
            message,
            "❌ Не похоже на файл бэкапа: ожидаю JSON-список записей. Пришлите другой файл.",
            cancel_kb("menu_backup"),
        )

    user_id = message.from_user.id
    added = updated = skipped = 0
    for item in data:
        parsed = normalize_import_item(item)
        if not parsed:
            skipped += 1
            continue
        name, b_date, tag = parsed
        if find_birthday_id(user_id, name) is None:
            added += 1
        else:
            updated += 1
        add_birthday(user_id, name, b_date, tag)
    await state.clear()
    await show(message, screens.render_import_result(added, updated, skipped), kb(
        [btn("📅 Мой список", "menu_list"), btn("🏠 Меню", "menu_start")],
    ))


# --- LIST / CARD / EDIT / DELETE ---

@dp.callback_query(F.data == "menu_upcoming")
async def menu_upcoming_birthdays(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await show(callback, *list_screen(callback.from_user.id, 0, "date"))


@dp.callback_query(F.data.startswith("menu_list"))
async def menu_list_birthdays(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    sort_by = callback.data.split(":")[1] if ":" in callback.data else "name"
    await show(callback, *list_screen(callback.from_user.id, 0, sort_by))


@dp.callback_query(F.data.startswith("list_page:"))
async def process_list_page(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    _, page, sort_by = callback.data.split(":")
    await show(callback, *list_screen(callback.from_user.id, int(page), sort_by))


@dp.callback_query(F.data.startswith("view_bday:"))
async def view_birthday_details(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    b_id, page, sort_by = parse_nav(callback.data)
    await show_card(callback, b_id, page, sort_by)


@dp.callback_query(F.data.startswith("delete_confirm:"))
async def process_delete_confirm(callback: CallbackQuery):
    b_id, page, sort_by = parse_nav(callback.data)
    row = get_user_birthday(b_id, callback.from_user.id)
    if not row:
        return await show(callback, *list_screen(callback.from_user.id, page, sort_by))
    await show(callback, screens.render_delete_confirm(row[2]), kb([
        btn("🗑 Да, удалить", f"delete_execute:{b_id}:{page}:{sort_by}", style="danger"),
        btn("Оставить", f"view_bday:{b_id}:{page}:{sort_by}"),
    ]))


@dp.callback_query(F.data.startswith("delete_execute:"))
async def process_delete_execute(callback: CallbackQuery, callback_answer: CallbackAnswer):
    b_id, page, sort_by = parse_nav(callback.data)
    row = get_user_birthday(b_id, callback.from_user.id)
    if row:
        delete_birthday_by_id(b_id)
        callback_answer.text = f"🗑 Удалено: {row[2]}"
    await show(callback, *list_screen(callback.from_user.id, page, sort_by))


@dp.callback_query(F.data.startswith("edit_info:"))
async def process_edit_info_start(callback: CallbackQuery, state: FSMContext):
    b_id, page, sort_by = parse_nav(callback.data)
    row = get_user_birthday(b_id, callback.from_user.id)
    if not row:
        return await show(callback, *list_screen(callback.from_user.id, page, sort_by))
    await state.set_state(AppStates.waiting_for_edit_data)
    await state.update_data(edit_b_id=b_id, edit_page=page, edit_sort_by=sort_by)
    await show(
        callback,
        screens.render_edit_info_prompt(row[2], row[4]),
        cancel_kb(f"view_bday:{b_id}:{page}:{sort_by}"),
    )


@dp.message(AppStates.waiting_for_edit_data, F.text)
async def process_edit_data(message: Message, state: FSMContext):
    text = message.text.strip()
    match = TAG_RE.search(text)
    new_tag = match.group(0) if match else None
    new_name = " ".join(TAG_RE.sub("", text).split())
    data = await state.get_data()
    back = cancel_kb(f"view_bday:{data['edit_b_id']}:{data['edit_page']}:{data['edit_sort_by']}")

    error = name_error(new_name)
    if error:
        return await show(message, error, back)
    if not get_user_birthday(data["edit_b_id"], message.from_user.id):
        await state.clear()
        return await show_home(message)
    try:
        update_birthday_info_by_id(data["edit_b_id"], new_name, new_tag)
    except sqlite3.IntegrityError:
        return await show(
            message, f"❌ **{screens.md(new_name)}** уже есть в списке. Введите другое имя.", back
        )
    await state.clear()
    await show_card(message, data["edit_b_id"], data["edit_page"], data["edit_sort_by"], notice="✅ Сохранено")


@dp.callback_query(F.data.startswith("edit_date:"))
async def process_edit_date_start(callback: CallbackQuery, state: FSMContext):
    b_id, page, sort_by = parse_nav(callback.data)
    row = get_user_birthday(b_id, callback.from_user.id)
    if not row:
        return await show(callback, *list_screen(callback.from_user.id, page, sort_by))
    await state.set_state(AppStates.waiting_for_edit_date)
    await state.update_data(edit_b_id=b_id, edit_page=page, edit_sort_by=sort_by, name=row[2])
    await show(callback, screens.render_edit_date_prompt(row[2], row[3]), kb(
        [btn("📅 Выбрать в календаре", "edit_date_calendar", style="primary")],
        [btn("❌ Отмена", f"view_bday:{b_id}:{page}:{sort_by}")],
    ))


@dp.message(AppStates.waiting_for_edit_date, F.text)
async def process_edit_date_text(message: Message, state: FSMContext):
    data = await state.get_data()
    date_tuple = parse_date_input(message.text.strip())
    error = date_error(date_tuple)
    if error:
        return await show(message, error, kb(
            [btn("📅 Выбрать в календаре", "edit_date_calendar")],
            [btn("❌ Отмена", f"view_bday:{data['edit_b_id']}:{data['edit_page']}:{data['edit_sort_by']}")],
        ))
    day, month, year = date_tuple
    if get_user_birthday(data["edit_b_id"], message.from_user.id):
        update_birthday_date_by_id(data["edit_b_id"], f"{day:02d}.{month:02d}.{year or YEARLESS_YEAR}")
    await state.clear()
    await show_card(message, data["edit_b_id"], data["edit_page"], data["edit_sort_by"], notice="✅ Дата обновлена")


@dp.callback_query(F.data == "edit_date_calendar")
async def process_edit_date_calendar(callback: CallbackQuery, state: FSMContext):
    await state.update_data(calendar_mode="edit")
    await show_decade_picker(callback, state)


# --- ADD BIRTHDAY FLOW ---

def add_menu_kb():
    return kb(
        [btn("📝 Ввести вручную", "add_manual_name", style="primary")],
        [btn("👤 Из контактов Telegram", "add_choose_contact")],
        [btn("🏠 Меню", "menu_start")],
    )


def get_decade_keyboard():
    rows = []
    start = (datetime.datetime.now().year // 10) * 10
    for d in range(start, start - 80, -20):
        rows.append([btn(f"{i}-е", f"set_decade:{i}") for i in range(d, d - 20, -10)])
    rows.append([btn("🤷 Год не знаю", "skip_year")])
    rows.append([btn("❌ Отмена", "picker_cancel")])
    return kb(*rows)


def get_year_in_decade_keyboard(decade):
    this_year = datetime.date.today().year
    years = [btn(str(y), f"set_year:{y}") for y in range(decade + 9, decade - 1, -1) if y <= this_year]
    return kb(*[years[i:i + 5] for i in range(0, len(years), 5)], [btn("🔙 Назад", "back_to_decade")])


def get_month_keyboard(is_yearless=False):
    rows = [[btn(MONTHS_SHORT[m], f"set_month:{m + 1}") for m in range(i, i + 3)] for i in range(0, 12, 3)]
    rows.append([btn("🔙 Назад", "back_to_decade" if is_yearless else "back_to_year")])
    return kb(*rows)


def get_day_keyboard(year, month):
    rows = [[label(d) for d in ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]]]
    for week in calendar.monthcalendar(year, month):
        rows.append([btn(str(day), f"set_day:{day}") if day else label(" ") for day in week])
    rows.append([btn("🔙 Назад", "back_to_month")])
    return kb(*rows)


async def show_decade_picker(target, state: FSMContext):
    await state.set_state(AppStates.waiting_for_decade)
    data = await state.get_data()
    await show(target, screens.render_picker(data.get("name"), "Выберите десятилетие рождения"), get_decade_keyboard())


async def ask_date(target, state: FSMContext, name: str, tag: str | None):
    """Name is known: ask for the date as text or via the calendar."""
    await state.set_state(AppStates.waiting_for_contact_date)
    await state.update_data(name=name, tg_username=tag, calendar_mode="add")
    await show(target, screens.render_contact_date_prompt(name, tag), kb(
        [btn("📅 Выбрать в календаре", "add_contact_calendar", style="primary")],
        [btn("❌ Отмена", "menu_start")],
    ))


async def ask_confirm(target, state: FSMContext, name, tag, day, month, year):
    exists = find_birthday_id(target.from_user.id, name) is not None
    await state.set_state(AppStates.waiting_for_confirm_add)
    await state.update_data(
        name=name, tg_username=tag, day=day, month=month,
        year=year if year is not None else YEARLESS_YEAR, calendar_mode="add",
    )
    await show(
        target,
        screens.render_confirm_add(name, tag, day, month, year, now_today(), exists),
        kb(
            [btn("✅ Сохранить", "confirm_add_yes", style="success"),
             btn("📅 Другая дата", "confirm_add_manual")],
            [btn("❌ Отмена", "menu_start")],
        ),
    )


async def save_and_show(target, state: FSMContext, name, tag, day, month, year):
    existed = find_birthday_id(target.from_user.id, name) is not None
    b_id = add_birthday(target.from_user.id, name, f"{day:02d}.{month:02d}.{year}", tag)
    await state.clear()
    notice = "✅ Запись обновлена" if existed else "✅ Добавлено в список"
    await show_card(target, b_id, notice=notice, after_add=True)


@dp.callback_query(F.data == "menu_add")
async def menu_add_options(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await show(callback, screens.render_add_menu(), add_menu_kb())


@dp.callback_query(F.data == "add_manual_name")
async def add_manual_name_start(callback: CallbackQuery, state: FSMContext):
    await state.set_state(AppStates.waiting_for_name)
    await show(callback, screens.render_name_prompt(), cancel_kb())


@dp.callback_query(F.data == "add_choose_contact")
async def add_choose_contact_start(callback: CallbackQuery):
    request = KeyboardButtonRequestUsers(
        request_id=1, max_quantity=1, user_is_bot=False, request_name=True, request_username=True,
    )
    markup = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="👤 Выбрать человека", request_users=request)],
                  [KeyboardButton(text=CANCEL_TEXT)]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )
    await callback.message.answer_rich(
        InputRichMessage(markdown=(
            "## 👤 Выбор из Telegram\n\n"
            "Нажмите **👤 Выбрать человека** внизу и выберите чат. "
            "Имя и @тег я подставлю сам, останется только дата."
        )),
        reply_markup=markup,
    )


@dp.message(F.users_shared)
async def process_shared_user(message: Message, state: FSMContext):
    shared = message.users_shared.users[0]
    name = " ".join(filter(None, [shared.first_name, shared.last_name]))
    tag = f"@{shared.username}" if shared.username else None
    await message.answer_rich(
        InputRichMessage(markdown=f"👤 Выбран: **{screens.md(name or 'без имени')}**"),
        reply_markup=ReplyKeyboardRemove(),
    )
    if name_error(name):
        await state.set_state(AppStates.waiting_for_name)
        await state.update_data(tg_username=tag)
        return await show(message, screens.render_name_prompt(prefilled_tag=tag), cancel_kb())
    await ask_date(message, state, name, tag)


@dp.message(F.contact)
async def process_contact(message: Message, state: FSMContext):
    name = " ".join(filter(None, [message.contact.first_name, message.contact.last_name]))
    await message.answer_rich(
        InputRichMessage(markdown="👤 Контакт получен."), reply_markup=ReplyKeyboardRemove()
    )
    if name_error(name):
        await state.set_state(AppStates.waiting_for_name)
        return await show(message, screens.render_name_prompt(), cancel_kb())
    await ask_date(message, state, name, None)


@dp.callback_query(F.data == "add_contact_calendar")
async def process_add_contact_calendar(callback: CallbackQuery, state: FSMContext):
    await show_decade_picker(callback, state)


@dp.message(AppStates.waiting_for_contact_date, F.text)
async def process_contact_date_text(message: Message, state: FSMContext):
    data = await state.get_data()
    date_tuple = parse_date_input(message.text.strip())
    error = date_error(date_tuple)
    if error:
        return await show(message, error, kb(
            [btn("📅 Выбрать в календаре", "add_contact_calendar")], [btn("❌ Отмена", "menu_start")],
        ))
    day, month, year = date_tuple
    await save_and_show(message, state, data["name"], data.get("tg_username"), day, month, year or YEARLESS_YEAR)


@dp.message(AppStates.waiting_for_name, F.text)
async def process_name(message: Message, state: FSMContext):
    name, username, date_tuple = extract_name_and_date(message.text.strip())
    error = name_error(name)
    if error:
        return await show(message, error, cancel_kb())
    username = username or (await state.get_data()).get("tg_username")
    if date_tuple:
        error = date_error(date_tuple)
        if error:
            return await show(message, error, cancel_kb())
        return await ask_confirm(message, state, name, username, *date_tuple)
    await state.update_data(name=name, tg_username=username, calendar_mode="add")
    await show_decade_picker(message, state)


@dp.callback_query(F.data == "confirm_add_yes")
async def process_confirm_add_yes(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    if not {"name", "day", "month", "year"} <= data.keys():
        return await show_home(callback, notice="⌛ Этот шаг устарел, начните заново.")
    await save_and_show(callback, state, data["name"], data.get("tg_username"), data["day"], data["month"], data["year"])


@dp.callback_query(F.data == "confirm_add_manual")
async def process_confirm_add_manual(callback: CallbackQuery, state: FSMContext):
    await show_decade_picker(callback, state)


@dp.callback_query(F.data == "picker_cancel")
async def process_picker_cancel(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    await state.clear()
    if data.get("calendar_mode") == "edit" and "edit_b_id" in data:
        return await show_card(callback, data["edit_b_id"], data.get("edit_page", 0), data.get("edit_sort_by", "name"))
    await show_home(callback)


@dp.callback_query(F.data == "skip_year")
async def process_skip_year(callback: CallbackQuery, state: FSMContext):
    await state.update_data(year=YEARLESS_YEAR)
    data = await state.get_data()
    await show(
        callback,
        screens.render_picker(data.get("name"), "Выберите месяц", year=YEARLESS_YEAR),
        get_month_keyboard(is_yearless=True),
    )


@dp.callback_query(F.data.startswith("set_decade:"))
async def process_decade(callback: CallbackQuery, state: FSMContext):
    decade = int(callback.data.split(":")[1])
    await state.update_data(decade=decade)
    data = await state.get_data()
    await show(callback, screens.render_picker(data.get("name"), "Выберите год"), get_year_in_decade_keyboard(decade))


@dp.callback_query(F.data.startswith("set_year:"))
async def process_year(callback: CallbackQuery, state: FSMContext):
    year = int(callback.data.split(":")[1])
    await state.update_data(year=year)
    data = await state.get_data()
    await show(callback, screens.render_picker(data.get("name"), "Выберите месяц", year=year), get_month_keyboard())


@dp.callback_query(F.data.startswith("set_month:"))
async def process_month(callback: CallbackQuery, state: FSMContext):
    month = int(callback.data.split(":")[1])
    data = await state.get_data()
    if "year" not in data:
        return await show_home(callback, notice="⌛ Этот шаг устарел, начните заново.")
    await state.update_data(month=month)
    await show(
        callback,
        screens.render_picker(data.get("name"), "Выберите день", year=data["year"], month=month),
        get_day_keyboard(data["year"], month),
    )


@dp.callback_query(F.data.startswith("set_day:"))
async def process_day(callback: CallbackQuery, state: FSMContext):
    day = int(callback.data.split(":")[1])
    data = await state.get_data()
    if not {"year", "month"} <= data.keys():
        return await show_home(callback, notice="⌛ Этот шаг устарел, начните заново.")
    year, month = data["year"], data["month"]

    if data.get("calendar_mode") == "edit":
        await state.clear()
        if get_user_birthday(data["edit_b_id"], callback.from_user.id):
            update_birthday_date_by_id(data["edit_b_id"], f"{day:02d}.{month:02d}.{year}")
        return await show_card(
            callback, data["edit_b_id"], data["edit_page"], data["edit_sort_by"], notice="✅ Дата обновлена"
        )
    if "name" not in data:
        return await show_home(callback, notice="⌛ Этот шаг устарел, начните заново.")
    await save_and_show(callback, state, data["name"], data.get("tg_username"), day, month, year)


@dp.callback_query(F.data == "back_to_decade")
async def back_to_decade_handler(callback: CallbackQuery, state: FSMContext):
    await show_decade_picker(callback, state)


@dp.callback_query(F.data == "back_to_year")
async def back_to_year_handler(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    if not data.get("decade"):
        return await show_decade_picker(callback, state)
    await show(
        callback,
        screens.render_picker(data.get("name"), "Выберите год"),
        get_year_in_decade_keyboard(data["decade"]),
    )


@dp.callback_query(F.data == "back_to_month")
async def back_to_month_handler(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    year = data.get("year")
    await show(
        callback,
        screens.render_picker(data.get("name"), "Выберите месяц", year=year),
        get_month_keyboard(is_yearless=year == YEARLESS_YEAR),
    )


@dp.callback_query(F.data == "ignore")
async def ignore_callback(callback: CallbackQuery):
    """Inert buttons on screens sent before the switch to disabled buttons."""


# --- Fallbacks (registered last) ---

@dp.message(StateFilter(None), F.text, ~F.text.startswith("/"))
async def quick_add(message: Message, state: FSMContext):
    """Free text outside any flow: try to read it as "Name @tag date"."""
    name, username, date_tuple = extract_name_and_date(message.text.strip())
    if name and not name_error(name) and date_tuple and not date_error(date_tuple):
        return await ask_confirm(message, state, name, username, *date_tuple)
    await show(
        message,
        "🤔 Не совсем понял. Чтобы добавить день рождения, напишите `Имя дата`, "
        "например `Маша 3 августа`, или выберите действие в меню.",
        main_menu(),
    )


@dp.message(StateFilter(None))
async def unknown_message(message: Message):
    if message.text:
        text = "Такой команды я не знаю. Вот что я умею:"
    else:
        text = "Я понимаю текст и кнопки. Вот что я умею:"
    await show(message, text, main_menu())


@dp.message()
async def unexpected_in_state(message: Message, state: FSMContext):
    current = await state.get_state()
    hint = "файл .json" if current == AppStates.waiting_for_import.state else "текстовое сообщение"
    await show(message, f"Сейчас я жду {hint}. Чтобы выйти, нажмите /cancel.", cancel_kb())


async def main():
    logging.basicConfig(level=logging.INFO)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    init_db()
    try:
        await bot.set_my_commands(BOT_COMMANDS)
    except Exception as e:
        logging.warning("Could not set bot commands: %s", e)
    scheduler = AsyncIOScheduler()
    scheduler.add_job(check_birthdays, "interval", minutes=1, args=[bot])
    scheduler.start()
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())

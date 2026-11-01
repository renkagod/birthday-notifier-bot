import asyncio
import datetime
import io
import json
import logging
import os
import re
import sqlite3
from collections import OrderedDict

from aiogram import Bot, Dispatcher, F
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    BotCommand,
    BufferedInputFile,
    CallbackQuery,
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
    find_message,
    get_birthdays_for_user,
    get_user_birthday,
    get_user_settings,
    init_db,
    remember_message,
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
)
from bot.scheduler import check_birthdays

load_dotenv()

TOKEN = os.getenv("BOT_TOKEN")
if not TOKEN:
    raise ValueError("No BOT_TOKEN provided in .env file")

# No default parse_mode: every message is a rich message with Markdown content and its
# controls inside the message (no inline keyboards).
bot = Bot(token=TOKEN)
dp = Dispatcher()
# Answers every callback query after its handler, so buttons never hang in "loading".
dp.callback_query.middleware(CallbackAnswerMiddleware())

CANCEL_TEXT = "Отмена"
LEGACY_CANCEL_TEXT = "❌ Отмена"
TAG_RE = re.compile(r"@\w{1,32}")
NO_TAG = {"без тега", "убрать тег", "-"}
DAYS_RE = re.compile(r"(?:за\s*)?(\d{1,3})(?:\s*(?:дн\w*|день))?")
STALE = "Этот шаг устарел, начните заново."

BOT_COMMANDS = [
    BotCommand(command="start", description="Сводка"),
    BotCommand(command="add", description="Добавить человека"),
    BotCommand(command="list", description="Все записи"),
    BotCommand(command="settings", description="Напоминания"),
    BotCommand(command="help", description="Как пользоваться"),
    BotCommand(command="cancel", description="Отменить действие"),
]

# Callbacks of earlier interfaces, so buttons on old messages keep working.
LEGACY_HOME = {"menu_start", "ignore"}
LEGACY_LIST = {"menu_list", "menu_list:name", "menu_list:date", "menu_upcoming"}
LEGACY_SETTINGS = {"menu_settings", "set_time", "set_intervals"}

# Last deleted and last edited records, so "Вернуть" works for a while (lost on restart).
UNDO_LIMIT = 500
deleted: OrderedDict[tuple[int, int], tuple[str, str, str | None]] = OrderedDict()
edited: OrderedDict[tuple[int, int], tuple[str, str, str | None]] = OrderedDict()


def keep(store: OrderedDict, key, value) -> None:
    store[key] = value
    store.move_to_end(key)
    while len(store) > UNDO_LIMIT:
        store.popitem(last=False)


class AppStates(StatesGroup):
    adding = State()          # waiting for "name [@tag] [date]"
    adding_date = State()     # name known, waiting for a date
    picking = State()         # calendar picker is open
    confirm_replace = State()
    editing_name = State()    # pre-reply interface, kept for in-flight sessions
    editing_date = State()
    settings = State()        # reminders open: a typed time or number of days applies
    importing = State()


# --- Rendering helpers ---

async def show(target: Message | CallbackQuery, text: str, *, new: bool = False) -> Message | None:
    """Edit the message a button was pressed on, or send a new rich message."""
    rich = InputRichMessage(markdown=text)
    if isinstance(target, CallbackQuery):
        if not new and isinstance(target.message, Message):
            try:
                # No reply_markup: also strips inline keyboards from pre-rich messages.
                await target.message.edit_text(rich_message=rich)
                return target.message
            except TelegramBadRequest as e:
                if "not modified" in str(e):
                    return target.message
                logging.debug("Falling back to a new message: %s", e)
        return await bot.send_rich_message(target.from_user.id, rich)
    return await target.answer_rich(rich)


def today():
    return datetime.datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)


def parse_date_input(text: str) -> tuple[int, int, int | None] | None:
    date_tuple = parse_natural_date(text)
    if not date_tuple:
        _, _, date_tuple = extract_name_and_date(text)
    return date_tuple


def date_error(date_tuple) -> str | None:
    if date_tuple is None:
        return "Не получилось распознать дату. Попробуйте `15.08.1990`, `22.10` или `3 августа`."
    year = date_tuple[2]
    if year is not None and not 1900 <= year <= datetime.date.today().year:
        return f"Год {year} выглядит странно. Проверьте дату или напишите её без года."
    return None


def name_error(name: str) -> str | None:
    if not name:
        return "Не вижу имени. Напишите, например, `Маша 3 августа`."
    if len(name) > screens.MAX_NAME_LENGTH:
        return f"Имя слишком длинное: не больше {screens.MAX_NAME_LENGTH} символов."
    return None


def stored_date(day: int, month: int, year: int | None) -> str:
    return f"{day:02d}.{month:02d}.{year or YEARLESS_YEAR}"


def cb_id(data: str) -> int:
    """Record id from "action:<id>" and legacy "action:<id>:<page>:<sort>"."""
    return int(data.split(":")[1])


def parse_days(text: str) -> int | None:
    match = DAYS_RE.fullmatch(text.strip().lower())
    if not match:
        return None
    days = int(match.group(1))
    return days if days <= screens.MAX_REMIND_DAYS else None


# --- Messages ---

async def show_brief(target, state: FSMContext, notice=None):
    await state.clear()
    user_id = target.from_user.id
    settings = get_user_settings(user_id)
    await show(target, screens.render_brief(
        get_birthdays_for_user(user_id), today(),
        notice=notice, reminders_on=bool(settings["intervals"]),
    ), new=True)


async def show_list(target, state: FSMContext, page=0, *, new=True):
    await state.clear()
    rows = get_birthdays_for_user(target.from_user.id)
    await show(target, screens.render_list(rows, today(), page), new=new)


async def show_person(target, state: FSMContext, b_id, *, notice=None, added=False, new=True):
    await state.clear()
    user_id = target.from_user.id
    row = get_user_birthday(b_id, user_id)
    if not row:
        return await show(target, screens.screen("Такой записи уже нет."), new=new)
    _, _, name, b_date, tag = row
    if added:
        text = screens.render_added(b_id, name, b_date, tag, today())
    else:
        text = screens.render_person(b_id, name, b_date, tag, today(), notice=notice)
    sent = await show(target, text, new=new)
    if sent:
        remember_message(user_id, sent.message_id, "person", b_id)


async def show_settings(target, state: FSMContext, notice=None, *, new=True):
    await state.set_state(AppStates.settings)
    user_id = target.from_user.id
    s = get_user_settings(user_id)
    sent = await show(target, screens.render_settings(s["notify_time"], s["intervals"], notice=notice), new=new)
    if sent:
        remember_message(user_id, sent.message_id, "settings")


async def save_new(target, state: FSMContext, name, tag, day, month, year, *, new=True):
    """Save a new person, or ask before replacing someone with the same name."""
    user_id = target.from_user.id
    existing = find_birthday_id(user_id, name)
    if existing is not None:
        old = get_user_birthday(existing, user_id)
        await state.set_state(AppStates.confirm_replace)
        await state.update_data(name=name, tg_username=tag, day=day, month=month, year=year)
        return await show(target, screens.render_replace_confirm(name, tag, day, month, year, old[3]), new=new)
    b_id = add_birthday(user_id, name, stored_date(day, month, year), tag)
    await show_person(target, state, b_id, added=True, new=new)


async def ask_date(target, state: FSMContext, name: str, tag: str | None, *, new=True):
    await state.set_state(AppStates.adding_date)
    await state.update_data(name=name, tg_username=tag, calendar_mode="add")
    await show(target, screens.render_date_prompt(name, tag), new=new)


async def handle_free_text(message: Message, state: FSMContext, text: str):
    """Text outside any flow: "Name @tag date" adds, a bare name searches."""
    name, tag, date_tuple = extract_name_and_date(text)
    if date_tuple:
        error = name_error(name) or date_error(date_tuple)
        if error:
            return await show(message, error)
        return await save_new(message, state, name, tag, *date_tuple)

    query = " ".join(text.split())
    if name_error(name):
        return await show(message, "Не понял. Напишите `Имя дата`, чтобы добавить человека, или имя, чтобы найти.")
    rows = get_birthdays_for_user(message.from_user.id)
    needle = query.lower()
    exact = [r for r in rows if r[1].lower() == needle]
    matches = [r for r in rows if needle in r[1].lower()]
    if len(exact) == 1 or len(matches) == 1:
        return await show_person(message, state, (exact or matches)[0][0])
    await state.clear()
    await state.update_data(name=name, tg_username=tag)
    await show(message, screens.render_search(query, matches, today()))


# --- Replies: edit a person or the reminders by answering their message ---

async def apply_person_reply(message: Message, state: FSMContext, b_id: int, text: str):
    user_id = message.from_user.id
    row = get_user_birthday(b_id, user_id)
    if not row:
        return await show(message, "Этой записи уже нет.")
    _, _, old_name, old_date, old_tag = row
    name, tag, date_tuple = old_name, old_tag, None

    if text.lower() in NO_TAG:
        tag = None
    elif TAG_RE.fullmatch(text):
        tag = text
    else:
        new_name, new_tag, date_tuple = extract_name_and_date(text)
        if date_tuple:
            error = date_error(date_tuple)
            if error:
                return await show(message, error)
        if new_name:
            error = name_error(new_name)
            if error:
                return await show(message, error)
            name = new_name
        tag = new_tag or tag
        if not date_tuple and not new_name and not new_tag:
            return await show(message, "Не понял. Ответьте датой `13.11.1988`, именем или тегом `@dima`.")

    try:
        update_birthday_info_by_id(b_id, name, tag)
    except sqlite3.IntegrityError:
        return await show(message, f"**{screens.md(name)}** уже есть в списке. Выберите другое имя.")
    if date_tuple:
        update_birthday_date_by_id(b_id, stored_date(*date_tuple))
    keep(edited, (user_id, b_id), (old_name, old_date, old_tag))
    await show_person(message, state, b_id,
                      notice=f"Исправил. {screens.link('Вернуть как было', f'revert:{b_id}')}")


async def apply_settings_text(message: Message, state: FSMContext, text: str) -> bool:
    """A number of days or a time typed for the reminders. False if it is neither."""
    user_id = message.from_user.id
    days = parse_days(text)
    if days is not None:
        intervals = get_user_settings(user_id)["intervals"]
        label = screens.interval_label(float(days)).lower()
        if float(days) in intervals:
            notice = f"Напоминание {label} уже включено."
        else:
            update_user_settings(user_id, intervals=intervals + [float(days)])
            notice = f"Добавил напоминание {label}."
        await show_settings(message, state, notice=notice)
        return True
    time_str = normalize_notify_time(text)
    if time_str:
        update_user_settings(user_id, notify_time=time_str)
        await show_settings(message, state, notice=f"Теперь напоминаю в **{time_str}**.")
        return True
    return False


def replied_ref(message: Message) -> dict | bool:
    """Filter: the message answers a remembered person or reminders message."""
    if not message.reply_to_message:
        return False
    ref = find_message(message.from_user.id, message.reply_to_message.message_id)
    return {"ref": ref} if ref else False


@dp.message(F.text, ~F.text.startswith("/"), replied_ref)
async def msg_reply(message: Message, state: FSMContext, ref: tuple):
    text = " ".join(message.text.split())
    if ref[0] == "person":
        return await apply_person_reply(message, state, ref[1], text)
    if await apply_settings_text(message, state, text):
        return
    await show(message, "Ответьте временем `08:30` или числом дней `14`.")


# --- Commands ---

@dp.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    await show_brief(message, state)


@dp.message(Command("help"))
async def cmd_help(message: Message, state: FSMContext):
    await state.clear()
    await show(message, screens.render_help())


@dp.message(Command("add"))
async def cmd_add(message: Message, state: FSMContext):
    await state.set_state(AppStates.adding)
    await show(message, screens.render_add_prompt())


@dp.message(Command("list", "upcoming"))
async def cmd_list(message: Message, state: FSMContext):
    await show_list(message, state)


@dp.message(Command("settings"))
async def cmd_settings(message: Message, state: FSMContext):
    await show_settings(message, state)


@dp.message(Command("cancel"))
@dp.message(F.text.in_({CANCEL_TEXT, LEGACY_CANCEL_TEXT}))
async def cmd_cancel(message: Message, state: FSMContext):
    had_state = await state.get_state() is not None
    await state.clear()
    await message.answer_rich(
        InputRichMessage(markdown="Отменено." if had_state else "Отменять нечего."),
        reply_markup=ReplyKeyboardRemove(),
    )


# --- Navigation: each opens a new message, so earlier ones stay as they were ---

@dp.callback_query(F.data.in_({"home"} | LEGACY_HOME))
async def cb_home(callback: CallbackQuery, state: FSMContext):
    await show_brief(callback, state)


@dp.callback_query(F.data == "cancel")
async def cb_cancel(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await show(callback, "Отменено.")


@dp.callback_query(F.data.in_({"help", "menu_help"}))
async def cb_help(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await show(callback, screens.render_help(), new=True)


@dp.callback_query(F.data.startswith("list:") | F.data.in_(LEGACY_LIST))
async def cb_list(callback: CallbackQuery, state: FSMContext):
    page = int(callback.data.split(":")[1]) if callback.data.startswith("list:") else 0
    await show_list(callback, state, page)


@dp.callback_query(F.data.startswith("page:"))
async def cb_page(callback: CallbackQuery, state: FSMContext):
    await show_list(callback, state, int(callback.data.split(":")[1]), new=False)


@dp.callback_query(F.data.startswith("list_page:"))
async def cb_legacy_list_page(callback: CallbackQuery, state: FSMContext):
    await show_list(callback, state)


@dp.callback_query(F.data.startswith("view:") | F.data.startswith("view_bday:")
                   | F.data.startswith("edit_name:") | F.data.startswith("edit_info:"))
async def cb_view(callback: CallbackQuery, state: FSMContext):
    await show_person(callback, state, cb_id(callback.data))


# --- Person actions: they change the message they were pressed on ---

@dp.callback_query(F.data.startswith("del:") | F.data.startswith("delete_confirm:")
                   | F.data.startswith("del_yes:") | F.data.startswith("delete_execute:"))
async def cb_delete(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    b_id = cb_id(callback.data)
    row = get_user_birthday(b_id, callback.from_user.id)
    if not row:
        return await show(callback, "Этой записи уже нет.")
    _, user_id, name, b_date, tag = row
    delete_birthday_by_id(b_id)
    keep(deleted, (user_id, b_id), (name, b_date, tag))
    await show(callback, screens.render_deleted(b_id, name))


@dp.callback_query(F.data.startswith("restore:"))
async def cb_restore(callback: CallbackQuery, state: FSMContext, callback_answer: CallbackAnswer):
    user_id = callback.from_user.id
    saved = deleted.pop((user_id, cb_id(callback.data)), None)
    if not saved:
        callback_answer.text = "Вернуть уже нельзя"
        callback_answer.show_alert = True
        return
    name, b_date, tag = saved
    if find_birthday_id(user_id, name) is not None:
        callback_answer.text = f"{name} уже снова в списке"
        callback_answer.show_alert = True
        return
    b_id = add_birthday(user_id, name, b_date, tag)
    await show_person(callback, state, b_id, notice="Вернул.", new=False)


@dp.callback_query(F.data.startswith("undo:"))
async def cb_undo(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    b_id = cb_id(callback.data)
    row = get_user_birthday(b_id, callback.from_user.id)
    if not row:
        return await show(callback, "Этой записи уже нет.")
    delete_birthday_by_id(b_id)
    await show(callback, screens.render_undone(row[2]))


@dp.callback_query(F.data.startswith("revert:"))
async def cb_revert(callback: CallbackQuery, state: FSMContext, callback_answer: CallbackAnswer):
    user_id, b_id = callback.from_user.id, cb_id(callback.data)
    saved = edited.pop((user_id, b_id), None)
    if not saved or not get_user_birthday(b_id, user_id):
        callback_answer.text = "Вернуть уже нельзя"
        callback_answer.show_alert = True
        return
    name, b_date, tag = saved
    try:
        update_birthday_info_by_id(b_id, name, tag)
    except sqlite3.IntegrityError:
        callback_answer.text = f"Имя {name} уже занято"
        callback_answer.show_alert = True
        return
    update_birthday_date_by_id(b_id, b_date)
    await show_person(callback, state, b_id, notice="Вернул как было.", new=False)


@dp.callback_query(F.data.startswith("edit_date:"))
async def cb_edit_date(callback: CallbackQuery, state: FSMContext):
    b_id = cb_id(callback.data)
    row = get_user_birthday(b_id, callback.from_user.id)
    if not row:
        return await show(callback, "Этой записи уже нет.")
    await state.clear()
    await state.set_state(AppStates.picking)
    await state.update_data(edit_b_id=b_id, name=row[2], calendar_mode="edit")
    await show(callback, screens.render_decade_picker(row[2], datetime.date.today().year), new=True)


# Flows started on the previous interface: a typed name or date still applies.

@dp.message(AppStates.editing_name, F.text)
async def msg_edit_name(message: Message, state: FSMContext):
    b_id = (await state.get_data())["edit_b_id"]
    await apply_person_reply(message, state, b_id, " ".join(message.text.split()))


@dp.message(AppStates.editing_date, F.text)
async def msg_edit_date(message: Message, state: FSMContext):
    b_id = (await state.get_data())["edit_b_id"]
    await apply_person_reply(message, state, b_id, " ".join(message.text.split()))


# --- Adding ---

@dp.callback_query(F.data.in_({"add", "menu_add", "add_manual_name"}))
async def cb_add(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await state.set_state(AppStates.adding)
    await show(callback, screens.render_add_prompt(), new=True)


@dp.message(AppStates.adding, F.text)
async def msg_adding(message: Message, state: FSMContext):
    name, tag, date_tuple = extract_name_and_date(message.text.strip())
    error = name_error(name)
    if error:
        return await show(message, error)
    tag = tag or (await state.get_data()).get("tg_username")
    if date_tuple:
        error = date_error(date_tuple)
        if error:
            return await show(message, error)
        return await save_new(message, state, name, tag, *date_tuple)
    await ask_date(message, state, name, tag)


@dp.callback_query(F.data == "add_pending")
async def cb_add_pending(callback: CallbackQuery, state: FSMContext):
    """"Add" on a search result: the searched name is already in FSM data."""
    data = await state.get_data()
    if not data.get("name"):
        await state.set_state(AppStates.adding)
        return await show(callback, screens.render_add_prompt(), new=True)
    await ask_date(callback, state, data["name"], data.get("tg_username"), new=True)


@dp.message(AppStates.adding_date, F.text)
async def msg_adding_date(message: Message, state: FSMContext):
    data = await state.get_data()
    date_tuple = parse_date_input(message.text.strip())
    error = date_error(date_tuple)
    if error:
        return await show(message, screens.screen(error, *screens.date_prompt_rows()))
    await save_new(message, state, data["name"], data.get("tg_username"), *date_tuple)


@dp.callback_query(F.data.in_({"confirm_yes", "confirm_add_yes"}))
async def cb_confirm_replace(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    if not {"name", "day", "month"} <= data.keys():
        return await show(callback, STALE)
    b_id = add_birthday(
        callback.from_user.id, data["name"],
        stored_date(data["day"], data["month"], data.get("year")), data.get("tg_username"),
    )
    await show_person(callback, state, b_id, notice="Заменил.", new=False)


@dp.callback_query(F.data.in_({"add_tg", "add_choose_contact"}))
async def cb_add_tg(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    request = KeyboardButtonRequestUsers(
        request_id=1, max_quantity=1, user_is_bot=False, request_name=True, request_username=True,
    )
    markup = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="Выбрать человека", request_users=request)],
                  [KeyboardButton(text=CANCEL_TEXT)]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )
    await callback.message.answer_rich(
        InputRichMessage(markdown=(
            "Нажмите **Выбрать человека** под полем ввода. Имя и тег я подставлю сам, "
            "останется дата."
        )),
        reply_markup=markup,
    )


@dp.message(F.users_shared)
async def msg_users_shared(message: Message, state: FSMContext):
    shared = message.users_shared.users[0]
    name = " ".join(filter(None, [shared.first_name, shared.last_name]))
    tag = f"@{shared.username}" if shared.username else None
    if name_error(name):
        await message.answer_rich(InputRichMessage(markdown=screens.render_add_prompt(prefilled_tag=tag)),
                                  reply_markup=ReplyKeyboardRemove())
        await state.set_state(AppStates.adding)
        return await state.update_data(tg_username=tag)
    await state.set_state(AppStates.adding_date)
    await state.update_data(name=name, tg_username=tag, calendar_mode="add")
    await message.answer_rich(InputRichMessage(markdown=screens.render_date_prompt(name, tag)),
                              reply_markup=ReplyKeyboardRemove())


@dp.message(F.contact)
async def msg_contact(message: Message, state: FSMContext):
    name = " ".join(filter(None, [message.contact.first_name, message.contact.last_name]))
    if name_error(name):
        await state.set_state(AppStates.adding)
        return await show(message, screens.render_add_prompt())
    await ask_date(message, state, name, None)


# --- Calendar picker ---

async def picker_data(callback: CallbackQuery, state: FSMContext, *keys) -> dict | None:
    data = await state.get_data()
    if data.get("calendar_mode") not in ("add", "edit") or not set(keys) <= data.keys():
        await show(callback, STALE)
        return None
    return data


@dp.callback_query(F.data.in_({"cal", "add_contact_calendar", "edit_date_calendar", "confirm_add_manual"}))
async def cb_calendar(callback: CallbackQuery, state: FSMContext):
    data = await picker_data(callback, state, "name")
    if data is None:
        return
    await state.set_state(AppStates.picking)
    await show(callback, screens.render_decade_picker(data["name"], datetime.date.today().year))


@dp.callback_query(F.data == "back_dec")
async def cb_back_decade(callback: CallbackQuery, state: FSMContext):
    await cb_calendar(callback, state)


@dp.callback_query(F.data.startswith("dec:"))
async def cb_decade(callback: CallbackQuery, state: FSMContext):
    data = await picker_data(callback, state, "name")
    if data is None:
        return
    decade = int(callback.data.split(":")[1])
    await state.update_data(decade=decade)
    await show(callback, screens.render_year_picker(data["name"], decade, datetime.date.today().year))


@dp.callback_query(F.data == "back_year")
async def cb_back_year(callback: CallbackQuery, state: FSMContext):
    data = await picker_data(callback, state, "name", "decade")
    if data is None:
        return
    await show(callback, screens.render_year_picker(data["name"], data["decade"], datetime.date.today().year))


@dp.callback_query(F.data.startswith("year:") | (F.data == "noyear"))
async def cb_year(callback: CallbackQuery, state: FSMContext):
    data = await picker_data(callback, state, "name")
    if data is None:
        return
    year = YEARLESS_YEAR if callback.data == "noyear" else int(callback.data.split(":")[1])
    await state.update_data(year=year)
    await show(callback, screens.render_month_picker(data["name"], year))


@dp.callback_query(F.data == "back_month")
async def cb_back_month(callback: CallbackQuery, state: FSMContext):
    data = await picker_data(callback, state, "name", "year")
    if data is None:
        return
    await show(callback, screens.render_month_picker(data["name"], data["year"]))


@dp.callback_query(F.data.startswith("month:"))
async def cb_month(callback: CallbackQuery, state: FSMContext):
    data = await picker_data(callback, state, "name", "year")
    if data is None:
        return
    month = int(callback.data.split(":")[1])
    await state.update_data(month=month)
    await show(callback, screens.render_day_picker(data["name"], data["year"], month))


@dp.callback_query(F.data.startswith("day:"))
async def cb_day(callback: CallbackQuery, state: FSMContext):
    data = await picker_data(callback, state, "name", "year", "month")
    if data is None:
        return
    day, month, year = int(callback.data.split(":")[1]), data["month"], data["year"]
    if data["calendar_mode"] == "edit":
        b_id = data["edit_b_id"]
        row = get_user_birthday(b_id, callback.from_user.id)
        if row:
            keep(edited, (callback.from_user.id, b_id), (row[2], row[3], row[4]))
            update_birthday_date_by_id(b_id, stored_date(day, month, year))
        return await show_person(callback, state, b_id, new=False,
                                 notice=f"Исправил. {screens.link('Вернуть как было', f'revert:{b_id}')}")
    await save_new(callback, state, data["name"], data.get("tg_username"), day, month,
                   None if year == YEARLESS_YEAR else year, new=False)


@dp.callback_query(F.data == "picker_cancel")
async def cb_picker_cancel(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    if data.get("calendar_mode") == "edit" and "edit_b_id" in data:
        return await show_person(callback, state, data["edit_b_id"], new=False)
    await state.clear()
    await show(callback, "Отменено.")


# --- Reminders ---

@dp.callback_query(F.data.in_({"settings"} | LEGACY_SETTINGS))
async def cb_settings(callback: CallbackQuery, state: FSMContext):
    await show_settings(callback, state)


@dp.callback_query(F.data == "settings:here")
async def cb_settings_here(callback: CallbackQuery, state: FSMContext):
    await show_settings(callback, state, new=False)


@dp.callback_query(F.data.startswith("time:") | F.data.startswith("time_preset:"))
async def cb_time(callback: CallbackQuery, state: FSMContext, callback_answer: CallbackAnswer):
    time_str = normalize_notify_time(callback.data.split(":", 1)[1])
    if time_str:
        update_user_settings(callback.from_user.id, notify_time=time_str)
        callback_answer.text = f"Напоминаю в {time_str}"
    await show_settings(callback, state, new=False)


@dp.callback_query(F.data.startswith("int:") | F.data.startswith("toggle_int:"))
async def cb_toggle_interval(callback: CallbackQuery, state: FSMContext, callback_answer: CallbackAnswer):
    try:
        val = float(callback.data.split(":")[1])
    except ValueError:
        val = None
    known = val in screens.ALL_INTERVALS or (
        val is not None and screens.is_day_interval(val) and val <= screens.MAX_REMIND_DAYS
    )
    if known:
        current = get_user_settings(callback.from_user.id)["intervals"]
        label = screens.interval_label(val)
        if val in current:
            current.remove(val)
            callback_answer.text = f"Выключено: {label.lower()}"
        else:
            current.append(val)
            callback_answer.text = f"Включено: {label.lower()}"
        update_user_settings(callback.from_user.id, intervals=current)
    await show_settings(callback, state, new=False)


@dp.callback_query(F.data.startswith("ints:") | F.data.startswith("preset_int:"))
async def cb_interval_preset(callback: CallbackQuery, state: FSMContext):
    preset = callback.data.split(":")[1]
    intervals = {"all": screens.ALL_INTERVALS, "none": []}.get(preset, [7.0, 1.0, 0.0])
    update_user_settings(callback.from_user.id, intervals=list(intervals))
    await show_settings(callback, state, new=False)


@dp.message(AppStates.settings, F.text, ~F.text.startswith("/"))
async def msg_settings_text(message: Message, state: FSMContext):
    """Right after the reminders: a time or a number of days applies; anything else as usual."""
    text = " ".join(message.text.split())
    if await apply_settings_text(message, state, text):
        return
    await state.clear()
    await handle_free_text(message, state, text)


# --- Backup ---

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


@dp.callback_query(F.data.in_({"backup", "menu_backup"}))
async def cb_backup(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    total = len(get_birthdays_for_user(callback.from_user.id))
    await show(callback, screens.render_backup(total), new=callback.data == "menu_backup")


@dp.callback_query(F.data.in_({"export", "backup_export"}))
async def cb_export(callback: CallbackQuery, callback_answer: CallbackAnswer):
    birthdays = get_birthdays_for_user(callback.from_user.id)
    if not birthdays:
        callback_answer.text = "Список пуст, выгружать нечего"
        callback_answer.show_alert = True
        return
    user_data = []
    for _id, name, b_date, tag in sort_by_name(birthdays):
        date_out = b_date[:5] if b_date.endswith(f".{YEARLESS_YEAR}") else b_date
        user_data.append({"name": name, "date": date_out, "tag": tag})
    json_data = json.dumps(user_data, ensure_ascii=False, indent=2)
    stamp = datetime.date.today().isoformat()
    file = BufferedInputFile(json_data.encode("utf-8"), filename=f"birthdays_{stamp}.json")
    await callback.message.answer_document(
        file, caption=f"Резервная копия: {screens.records_word(len(user_data))}"
    )
    callback_answer.text = "Файл отправлен"


@dp.callback_query(F.data.in_({"import", "backup_import"}))
async def cb_import(callback: CallbackQuery, state: FSMContext):
    await state.set_state(AppStates.importing)
    await show(callback, screens.render_import_prompt())


@dp.message(AppStates.importing, F.document)
async def msg_import(message: Message, state: FSMContext):
    if message.document.file_size and message.document.file_size > 1024 * 1024:
        return await show(message, "Файл больше 1 МБ — это точно резервная копия? Пришлите другой или /cancel.")
    content = await bot.download(message.document, io.BytesIO())
    try:
        data = json.loads(content.getvalue().decode("utf-8"))
        if not isinstance(data, list):
            raise ValueError
    except (UnicodeDecodeError, ValueError):
        return await show(message, "Не похоже на резервную копию: жду JSON-список записей. Пришлите другой файл или /cancel.")

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
    await show(message, screens.render_import_result(added, updated, skipped))


# --- Fallbacks (registered last) ---

@dp.message(F.text.startswith("/"))
async def msg_unknown_command(message: Message):
    await show(message, "Такой команды нет. Список команд — в /help.")


async def route_text(message: Message, state: FSMContext):
    await state.clear()
    await handle_free_text(message, state, message.text.strip())


@dp.message(F.text, ~StateFilter(AppStates.importing))
async def msg_free_text(message: Message, state: FSMContext):
    """No flow is waiting for this text (or the flow's buttons were left behind)."""
    await route_text(message, state)


@dp.callback_query()
async def cb_unknown(callback: CallbackQuery, callback_answer: CallbackAnswer):
    """Buttons from messages of older versions that no longer exist."""
    callback_answer.text = STALE
    callback_answer.show_alert = True


@dp.message()
async def msg_unexpected(message: Message, state: FSMContext):
    if await state.get_state() == AppStates.importing.state:
        return await show(message, "Жду JSON-файл резервной копии. Чтобы выйти, нажмите /cancel.")
    await show(message, "Я понимаю текст и кнопки. Напишите `Имя дата`, чтобы добавить человека.")


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

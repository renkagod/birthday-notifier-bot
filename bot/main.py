import asyncio
import datetime
import json
import logging
import os
import re

from aiogram import Bot, Dispatcher, F, types
from aiogram.client.default import DefaultBotProperties
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    BufferedInputFile,
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    Message,
    ReplyKeyboardMarkup,
)
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from dotenv import load_dotenv

from bot.database import (
    add_birthday,
    delete_birthday_by_id,
    get_birthday_by_id,
    get_birthdays_for_user,
    get_user_settings,
    init_db,
    update_birthday_date_by_id,
    update_birthday_info_by_id,
    update_user_settings,
)
from bot.dates import (
    age_turning,
    days_until,
    extract_name_and_date,
    next_birthday_datetime,
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

bot = Bot(token=TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
dp = Dispatcher()

MONTHS_RU_NAME = {
    1: "Январе", 2: "Феврале", 3: "Марте", 4: "Апреле", 5: "Мае", 6: "Июне",
    7: "Июле", 8: "Августе", 9: "Сентябре", 10: "Октябре", 11: "Ноябре", 12: "Декабре"
}

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

def get_main_menu():
    keyboard = [
        [InlineKeyboardButton(text="➕ Добавить", callback_data="menu_add"), 
         InlineKeyboardButton(text="📅 Мой список", callback_data="menu_list")],
        [InlineKeyboardButton(text="🔥 Ближайшие", callback_data="menu_upcoming")],
        [InlineKeyboardButton(text="⚙️ Настройки", callback_data="menu_settings"),
         InlineKeyboardButton(text="💾 Бэкап", callback_data="menu_backup")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

ITEMS_PER_PAGE = 8

def get_sorted_birthdays(user_id, sort_by="name"):
    birthdays = get_birthdays_for_user(user_id)
    if sort_by == "name":
        return sort_by_name(birthdays)
    now = datetime.datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    return sort_by_upcoming(birthdays, now)

def get_birthdays_page_keyboard(user_id, page=0, sort_by="name"):
    birthdays = get_sorted_birthdays(user_id, sort_by)
    total_items = len(birthdays)
    total_pages = (total_items + ITEMS_PER_PAGE - 1) // ITEMS_PER_PAGE
    if total_pages == 0:
        total_pages = 1
    if page >= total_pages:
        page = total_pages - 1
    if page < 0:
        page = 0
        
    start_idx = page * ITEMS_PER_PAGE
    page_items = birthdays[start_idx:start_idx+ITEMS_PER_PAGE]
    
    keyboard = []
    for b_id, b_name, b_date, _b_tag in page_items:
        try:
            bday_dt = parse_birth_date(b_date)
            date_display = bday_dt.strftime("%d.%m") if bday_dt.year == 1004 else bday_dt.strftime("%d.%m.%Y")
        except Exception:
            date_display = b_date
        keyboard.append([InlineKeyboardButton(text=f"👤 {b_name} ({date_display})", callback_data=f"view_bday:{b_id}:{page}:{sort_by}")])
        
    nav_row = []
    if page > 0:
        nav_row.append(InlineKeyboardButton(text="⬅️ Пред.", callback_data=f"list_page:{page-1}:{sort_by}"))
    nav_row.append(InlineKeyboardButton(text=f"📄 {page+1}/{total_pages}", callback_data="ignore"))
    if page < total_pages - 1:
        nav_row.append(InlineKeyboardButton(text="След. ➡️", callback_data=f"list_page:{page+1}:{sort_by}"))
    if len(nav_row) > 1 or (len(nav_row) == 1 and nav_row[0].text != "📄 1/1"):
        keyboard.append(nav_row)
        
    next_sort = 'date' if sort_by == 'name' else 'name'
    sort_label = "🔄 По дате" if sort_by == 'name' else "🔄 По имени"
    keyboard.append([
        InlineKeyboardButton(text=sort_label, callback_data=f"list_page:{page}:{next_sort}"),
        InlineKeyboardButton(text="🔙 Меню", callback_data="menu_start")
    ])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

@dp.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("<b>🎂 Birthday Notifier</b>\n\nЯ помогу вам не забыть про важные даты.\nВыберите действие в меню:", reply_markup=get_main_menu())

# --- SETTINGS ---
def get_intervals_keyboard(user_id):
    s = get_user_settings(user_id)
    current = s['intervals']
    options = [
        (30.0, "📅 За месяц"), (7.0, "📅 За неделю"), (3.0, "📅 За 3 дня"), 
        (1.0, "📅 Завтра"), (0.0, "☀️ Сегодня (днем)"),
        (0.5, "⏳ За 30 мин"), (0.08, "⏳ За 5 мин"), (-1.0, "🌙 В полночь (00:00)")
    ]
    keyboard = [[InlineKeyboardButton(text=f"{'✅' if val in current else '❌'} {label}", callback_data=f"toggle_int:{val}")] for val, label in options]
    keyboard.append([
        InlineKeyboardButton(text="🔔 Всё", callback_data="preset_int:all"),
        InlineKeyboardButton(text="🔕 Ничего", callback_data="preset_int:none"),
        InlineKeyboardButton(text="⭐ Стандарт", callback_data="preset_int:default")
    ])
    keyboard.append([InlineKeyboardButton(text="🔙 Назад", callback_data="menu_settings")])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

@dp.callback_query(F.data == "menu_settings")
async def settings_main(callback: CallbackQuery):
    s = get_user_settings(callback.from_user.id)
    display_ints = []
    mapping = {
        30.0: "Месяц", 7.0: "Неделя", 3.0: "3 дня", 1.0: "Завтра", 
        0.0: "Днем", 0.5: "30 мин", 0.08: "5 мин", -1.0: "Полночь"
    }
    for i in s['intervals']:
        if i in mapping: display_ints.append(mapping[i])
    text = (f"⚙️ <b>Настройки уведомлений</b>\n\n⏰ Время напоминаний: <b>{s['notify_time']}</b>\n"
            f"🔔 Активные интервалы: <b>{', '.join(display_ints) if display_ints else 'Нет'}</b>\n\nВыберите пункт для изменения:")
    keyboard = [[InlineKeyboardButton(text="⏰ Изменить время", callback_data="set_time")], [InlineKeyboardButton(text="🔔 Выбрать интервалы", callback_data="set_intervals")], [InlineKeyboardButton(text="🔙 Назад", callback_data="menu_start")]]
    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard))

@dp.callback_query(F.data == "set_intervals")
async def set_intervals_menu(callback: CallbackQuery):
    await callback.message.edit_text("<b>Выберите интервалы уведомлений:</b>", reply_markup=get_intervals_keyboard(callback.from_user.id))

@dp.callback_query(F.data.startswith("toggle_int:"))
async def process_toggle_int(callback: CallbackQuery):
    val = float(callback.data.split(":")[1])
    s = get_user_settings(callback.from_user.id)
    current = s['intervals']
    if val in current: current.remove(val)
    else: current.append(val)
    update_user_settings(callback.from_user.id, intervals=current)
    await callback.message.edit_reply_markup(reply_markup=get_intervals_keyboard(callback.from_user.id))

@dp.callback_query(F.data.startswith("preset_int:"))
async def process_preset_int(callback: CallbackQuery):
    preset = callback.data.split(":")[1]
    if preset == "all":
        intervals = [30.0, 7.0, 3.0, 1.0, 0.0, 0.5, 0.08, -1.0]
    elif preset == "none":
        intervals = []
    else:
        intervals = [1.0, 0.0, -1.0]
    update_user_settings(callback.from_user.id, intervals=intervals)
    await callback.message.edit_reply_markup(reply_markup=get_intervals_keyboard(callback.from_user.id))

# --- BACKUP ---
@dp.callback_query(F.data == "menu_backup")
async def backup_menu(callback: CallbackQuery):
    keyboard = [[InlineKeyboardButton(text="📤 Экспорт в JSON", callback_data="backup_export")], [InlineKeyboardButton(text="📥 Импорт из JSON", callback_data="backup_import")], [InlineKeyboardButton(text="🔙 Назад", callback_data="menu_start")]]
    await callback.message.edit_text("💾 <b>Резервное копирование</b>", reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard))

@dp.callback_query(F.data == "backup_export")
async def backup_export(callback: CallbackQuery):
    birthdays = get_birthdays_for_user(callback.from_user.id)
    user_data = [{"name": b[1], "date": b[2], "tag": b[3]} for b in birthdays]
    if not user_data: return await callback.answer("❌ Нечего экспортировать", show_alert=True)
    json_data = json.dumps(user_data, ensure_ascii=False, indent=2)
    file = BufferedInputFile(json_data.encode('utf-8'), filename="birthdays_backup.json")
    await callback.message.answer_document(file, caption="✅ Ваш бэкап готов!")
    await callback.answer()

@dp.callback_query(F.data == "backup_import")
async def backup_import_start(callback: CallbackQuery, state: FSMContext):
    await state.set_state(AppStates.waiting_for_import)
    await callback.message.edit_text("📥 Отправьте JSON файл бэкапа:", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="❌ Отмена", callback_data="menu_backup")]]))

@dp.message(AppStates.waiting_for_import, F.document)
async def process_import(message: Message, state: FSMContext):
    file = await bot.get_file(message.document.file_id)
    import io
    content = await bot.download_file(file.file_path, io.BytesIO())
    try:
        data = json.loads(content.getvalue().decode('utf-8'))
        count = 0
        for item in data:
            if "name" in item and "date" in item:
                raw_date = item['date']
                if len(raw_date) == 5:
                    raw_date = f"{raw_date}.1004"
                add_birthday(message.from_user.id, item['name'], raw_date, item.get('tag'))
                count += 1
        await message.answer(f"✅ Импортировано <b>{count}</b> записей!", reply_markup=get_main_menu())
        await state.clear()
    except Exception as e: await message.answer(f"❌ Ошибка: {e}", reply_markup=get_main_menu())

# --- LIST / DETAIL VIEW / EDIT / DELETE BY ID ---
@dp.callback_query(F.data.startswith("menu_list"))
async def menu_list_birthdays(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    sort_by = 'name'
    if ":" in callback.data:
        sort_by = callback.data.split(":")[1]
    
    birthdays = get_sorted_birthdays(callback.from_user.id, sort_by)
    if not birthdays: 
        return await callback.message.edit_text("ℹ️ Список пуст.", reply_markup=get_main_menu())
    
    await callback.message.edit_text(
        "📅 <b>Ваш список именинников:</b>", 
        reply_markup=get_birthdays_page_keyboard(callback.from_user.id, page=0, sort_by=sort_by)
    )

@dp.callback_query(F.data.startswith("list_page:"))
async def process_list_page(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    parts = callback.data.split(":")
    page = int(parts[1])
    sort_by = parts[2]
    
    await callback.message.edit_text(
        "📅 <b>Ваш список именинников:</b>", 
        reply_markup=get_birthdays_page_keyboard(callback.from_user.id, page=page, sort_by=sort_by)
    )

@dp.callback_query(F.data.startswith("view_bday:"))
async def view_birthday_details(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    parts = callback.data.split(":")
    b_id = int(parts[1])
    page = int(parts[2])
    sort_by = parts[3]
    
    row = get_birthday_by_id(b_id)
    if not row:
        return await callback.answer("❌ Запись не найдена", show_alert=True)
    
    _, user_id, name, b_date, tg_username = row
    
    now = datetime.datetime.now()
    try:
        bday_dt = parse_birth_date(b_date)
        target_date = next_birthday_datetime(bday_dt, now)
        days_left = days_until(target_date, now)
        is_yearless = bday_dt.year == 1004
        date_display = bday_dt.strftime("%d.%m") if is_yearless else b_date
        age_display = f"\n• Исполнится лет: <b>{age_turning(bday_dt, target_date)}</b>" if not is_yearless else ""
    except Exception:
        date_display = b_date
        days_left = "?"
        age_display = ""
        
    tag_display = tg_username if tg_username else "нет"
    
    text = (
        f"👤 <b>Карточка контакта</b>\n\n"
        f"• Имя: <b>{name}</b>\n"
        f"• Дата рождения: <code>{date_display}</code>{age_display}\n"
        f"• Telegram-тег: {tag_display}\n"
        f"• Дней до события: <b>{days_left}</b>"
    )
    
    keyboard = [
        [
            InlineKeyboardButton(text="✏️ Изменить инфо", callback_data=f"edit_info:{b_id}:{page}:{sort_by}"),
            InlineKeyboardButton(text="📅 Изменить дату", callback_data=f"edit_date:{b_id}:{page}:{sort_by}")
        ],
        [InlineKeyboardButton(text="🗑 Удалить", callback_data=f"delete_confirm:{b_id}:{page}:{sort_by}")],
        [InlineKeyboardButton(text="🔙 Назад к списку", callback_data=f"list_page:{page}:{sort_by}")]
    ]
    
    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard), disable_web_page_preview=True)

@dp.callback_query(F.data.startswith("delete_confirm:"))
async def process_delete_confirm(callback: CallbackQuery):
    parts = callback.data.split(":")
    b_id = int(parts[1])
    page = int(parts[2])
    sort_by = parts[3]
    
    row = get_birthday_by_id(b_id)
    if not row:
        return await callback.answer("❌ Запись не найдена", show_alert=True)
        
    text = f"❓ Вы уверены, что хотите удалить день рождения <b>{row[2]}</b>?"
    
    keyboard = [
        [
            InlineKeyboardButton(text="🗑 Да, удалить", callback_data=f"delete_execute:{b_id}:{page}:{sort_by}"),
            InlineKeyboardButton(text="❌ Отмена", callback_data=f"view_bday:{b_id}:{page}:{sort_by}")
        ]
    ]
    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard))

@dp.callback_query(F.data.startswith("delete_execute:"))
async def process_delete_execute(callback: CallbackQuery):
    parts = callback.data.split(":")
    b_id = int(parts[1])
    page = int(parts[2])
    sort_by = parts[3]
    
    row = get_birthday_by_id(b_id)
    if row:
        delete_birthday_by_id(b_id)
        await callback.answer(f"✅ Удалено: {row[2]}", show_alert=True)
        
    await callback.message.edit_text(
        "📅 <b>Ваш список именинников:</b>",
        reply_markup=get_birthdays_page_keyboard(callback.from_user.id, page, sort_by)
    )

@dp.callback_query(F.data.startswith("edit_info:"))
async def process_edit_info_start(callback: CallbackQuery, state: FSMContext):
    parts = callback.data.split(":")
    b_id = int(parts[1])
    page = int(parts[2])
    sort_by = parts[3]
    
    row = get_birthday_by_id(b_id)
    if not row:
        return await callback.answer("❌ Запись не найдена", show_alert=True)
        
    await state.set_state(AppStates.waiting_for_edit_data)
    await state.update_data(edit_b_id=b_id, edit_page=page, edit_sort_by=sort_by)
    
    await callback.message.edit_text(
        f"Текущее имя: <b>{row[2]}</b>\nТекущий тег: <b>{row[4] or 'нет'}</b>\n\n"
        f"📝 Введите новое имя и @тег (например: <code>Иван @ivan</code>):",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="❌ Отмена", callback_data=f"view_bday:{b_id}:{page}:{sort_by}")
        ]])
    )

@dp.message(AppStates.waiting_for_edit_data)
async def process_edit_data(message: Message, state: FSMContext):
    text = message.text.strip()
    match = re.search(r'(@\w+)', text)
    new_tag = match.group(1) if match else None
    new_name = re.sub(r'(@\w+)', '', text).strip()
    
    if not new_name:
        await message.answer("❌ Имя не может быть пустым. Пожалуйста, введите имя:")
        return
        
    data = await state.get_data()
    b_id = data['edit_b_id']
    
    update_birthday_info_by_id(b_id, new_name, new_tag)
    await state.clear()
    await message.answer("✅ Контакт обновлен!", reply_markup=get_main_menu())

@dp.callback_query(F.data.startswith("edit_date:"))
async def process_edit_date_start(callback: CallbackQuery, state: FSMContext):
    parts = callback.data.split(":")
    b_id = int(parts[1])
    page = int(parts[2])
    sort_by = parts[3]
    
    await state.set_state(AppStates.waiting_for_edit_date)
    await state.update_data(edit_b_id=b_id, edit_page=page, edit_sort_by=sort_by)
    
    keyboard = [
        [InlineKeyboardButton(text="📅 Календарь", callback_data="edit_date_calendar")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data=f"view_bday:{b_id}:{page}:{sort_by}")]
    ]
    await callback.message.edit_text(
        "📝 Отправьте новую дату текстом (например: <code>15.08.1990</code>, <code>22.10</code> или <code>3 августа</code>):",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard)
    )

@dp.message(AppStates.waiting_for_edit_date)
async def process_edit_date_text(message: Message, state: FSMContext):
    text = message.text.strip()
    date_tuple = parse_natural_date(text)
    if not date_tuple:
        _, _, date_tuple = extract_name_and_date(text)
        
    if date_tuple:
        day, month, year = date_tuple
        year = year if year is not None else 1004
        date_str = f"{day:02d}.{month:02d}.{year}"
        
        data = await state.get_data()
        b_id = data['edit_b_id']
        
        update_birthday_date_by_id(b_id, date_str)
        date_display = f"{day:02d}.{month:02d}" + (f".{year}" if year != 1004 else "")
        await message.answer(f"✅ Дата обновлена на: <b>{date_display}</b>", reply_markup=get_main_menu())
        await state.clear()
    else:
        await message.answer("❌ Не удалось распознать дату. Введите еще раз в формате ДД.ММ.ГГГГ, ДД.ММ или словесно (например, 3 августа):")

@dp.callback_query(F.data == "edit_date_calendar")
async def process_edit_date_calendar(callback: CallbackQuery, state: FSMContext):
    await state.update_data(calendar_mode="edit")
    await state.set_state(AppStates.waiting_for_decade)
    await callback.message.edit_text("📅 Выберите десятилетие:", reply_markup=get_decade_keyboard())

# --- ADD BIRTHDAY FLOW (SMART & MANUAL WIZARDS) ---
def get_decade_keyboard():
    keyboard = []
    curr = datetime.datetime.now().year
    start = (curr // 10) * 10
    for d in range(start, start - 80, -20):
        keyboard.append([InlineKeyboardButton(text=f"{i}s", callback_data=f"set_decade:{i}") for i in range(d, d - 20, -10)])
    keyboard.append([InlineKeyboardButton(text="🤷‍♂️ Без года", callback_data="skip_year")])
    keyboard.append([InlineKeyboardButton(text="❌ Отмена", callback_data="menu_start")])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def get_year_in_decade_keyboard(decade):
    keyboard = []
    for y in range(decade + 9, decade - 1, -1):
        if (decade + 9 - y) % 5 == 0: keyboard.append([])
        keyboard[-1].append(InlineKeyboardButton(text=str(y), callback_data=f"set_year:{y}"))
    keyboard.append([InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_decade")])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def get_month_keyboard(is_yearless=False):
    months = ["Янв", "Фев", "Мар", "Апр", "Май", "Июн", "Июл", "Авг", "Сен", "Окт", "Ноя", "Дек"]
    keyboard = []
    for i in range(0, 12, 3): 
        keyboard.append([InlineKeyboardButton(text=months[m], callback_data=f"set_month:{m+1}") for m in range(i, i + 3)])
    back_callback = "back_to_decade" if is_yearless else "back_to_year"
    keyboard.append([InlineKeyboardButton(text="🔙 Назад", callback_data=back_callback)])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def get_day_keyboard(year, month):
    import calendar
    kb = []
    
    months_ru = ["Январь", "Февраль", "Март", "Апрель", "Май", "Июнь", "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь"]
    month_name = months_ru[month - 1]
    year_display = f" {year}г." if year != 1004 else " (без года)"
    kb.append([InlineKeyboardButton(text=f"📅 {month_name}{year_display}", callback_data="ignore")])
    
    weekdays = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
    kb.append([InlineKeyboardButton(text=day, callback_data="ignore") for day in weekdays])
    
    for week in calendar.monthcalendar(year, month):
        kb.append([InlineKeyboardButton(text=str(day) if day != 0 else " ", callback_data=f"set_day:{day}" if day != 0 else "ignore") for day in week])
        
    kb.append([InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_month")])
    return InlineKeyboardMarkup(inline_keyboard=kb)

@dp.callback_query(F.data == "menu_add")
async def menu_add_options(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    keyboard = [
        [InlineKeyboardButton(text="📝 Ввести имя вручную", callback_data="add_manual_name")],
        [InlineKeyboardButton(text="👤 Выбрать из контактов", callback_data="add_choose_contact")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="menu_start")]
    ]
    await callback.message.edit_text("Выберите способ добавления:", reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard))

@dp.callback_query(F.data == "add_manual_name")
async def add_manual_name_start(callback: CallbackQuery, state: FSMContext):
    await state.set_state(AppStates.waiting_for_name)
    await callback.message.edit_text(
        "📝 Введите имя (и @тег, если нужно), а также дату рождения, если хотите добавить в один шаг.\n\n"
        "Например:\n"
        "• <code>Иван Иванов @ivan 12.05.1990</code>\n"
        "• <code>Маша 3 августа</code>\n\n"
        "Или просто введите имя:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="❌ Отмена", callback_data="menu_start")]])
    )

@dp.callback_query(F.data == "add_choose_contact")
async def add_choose_contact_start(callback: CallbackQuery):
    kb = [[KeyboardButton(text="👤 Выбрать контакт", request_contact=True)]]
    reply_markup = ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True, one_time_keyboard=True)
    await callback.message.answer("Нажмите кнопку ниже для отправки контакта:", reply_markup=reply_markup)
    await callback.answer()

@dp.message(F.contact)
async def process_contact(message: Message, state: FSMContext):
    name = f"{message.contact.first_name} {message.contact.last_name or ''}".strip()
    await state.update_data(name=name, tg_username=None)
    await state.set_state(AppStates.waiting_for_contact_date)
    
    keyboard = [
        [InlineKeyboardButton(text="📅 Календарь", callback_data="add_contact_calendar")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="menu_start")]
    ]
    
    await message.answer("👤 Контакт получен.", reply_markup=types.ReplyKeyboardRemove())
    await message.answer(
        f"Имя контакта: <b>{name}</b>\n\n"
        f"📝 Отправьте дату его рождения (например: <code>15.08.1990</code> или <code>3 августа</code>) или откройте интерактивный календарь:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard)
    )

@dp.callback_query(F.data == "add_contact_calendar")
async def process_add_contact_calendar(callback: CallbackQuery, state: FSMContext):
    await state.set_state(AppStates.waiting_for_decade)
    await callback.message.edit_text("📅 Выберите десятилетие:", reply_markup=get_decade_keyboard())

@dp.message(AppStates.waiting_for_contact_date)
async def process_contact_date_text(message: Message, state: FSMContext):
    text = message.text.strip()
    date_tuple = parse_natural_date(text)
    if not date_tuple:
        _, _, date_tuple = extract_name_and_date(text)
        
    if date_tuple:
        day, month, year = date_tuple
        year = year if year is not None else 1004
        date_str = f"{day:02d}.{month:02d}.{year}"
        
        data = await state.get_data()
        add_birthday(message.from_user.id, data['name'], date_str, data.get('tg_username'))
        
        date_display = f"{day:02d}.{month:02d}" + (f".{year}" if year != 1004 else "")
        await message.answer(f"✅ Добавлено: <b>{data['name']}</b> ({date_display})", reply_markup=get_main_menu())
        await state.clear()
    else:
        await message.answer("❌ Не удалось распознать дату. Введите еще раз в формате ДД.ММ.ГГГГ, ДД.ММ или словесно (например, 3 августа):")

@dp.message(AppStates.waiting_for_name)
async def process_name(message: Message, state: FSMContext):
    text = message.text.strip()
    name, username, date_tuple = extract_name_and_date(text)
    
    if not name:
        await message.answer("❌ Пожалуйста, введите имя:")
        return
        
    await state.update_data(name=name, tg_username=username)
    
    if date_tuple:
        day, month, year = date_tuple
        await state.update_data(day=day, month=month, year=year if year is not None else 1004)
        
        date_display = f"{day:02d}.{month:02d}" + (f".{year}" if year is not None else "")
        tag_display = username if username else "нет"
        
        text_confirm = (
            f"🔍 <b>Распознаны данные:</b>\n\n"
            f"👤 Имя: <b>{name}</b>\n"
            f"📅 Дата: <b>{date_display}</b>\n"
            f"🔗 Тег: <b>{tag_display}</b>\n\n"
            f"Всё верно?"
        )
        
        keyboard = [
            [
                InlineKeyboardButton(text="✅ Да, сохранить", callback_data="confirm_add_yes"),
                InlineKeyboardButton(text="✏️ Изменить вручную", callback_data="confirm_add_manual")
            ]
        ]
        await state.set_state(AppStates.waiting_for_confirm_add)
        await message.answer(text_confirm, reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard))
    else:
        await state.set_state(AppStates.waiting_for_decade)
        await message.answer(f"Имя: <b>{name}</b>\n📅 Выберите десятилетие рождения:", reply_markup=get_decade_keyboard())

@dp.callback_query(F.data == "confirm_add_yes")
async def process_confirm_add_yes(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    day = data['day']
    month = data['month']
    year = data['year']
    date_str = f"{day:02d}.{month:02d}.{year}"
    
    add_birthday(callback.from_user.id, data['name'], date_str, data.get('tg_username'))
    await state.clear()
    
    date_display = f"{day:02d}.{month:02d}" + (f".{year}" if year != 1004 else "")
    await callback.message.edit_text(f"✅ Добавлено: <b>{data['name']}</b> ({date_display})", reply_markup=get_main_menu())

@dp.callback_query(F.data == "confirm_add_manual")
async def process_confirm_add_manual(callback: CallbackQuery, state: FSMContext):
    await state.set_state(AppStates.waiting_for_decade)
    await callback.message.edit_text("📅 Выберите десятилетие:", reply_markup=get_decade_keyboard())

@dp.callback_query(F.data == "skip_year")
async def process_skip_year(callback: CallbackQuery, state: FSMContext):
    await state.update_data(year=1004)
    await callback.message.edit_text("📅 Выберите месяц:", reply_markup=get_month_keyboard(is_yearless=True))

@dp.callback_query(F.data.startswith("set_decade:"))
async def process_decade(callback: CallbackQuery, state: FSMContext):
    decade = int(callback.data.split(":")[1])
    await state.update_data(decade=decade)
    await callback.message.edit_text("📅 Выберите год:", reply_markup=get_year_in_decade_keyboard(decade))

@dp.callback_query(F.data.startswith("set_year:"))
async def process_year(callback: CallbackQuery, state: FSMContext):
    await state.update_data(year=int(callback.data.split(":")[1]))
    await callback.message.edit_text("📅 Выберите месяц:", reply_markup=get_month_keyboard(is_yearless=False))

@dp.callback_query(F.data.startswith("set_month:"))
async def process_month(callback: CallbackQuery, state: FSMContext):
    month = int(callback.data.split(":")[1])
    data = await state.get_data()
    await state.update_data(month=month)
    await callback.message.edit_text("📅 Выберите день:", reply_markup=get_day_keyboard(data['year'], month))

@dp.callback_query(F.data.startswith("set_day:"))
async def process_day(callback: CallbackQuery, state: FSMContext):
    day = int(callback.data.split(":")[1])
    data = await state.get_data()
    date_str = f"{day:02d}.{data['month']:02d}.{data['year']}"
    
    if data.get("calendar_mode") == "edit":
        update_birthday_date_by_id(data['edit_b_id'], date_str)
        await state.clear()
        
        # Display the updated date
        year_val = data['year']
        date_display = f"{day:02d}.{data['month']:02d}" + (f".{year_val}" if year_val != 1004 else "")
        await callback.message.edit_text(f"✅ Дата обновлена на: {date_display}", reply_markup=get_main_menu())
    else:
        add_birthday(callback.from_user.id, data['name'], date_str, data.get('tg_username'))
        await state.clear()
        date_display = f"{day:02d}.{data['month']:02d}" + (f".{data['year']}" if data['year'] != 1004 else "")
        await callback.message.edit_text(f"✅ Добавлено: <b>{data['name']}</b> ({date_display})", reply_markup=get_main_menu())

# --- NAVIGATION BACK BUTTON HANDLERS FOR CALENDAR ---
@dp.callback_query(F.data == "back_to_decade")
async def back_to_decade_handler(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text("📅 Выберите десятилетие:", reply_markup=get_decade_keyboard())

@dp.callback_query(F.data == "back_to_year")
async def back_to_year_handler(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    decade = data.get('decade')
    if decade:
        await callback.message.edit_text("📅 Выберите год:", reply_markup=get_year_in_decade_keyboard(decade))
    else:
        await callback.message.edit_text("📅 Выберите десятилетие:", reply_markup=get_decade_keyboard())

@dp.callback_query(F.data == "back_to_month")
async def back_to_month_handler(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    is_yearless = data.get('year') == 1004
    await callback.message.edit_text("📅 Выберите месяц:", reply_markup=get_month_keyboard(is_yearless=is_yearless))

@dp.callback_query(F.data == "menu_start")
async def back_to_menu(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("<b>🎂 Birthday Notifier</b>", reply_markup=get_main_menu())

@dp.callback_query(F.data == "ignore")
async def ignore_callback(callback: CallbackQuery): 
    await callback.answer()

async def main():
    logging.basicConfig(level=logging.INFO)
    init_db()
    scheduler = AsyncIOScheduler()
    scheduler.add_job(check_birthdays, "interval", minutes=1, args=[bot])
    scheduler.start()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())

import asyncio
import os
import logging
import datetime
import re
import json
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command, StateFilter
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, ReplyKeyboardMarkup, KeyboardButton, BufferedInputFile
from aiogram.client.default import DefaultBotProperties
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from dotenv import load_dotenv
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from bot.database import init_db, add_birthday, get_all_birthdays, delete_birthday, update_birthday_info, get_user_settings, update_user_settings
from bot.scheduler import check_birthdays

load_dotenv()

TOKEN = os.getenv("BOT_TOKEN")
if not TOKEN:
    raise ValueError("No BOT_TOKEN provided in .env file")

bot = Bot(token=TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
dp = Dispatcher()

class AppStates(StatesGroup):
    waiting_for_name = State()
    waiting_for_decade = State()
    waiting_for_year = State()
    waiting_for_month = State()
    waiting_for_day = State()
    waiting_for_delete_index = State()
    waiting_for_edit_index = State()
    waiting_for_edit_data = State()
    waiting_for_notify_time = State()
    waiting_for_import = State()

def get_main_menu():
    keyboard = [
        [InlineKeyboardButton(text="➕ Добавить", callback_data="menu_add"), 
         InlineKeyboardButton(text="📅 Мой список", callback_data="menu_list")],
        [InlineKeyboardButton(text="🔥 Ближайшие", callback_data="menu_upcoming")],
        [InlineKeyboardButton(text="⚙️ Настройки", callback_data="menu_settings"),
         InlineKeyboardButton(text="💾 Бэкап", callback_data="menu_backup")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

@dp.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("<b>🎂 Birthday Notifier</b>\n\nЯ помогу вам не забыть про важные даты.\nВыберите действие в меню:", reply_markup=get_main_menu())

# --- SECTION: SETTINGS ---

@dp.callback_query(F.data == "menu_settings")
async def settings_main(callback: CallbackQuery):
    s = get_user_settings(callback.from_user.id)
    text = (f"⚙️ <b>Настройки уведомлений</b>\n\n"
            f"⏰ Время напоминаний: <b>{s['notify_time']}</b>\n"
            f"📅 Интервалы (дней до): <b>{', '.join([str(i) for i in s['intervals']])}</b>\n\n"
            "Здесь можно настроить, за сколько дней и в какое время я буду присылать уведомления.")
    
    keyboard = [
        [InlineKeyboardButton(text="⏰ Изменить время", callback_data="set_time")],
        [InlineKeyboardButton(text="🔔 Выбрать интервалы", callback_data="set_intervals")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="menu_start")]
    ]
    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard))

@dp.callback_query(F.data == "set_time")
async def set_time_start(callback: CallbackQuery, state: FSMContext):
    await state.set_state(AppStates.waiting_for_notify_time)
    await callback.message.edit_text("Введите время в формате ЧЧ:ММ (например, <code>10:00</code>):", 
                                     reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="❌ Отмена", callback_data="menu_settings")]]))

@dp.message(AppStates.waiting_for_notify_time)
async def process_set_time(message: Message, state: FSMContext):
    if re.match(r'^([01]\d|2[0-3]):([0-5]\d)$', message.text):
        update_user_settings(message.from_user.id, notify_time=message.text)
        await message.answer(f"✅ Время уведомлений изменено на <b>{message.text}</b>", reply_markup=get_main_menu())
        await state.clear()
    else:
        await message.answer("❌ Неверный формат. Введите время как ЧЧ:ММ (00:00 - 23:59):")

# --- SECTION: UPCOMING ---

@dp.callback_query(F.data == "menu_upcoming")
async def upcoming_birthdays(callback: CallbackQuery):
    birthdays = get_all_birthdays()
    user_birthdays = [b for b in birthdays if b[0] == callback.from_user.id]
    if not user_birthdays:
        return await callback.message.edit_text("ℹ️ Список пуст.", reply_markup=get_main_menu())
    
    now = datetime.datetime.now()
    this_month = []
    for _, name, b_date, tag in user_birthdays:
        dt = datetime.datetime.strptime(b_date, "%d.%m.%Y")
        if dt.month == now.month:
            this_month.append((name, b_date, tag, dt.day))
    
    this_month.sort(key=lambda x: x[3])
    
    if not this_month:
        text = "📅 <b>В этом месяце именинников нет.</b>"
    else:
        text = f"🎁 <b>Именинники в {now.strftime('%B')}:</b>\n\n"
        for name, b_date, tag, day in this_month:
            tag_str = f" ({tag})" if tag else ""
            text += f"• <b>{day:02d}.{now.month:02d}</b> — <b>{name}</b>{tag_str}\n"
            
    await callback.message.edit_text(text, reply_markup=get_main_menu())

# --- SECTION: BACKUP ---

@dp.callback_query(F.data == "menu_backup")
async def backup_menu(callback: CallbackQuery):
    keyboard = [
        [InlineKeyboardButton(text="📤 Экспорт в JSON", callback_data="backup_export")],
        [InlineKeyboardButton(text="📥 Импорт из JSON", callback_data="backup_import")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="menu_start")]
    ]
    await callback.message.edit_text("💾 <b>Резервное копирование</b>\n\nВы можете сохранить свои данные в файл или восстановить их.", reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard))

@dp.callback_query(F.data == "backup_export")
async def backup_export(callback: CallbackQuery):
    birthdays = get_all_birthdays()
    user_data = [{"name": b[1], "date": b[2], "tag": b[3]} for b in birthdays if b[0] == callback.from_user.id]
    
    if not user_data:
        return await callback.answer("❌ Нечего экспортировать", show_alert=True)
        
    json_data = json.dumps(user_data, ensure_ascii=False, indent=2)
    file = BufferedInputFile(json_data.encode('utf-8'), filename="birthdays_backup.json")
    await callback.message.answer_document(file, caption="✅ Ваш бэкап готов!")
    await callback.answer()

# --- REUSE PREVIOUS LOGIC (Add/List/Edit/Delete) ---
# (Helper for list)
def get_birthdays_list_text(user_id):
    birthdays = get_all_birthdays()
    user_birthdays = [b for b in birthdays if b[0] == user_id]
    if not user_birthdays: return None
    user_birthdays.sort(key=lambda x: x[1].lower())
    text = "📅 <b>Ваш список дней рождения:</b>\n\n"
    now = datetime.datetime.now()
    for i, (_, b_name, b_date, b_tag) in enumerate(user_birthdays, 1):
        try:
            bday_dt = datetime.datetime.strptime(b_date, "%d.%m.%Y")
            target_date = bday_dt.replace(year=now.year)
            if target_date < now.replace(hour=0, minute=0, second=0): target_date = target_date.replace(year=now.year + 1)
            age = target_date.year - bday_dt.year
            name_display = f'<a href="https://t.me/{b_tag.lstrip("@")}">{b_name}</a>' if b_tag else f'<b>{b_name}</b>'
            text += f"{i}. {name_display} — <code>{b_date}</code> (<b>{age}</b>)\n"
        except Exception: text += f"{i}. <b>{b_name}</b> — <code>{b_date}</code>\n"
    return text

@dp.callback_query(F.data == "menu_list")
async def menu_list_birthdays(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    text = get_birthdays_list_text(callback.from_user.id)
    if not text: return await callback.message.edit_text("ℹ️ Список пуст.", reply_markup=get_main_menu())
    keyboard = [
        [InlineKeyboardButton(text="🗑 Удалить", callback_data="menu_delete_index"),
         InlineKeyboardButton(text="✏️ Изменить", callback_data="menu_edit_index")],
        [InlineKeyboardButton(text="🔙 В главное меню", callback_data="menu_start")]
    ]
    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard), disable_web_page_preview=True)

@dp.callback_query(F.data == "menu_add")
async def menu_add_manual(callback: CallbackQuery, state: FSMContext):
    await state.set_state(AppStates.waiting_for_name)
    await callback.message.edit_text("📝 <b>Имя и Тег</b>\nВведите имя (и @тег через пробел):", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="❌ Отмена", callback_data="menu_start")]]))

@dp.callback_query(F.data == "menu_start")
async def back_to_menu(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("<b>🎂 Birthday Notifier</b>\n\nВыберите действие в меню:", reply_markup=get_main_menu())

# (Year/Month/Day Keyboards - identical to previous version)
def get_decade_keyboard():
    keyboard = []
    current_year = datetime.datetime.now().year
    start_decade = (current_year // 10) * 10
    for d in range(start_decade, start_decade - 80, -20):
        row = [InlineKeyboardButton(text=f"{i}s", callback_data=f"set_decade:{i}") for i in range(d, d - 20, -10)]
        keyboard.append(row)
    keyboard.append([InlineKeyboardButton(text="❌ Отмена", callback_data="menu_start")])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def get_year_in_decade_keyboard(decade):
    keyboard = []
    for y in range(decade + 9, decade - 1, -1):
        if (decade + 9 - y) % 5 == 0: keyboard.append([])
        keyboard[-1].append(InlineKeyboardButton(text=str(y), callback_data=f"set_year:{y}"))
    keyboard.append([InlineKeyboardButton(text="🔙 Назад", callback_data="menu_add_year_step")])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def get_month_keyboard():
    months = ["Янв", "Фев", "Мар", "Апр", "Май", "Июн", "Июл", "Авг", "Сен", "Окт", "Ноя", "Дек"]
    keyboard = []
    for i in range(0, 12, 3): keyboard.append([InlineKeyboardButton(text=months[m], callback_data=f"set_month:{m+1}") for m in range(i, i + 3)])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def get_day_keyboard(year, month):
    import calendar
    kb = []
    for week in calendar.monthcalendar(year, month):
        row = [InlineKeyboardButton(text=str(day) if day != 0 else " ", callback_data=f"set_day:{day}" if day != 0 else "ignore") for day in week]
        kb.append(row)
    return InlineKeyboardMarkup(inline_keyboard=kb)

# --- HANDLERS ---
@dp.callback_query(F.data.startswith("set_decade:"))
async def process_decade(callback: CallbackQuery, state: FSMContext):
    decade = int(callback.data.split(":")[1])
    await state.update_data(decade=decade)
    await callback.message.edit_text(f"📅 <b>Выберите год:</b>", reply_markup=get_year_in_decade_keyboard(decade))

@dp.callback_query(F.data.startswith("set_year:"))
async def process_year(callback: CallbackQuery, state: FSMContext):
    year = int(callback.data.split(":")[1])
    await state.update_data(year=year)
    await callback.message.edit_text("📅 <b>Выберите месяц:</b>", reply_markup=get_month_keyboard())

@dp.callback_query(F.data.startswith("set_month:"))
async def process_month(callback: CallbackQuery, state: FSMContext):
    month = int(callback.data.split(":")[1])
    data = await state.get_data()
    await state.update_data(month=month)
    await callback.message.edit_text(f"📅 <b>Выберите день:</b>", reply_markup=get_day_keyboard(data['year'], month))

@dp.callback_query(F.data.startswith("set_day:"))
async def process_day(callback: CallbackQuery, state: FSMContext):
    day = int(callback.data.split(":")[1])
    data = await state.get_data()
    date_str = f"{day:02d}.{data['month']:02d}.{data['year']}"
    add_birthday(callback.from_user.id, data['name'], date_str, data.get('tg_username'))
    await state.clear()
    await callback.message.edit_text(f"✅ Добавлено: <b>{data['name']}</b> ({date_str})", reply_markup=get_main_menu())

@dp.message(AppStates.waiting_for_name)
async def process_name(message: Message, state: FSMContext):
    text = message.text.strip()
    match = re.search(r'(@\w+)', text)
    await state.update_data(name=re.sub(r'(@\w+)', '', text).strip(), tg_username=match.group(1) if match else None)
    await state.set_state(AppStates.waiting_for_decade)
    await message.answer("📅 <b>Выберите десятилетие:</b>", reply_markup=get_decade_keyboard())

@dp.callback_query(F.data == "menu_delete_index")
async def delete_index_start(callback: CallbackQuery, state: FSMContext):
    await state.set_state(AppStates.waiting_for_delete_index)
    await callback.message.edit_text(get_birthdays_list_text(callback.from_user.id) + "\n🗑 <b>Номер для удаления:</b>", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="❌ Отмена", callback_data="menu_list")]]))

@dp.message(AppStates.waiting_for_delete_index)
async def process_delete(message: Message, state: FSMContext):
    if message.text.isdigit():
        birthdays = sorted([b for b in get_all_birthdays() if b[0] == message.from_user.id], key=lambda x: x[1].lower())
        idx = int(message.text)
        if 1 <= idx <= len(birthdays):
            delete_birthday(message.from_user.id, birthdays[idx-1][1])
            await message.answer("✅ Удалено!", reply_markup=get_main_menu())
        else: await message.answer("❌ Ошибка в номере.")
    await state.clear()

async def main():
    logging.basicConfig(level=logging.INFO)
    init_db()
    scheduler = AsyncIOScheduler()
    scheduler.add_job(check_birthdays, "interval", minutes=1, args=[bot])
    scheduler.start()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())

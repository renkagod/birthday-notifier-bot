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

from bot.database import init_db, add_birthday, get_birthdays_for_user, delete_birthday, update_birthday_info, get_user_settings, update_user_settings
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

def get_sorted_birthdays(user_id, sort_by='name'):
    birthdays = get_birthdays_for_user(user_id)
    if sort_by == 'name':
        return sorted(birthdays, key=lambda x: x[1].lower())
    
    now = datetime.datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    def get_upcoming_date(b):
        try:
            b_date = b[2]
            bday_dt = datetime.datetime.strptime(b_date, "%d.%m.%Y")
            target_date = bday_dt.replace(year=now.year)
            if target_date < now:
                target_date = target_date.replace(year=now.year + 1)
            return target_date
        except: return datetime.datetime.max
            
    return sorted(birthdays, key=lambda x: (get_upcoming_date(x), x[1].lower()))

def get_birthdays_list_text(user_id, sort_by='name'):
    user_birthdays = get_sorted_birthdays(user_id, sort_by)
    if not user_birthdays: return None
    
    title = "📅 <b>Ваш список (по имени):</b>\n\n" if sort_by == 'name' else "📅 <b>Ваш список (по дате):</b>\n\n"
    text = title
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

@dp.callback_query(F.data == "set_time")
async def set_time_start(callback: CallbackQuery, state: FSMContext):
    await state.set_state(AppStates.waiting_for_notify_time)
    await callback.message.edit_text("Введите время в формате ЧЧ:ММ (например, <code>10:00</code>):", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="❌ Отмена", callback_data="menu_settings")]]))

@dp.message(AppStates.waiting_for_notify_time)
async def process_set_time(message: Message, state: FSMContext):
    if re.match(r'^([01]\d|2[0-3]):([0-5]\d)$', message.text):
        update_user_settings(message.from_user.id, notify_time=message.text)
        await message.answer(f"✅ Время уведомлений изменено на <b>{message.text}</b>", reply_markup=get_main_menu())
        await state.clear()
    else: await message.answer("❌ Неверный формат. Введите время как ЧЧ:ММ:")

# --- UPCOMING ---
@dp.callback_query(F.data == "menu_upcoming")
async def upcoming_birthdays(callback: CallbackQuery):
    user_birthdays = get_birthdays_for_user(callback.from_user.id)
    if not user_birthdays: return await callback.message.edit_text("ℹ️ Список пуст.", reply_markup=get_main_menu())
    
    now = datetime.datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    upcoming = []
    
    for _, name, b_date, tag in user_birthdays:
        try:
            bday_dt = datetime.datetime.strptime(b_date, "%d.%m.%Y")
            target_date = bday_dt.replace(year=now.year)
            if target_date < now:
                target_date = target_date.replace(year=now.year + 1)
            
            days_until = (target_date - now).days
            if days_until <= 30: # Показываем на ближайшие 30 дней
                upcoming.append({
                    'name': name,
                    'date': target_date,
                    'tag': tag,
                    'days_until': days_until,
                    'age': target_date.year - bday_dt.year
                })
        except Exception: continue
        
    upcoming.sort(key=lambda x: x['days_until'])
    
    if not upcoming:
        text = "📅 <b>В ближайшие 30 дней именинников нет.</b>"
    else:
        text = "🔥 <b>Ближайшие дни рождения:</b>\n\n"
        for item in upcoming:
            date_str = item['date'].strftime("%d.%m")
            days_text = ""
            if item['days_until'] == 0: days_text = " (<b>Сегодня!</b> 🥳)"
            elif item['days_until'] == 1: days_text = " (Завтра!)"
            else: days_text = f" (через {item['days_until']} дн.)"
            
            tag_display = f' ({item["tag"]})' if item["tag"] else ''
            text += f"• <b>{date_str}</b> — <b>{item['name']}</b>{tag_display}{days_text}\n"
            
    await callback.message.edit_text(text, reply_markup=get_main_menu())

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
                add_birthday(message.from_user.id, item['name'], item['date'], item.get('tag'))
                count += 1
        await message.answer(f"✅ Импортировано <b>{count}</b> записей!", reply_markup=get_main_menu())
        await state.clear()
    except Exception as e: await message.answer(f"❌ Ошибка: {e}", reply_markup=get_main_menu())

# --- LIST / EDIT / DELETE ---
@dp.callback_query(F.data.startswith("menu_list"))
async def menu_list_birthdays(callback: CallbackQuery, state: FSMContext):
    sort_by = 'name'
    if ":" in callback.data:
        sort_by = callback.data.split(":")[1]
    
    await state.update_data(current_sort=sort_by)
    text = get_birthdays_list_text(callback.from_user.id, sort_by)
    
    if not text: 
        return await callback.message.edit_text("ℹ️ Список пуст.", reply_markup=get_main_menu())
    
    sort_label = "🔤 По имени" if sort_by == 'name' else "📅 По дате"
    next_sort = 'date' if sort_by == 'name' else 'name'
    next_label = "🔄 Сортировать по дате" if sort_by == 'name' else "🔄 Сортировать по имени"
    
    keyboard = [
        [InlineKeyboardButton(text=next_label, callback_data=f"menu_list:{next_sort}")],
        [InlineKeyboardButton(text="🗑 Удалить", callback_data="menu_delete_index"), 
         InlineKeyboardButton(text="✏️ Изменить", callback_data="menu_edit_index")],
        [InlineKeyboardButton(text="🔙 В главное меню", callback_data="menu_start")]
    ]
    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard), disable_web_page_preview=True)

@dp.callback_query(F.data == "menu_delete_index")
async def delete_index_start(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    sort_by = data.get('current_sort', 'name')
    await state.set_state(AppStates.waiting_for_delete_index)
    await callback.message.edit_text(get_birthdays_list_text(callback.from_user.id, sort_by) + "\n🗑 Введите номер для удаления:", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="❌ Отмена", callback_data="menu_list")]]), disable_web_page_preview=True)

@dp.message(AppStates.waiting_for_delete_index)
async def process_delete(message: Message, state: FSMContext):
    if message.text.isdigit():
        data = await state.get_data()
        sort_by = data.get('current_sort', 'name')
        birthdays = get_sorted_birthdays(message.from_user.id, sort_by)
        idx = int(message.text)
        if 1 <= idx <= len(birthdays):
            delete_birthday(message.from_user.id, birthdays[idx-1][1])
            await message.answer(f"✅ Удалено: <b>{birthdays[idx-1][1]}</b>", reply_markup=get_main_menu())
        else: await message.answer("❌ Ошибка в номере.", reply_markup=get_main_menu())
    else: await message.answer("❌ Введите число.", reply_markup=get_main_menu())
    await state.clear()

@dp.callback_query(F.data == "menu_edit_index")
async def edit_index_start(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    sort_by = data.get('current_sort', 'name')
    await state.set_state(AppStates.waiting_for_edit_index)
    await callback.message.edit_text(get_birthdays_list_text(callback.from_user.id, sort_by) + "\n✏️ Введите номер для изменения:", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="❌ Отмена", callback_data="menu_list")]]), disable_web_page_preview=True)

@dp.message(AppStates.waiting_for_edit_index)
async def process_edit_index(message: Message, state: FSMContext):
    if message.text.isdigit():
        data = await state.get_data()
        sort_by = data.get('current_sort', 'name')
        birthdays = get_sorted_birthdays(message.from_user.id, sort_by)
        idx = int(message.text)
        if 1 <= idx <= len(birthdays):
            await state.update_data(old_name=birthdays[idx-1][1])
            await state.set_state(AppStates.waiting_for_edit_data)
            await message.answer(f"Выбрано: <b>{birthdays[idx-1][1]}</b>\nВведите новое имя и @тег:")
            return
    await message.answer("❌ Ошибка.", reply_markup=get_main_menu())
    await state.clear()

@dp.message(AppStates.waiting_for_edit_data)
async def process_edit_data(message: Message, state: FSMContext):
    text = message.text.strip()
    match = re.search(r'(@\w+)', text)
    new_tag = match.group(1) if match else None
    new_name = re.sub(r'(@\w+)', '', text).strip()
    data = await state.get_data()
    update_birthday_info(message.from_user.id, data['old_name'], new_name, new_tag)
    await message.answer(f"✅ Обновлено!", reply_markup=get_main_menu())
    await state.clear()

# --- ADD BIRTHDAY FLOW ---
def get_decade_keyboard():
    keyboard = []
    curr = datetime.datetime.now().year
    start = (curr // 10) * 10
    for d in range(start, start - 80, -20):
        keyboard.append([InlineKeyboardButton(text=f"{i}s", callback_data=f"set_decade:{i}") for i in range(d, d - 20, -10)])
    keyboard.append([InlineKeyboardButton(text="❌ Отмена", callback_data="menu_start")])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def get_year_in_decade_keyboard(decade):
    keyboard = []
    for y in range(decade + 9, decade - 1, -1):
        if (decade + 9 - y) % 5 == 0: keyboard.append([])
        keyboard[-1].append(InlineKeyboardButton(text=str(y), callback_data=f"set_year:{y}"))
    keyboard.append([InlineKeyboardButton(text="🔙 Назад", callback_data="menu_add")])
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
        kb.append([InlineKeyboardButton(text=str(day) if day != 0 else " ", callback_data=f"set_day:{day}" if day != 0 else "ignore") for day in week])
    return InlineKeyboardMarkup(inline_keyboard=kb)

@dp.callback_query(F.data == "menu_add")
async def menu_add_manual(callback: CallbackQuery, state: FSMContext):
    await state.set_state(AppStates.waiting_for_name)
    await callback.message.edit_text("📝 Введите имя (и @тег):", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="❌ Отмена", callback_data="menu_start")]]))

@dp.callback_query(F.data == "menu_contact")
async def menu_add_contact(callback: CallbackQuery):
    from aiogram.types import KeyboardButtonRequestUsers
    kb = [[KeyboardButton(text="👤 Выбрать контакт", request_users=KeyboardButtonRequestUsers(request_id=1, user_count=1))]]
    await callback.message.answer("Выберите контакт:", reply_markup=ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True, one_time_keyboard=True))

@dp.message(F.user_shared)
async def process_shared_user(message: Message, state: FSMContext):
    await state.set_state(AppStates.waiting_for_name)
    await message.answer("Введите имя (и @тег):", reply_markup=types.ReplyKeyboardRemove())

@dp.message(F.contact)
async def process_contact(message: Message, state: FSMContext):
    name = f"{message.contact.first_name} {message.contact.last_name or ''}".strip()
    await state.update_data(name=name)
    await state.set_state(AppStates.waiting_for_decade)
    await message.answer(f"Имя: <b>{name}</b>\nВыберите десятилетие:", reply_markup=get_decade_keyboard())

@dp.message(AppStates.waiting_for_name)
async def process_name(message: Message, state: FSMContext):
    text = message.text.strip()
    match = re.search(r'(@\w+)', text)
    await state.update_data(name=re.sub(r'(@\w+)', '', text).strip(), tg_username=match.group(1) if match else None)
    await state.set_state(AppStates.waiting_for_decade)
    await message.answer("📅 Выберите десятилетие:", reply_markup=get_decade_keyboard())

@dp.callback_query(F.data.startswith("set_decade:"))
async def process_decade(callback: CallbackQuery, state: FSMContext):
    decade = int(callback.data.split(":")[1])
    await state.update_data(decade=decade)
    await callback.message.edit_text("📅 Выберите год:", reply_markup=get_year_in_decade_keyboard(decade))

@dp.callback_query(F.data.startswith("set_year:"))
async def process_year(callback: CallbackQuery, state: FSMContext):
    await state.update_data(year=int(callback.data.split(":")[1]))
    await callback.message.edit_text("📅 Выберите месяц:", reply_markup=get_month_keyboard())

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
    add_birthday(callback.from_user.id, data['name'], date_str, data.get('tg_username'))
    await state.clear()
    await callback.message.edit_text(f"✅ Добавлено: <b>{data['name']}</b> ({date_str})", reply_markup=get_main_menu())

@dp.callback_query(F.data == "menu_start")
async def back_to_menu(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("<b>🎂 Birthday Notifier</b>", reply_markup=get_main_menu())

@dp.callback_query(F.data == "ignore")
async def ignore_callback(callback: CallbackQuery): await callback.answer()

async def main():
    logging.basicConfig(level=logging.INFO)
    init_db()
    scheduler = AsyncIOScheduler()
    scheduler.add_job(check_birthdays, "interval", minutes=1, args=[bot])
    scheduler.start()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())

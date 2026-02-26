import asyncio
import os
import logging
import datetime
import re
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command, StateFilter
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, ReplyKeyboardMarkup, KeyboardButton
from aiogram.client.default import DefaultBotProperties
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from dotenv import load_dotenv
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from bot.database import init_db, add_birthday, get_all_birthdays, delete_birthday
from bot.scheduler import check_birthdays

load_dotenv()

TOKEN = os.getenv("BOT_TOKEN")
if not TOKEN:
    raise ValueError("No BOT_TOKEN provided in .env file")

bot = Bot(token=TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
dp = Dispatcher()

class AddBirthday(StatesGroup):
    waiting_for_name = State()
    waiting_for_decade = State()
    waiting_for_year = State()
    waiting_for_month = State()
    waiting_for_day = State()
    waiting_for_delete_index = State()

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
        if (decade + 9 - y) % 5 == 0:
            row = []
            keyboard.append(row)
        row.append(InlineKeyboardButton(text=str(y), callback_data=f"set_year:{y}"))
    keyboard.append([InlineKeyboardButton(text="🔙 К десятилетиям", callback_data="menu_add_year_step")])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def get_month_keyboard():
    months = ["Янв", "Фев", "Мар", "Апр", "Май", "Июн", "Июл", "Авг", "Сен", "Окт", "Ноя", "Дек"]
    keyboard = []
    for i in range(0, 12, 3):
        row = [InlineKeyboardButton(text=months[m], callback_data=f"set_month:{m+1}") for m in range(i, i + 3)]
        keyboard.append(row)
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def get_day_keyboard(year, month):
    import calendar
    keyboard = []
    month_calendar = calendar.monthcalendar(year, month)
    for week in month_calendar:
        row = []
        for day in week:
            if day == 0:
                row.append(InlineKeyboardButton(text=" ", callback_data="ignore"))
            else:
                row.append(InlineKeyboardButton(text=str(day), callback_data=f"set_day:{day}"))
        keyboard.append(row)
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def get_main_menu():
    keyboard = [
        [InlineKeyboardButton(text="➕ Добавить вручную", callback_data="menu_add")],
        [InlineKeyboardButton(text="👤 Выбрать из контактов", callback_data="menu_contact")],
        [InlineKeyboardButton(text="📅 Мой список", callback_data="menu_list")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

@dp.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("<b>🎂 Birthday Notifier</b>\n\nЯ помогу вам не забыть про важные даты.\nВыберите действие в меню:", reply_markup=get_main_menu())

@dp.callback_query(F.data == "menu_add")
async def menu_add_manual(callback: CallbackQuery, state: FSMContext):
    await state.set_state(AddBirthday.waiting_for_name)
    await callback.message.edit_text("📝 <b>Шаг 1: Имя и Тег</b>\n\nВведите имя человека.\n<i>Можно также добавить @username, чтобы я мог тегнуть его в уведомлении.</i>\n\nПример: <code>Иван @vanya</code>", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="❌ Отмена", callback_data="menu_start")]]))
    await callback.answer()

@dp.callback_query(F.data == "menu_contact")
async def menu_add_contact(callback: CallbackQuery):
    from aiogram.types import KeyboardButtonRequestUsers
    kb = [[KeyboardButton(text="👤 Выбрать контакт", request_users=KeyboardButtonRequestUsers(request_id=1, user_count=1))]]
    markup = ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True, one_time_keyboard=True)
    await callback.message.answer("Выберите человека из вашей записной книжки:", reply_markup=markup)
    await callback.answer()

@dp.message(F.user_shared)
async def process_shared_user(message: Message, state: FSMContext):
    await state.set_state(AddBirthday.waiting_for_name)
    await message.answer("✅ Контакт выбран!\n\nТеперь введите <b>имя</b> для этого человека (и по желанию @тег):", reply_markup=types.ReplyKeyboardRemove())

@dp.message(AddBirthday.waiting_for_name)
async def process_name(message: Message, state: FSMContext):
    text = message.text.strip()
    username_match = re.search(r'(@\w+)', text)
    tg_username = username_match.group(1) if username_match else None
    name = re.sub(r'(@\w+)', '', text).strip()
    await state.update_data(name=name, tg_username=tg_username)
    await state.set_state(AddBirthday.waiting_for_decade)
    await message.answer(f"👤 Имя: <b>{name}</b>" + (f"\n🔗 Тег: <b>{tg_username}</b>" if tg_username else "") + "\n\n📅 <b>Шаг 2: Выберите десятилетие рождения:</b>", reply_markup=get_decade_keyboard())

@dp.callback_query(F.data == "menu_add_year_step")
@dp.callback_query(F.data.startswith("set_decade:"))
async def process_decade(callback: CallbackQuery, state: FSMContext):
    if callback.data == "menu_add_year_step":
        data = await state.get_data()
        decade = data.get("decade")
    else:
        decade = int(callback.data.split(":")[1])
        await state.update_data(decade=decade)
    await state.set_state(AddBirthday.waiting_for_year)
    await callback.message.edit_text(f"📅 <b>Выберите год из {decade}-х:</b>", reply_markup=get_year_in_decade_keyboard(decade))
    await callback.answer()

@dp.callback_query(F.data.startswith("set_year:"))
async def process_year(callback: CallbackQuery, state: FSMContext):
    year = int(callback.data.split(":")[1])
    await state.update_data(year=year)
    await state.set_state(AddBirthday.waiting_for_month)
    await callback.message.edit_text(f"📅 Год: <b>{year}</b>\n\n<b>Шаг 3: Выберите месяц:</b>", reply_markup=get_month_keyboard())
    await callback.answer()

@dp.callback_query(F.data.startswith("set_month:"))
async def process_month(callback: CallbackQuery, state: FSMContext):
    month = int(callback.data.split(":")[1])
    data = await state.get_data()
    year = data.get("year")
    await state.update_data(month=month)
    await state.set_state(AddBirthday.waiting_for_day)
    await callback.message.edit_text(f"📅 Год: <b>{year}</b>, Месяц: <b>{month:02d}</b>\n\n<b>Шаг 4: Выберите день:</b>", reply_markup=get_day_keyboard(year, month))
    await callback.answer()

@dp.callback_query(F.data.startswith("set_day:"))
async def process_day_selection(callback: CallbackQuery, state: FSMContext):
    day = int(callback.data.split(":")[1])
    data = await state.get_data()
    name = data.get("name")
    tg_username = data.get("tg_username")
    date_str = f"{day:02d}.{data.get('month'):02d}.{data.get('year')}"
    add_birthday(callback.from_user.id, name, date_str, tg_username)
    await state.clear()
    success_text = f"✅ <b>Готово!</b>\n\nИмя: <b>{name}</b>"
    if tg_username: success_text += f"\nТег: <b>{tg_username}</b>"
    success_text += f"\nДата: <b>{date_str}</b>"
    await callback.message.edit_text(success_text, reply_markup=get_main_menu())
    await callback.answer()

@dp.callback_query(F.data == "menu_list")
async def menu_list_birthdays(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    birthdays = get_all_birthdays()
    user_birthdays = [b for b in birthdays if b[0] == callback.from_user.id]
    if not user_birthdays:
        await callback.message.edit_text("ℹ️ В вашем списке пока нет записей.", reply_markup=get_main_menu())
        return
    
    # Sort alphabetically by name
    user_birthdays.sort(key=lambda x: x[1].lower())
    
    text = "📅 <b>Ваш список дней рождения:</b>\n\n"
    now = datetime.datetime.now()
    
    for i, (_, b_name, b_date, b_tag) in enumerate(user_birthdays, 1):
        try:
            bday_dt = datetime.datetime.strptime(b_date, "%d.%m.%Y")
            target_date = bday_dt.replace(year=now.year)
            if target_date < now.replace(hour=0, minute=0, second=0):
                target_date = target_date.replace(year=now.year + 1)
            age = target_date.year - bday_dt.year
            
            tag_str = f" ({b_tag})" if b_tag else ""
            # Format: 1. Name (@tag) — 27.02.2005 (21)
            text += f"{i}. <b>{b_name}</b>{tag_str} — <code>{b_date}</code> (<b>{age}</b>)\n"
        except Exception:
            text += f"{i}. <b>{b_name}</b> — <code>{b_date}</code>\n"
    
    keyboard = [
        [InlineKeyboardButton(text="🗑 Удалить по номеру", callback_data="menu_delete_index")],
        [InlineKeyboardButton(text="🔙 В главное меню", callback_data="menu_start")]
    ]
    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard))
    await callback.answer()

@dp.callback_query(F.data == "menu_delete_index")
async def delete_index_start(callback: CallbackQuery, state: FSMContext):
    await state.set_state(AddBirthday.waiting_for_delete_index)
    await callback.message.edit_text("Введите <b>номер</b> записи для удаления:", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="❌ Отмена", callback_data="menu_list")]]))
    await callback.answer()

@dp.message(AddBirthday.waiting_for_delete_index)
async def process_delete_index(message: Message, state: FSMContext):
    if not message.text or not message.text.isdigit():
        await state.clear()
        await message.answer("Удаление отменено.", reply_markup=get_main_menu())
        return
    idx = int(message.text)
    birthdays = get_all_birthdays()
    user_birthdays = [b for b in birthdays if b[0] == message.from_user.id]
    user_birthdays.sort(key=lambda x: x[1].lower())
    if 1 <= idx <= len(user_birthdays):
        target = user_birthdays[idx-1]
        delete_birthday(message.from_user.id, target[1])
        await message.answer(f"✅ Запись <b>{target[1]}</b> удалена!", reply_markup=get_main_menu())
    else:
        await message.answer(f"❌ Номер {idx} не найден.", reply_markup=get_main_menu())
    await state.clear()

@dp.callback_query(F.data == "menu_start")
async def back_to_menu(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("<b>🎂 Birthday Notifier</b>\n\nВыберите действие в меню:", reply_markup=get_main_menu())
    await callback.answer()

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

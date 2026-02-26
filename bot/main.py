import asyncio
import os
import logging
import datetime
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
    waiting_for_date = State()

def get_calendar_keyboard(year=None, month=None):
    if year is None: year = datetime.datetime.now().year
    if month is None: month = datetime.datetime.now().month
    
    keyboard = []
    # Month/Year header
    keyboard.append([InlineKeyboardButton(text=f"{datetime.date(year, month, 1).strftime('%B %Y')}", callback_data="ignore")])
    
    # Days of week
    days = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
    keyboard.append([InlineKeyboardButton(text=d, callback_data="ignore") for d in days])
    
    # Calendar logic
    import calendar
    month_calendar = calendar.monthcalendar(year, month)
    for week in month_calendar:
        row = []
        for day in week:
            if day == 0:
                row.append(InlineKeyboardButton(text=" ", callback_data="ignore"))
            else:
                row.append(InlineKeyboardButton(text=str(day), callback_data=f"date:{day}.{month}.{year}"))
        keyboard.append(row)
    
    # Navigation
    prev_m = month - 1 if month > 1 else 12
    prev_y = year if month > 1 else year - 1
    next_m = month + 1 if month < 12 else 1
    next_y = year if month < 12 else year + 1
    
    keyboard.append([
        InlineKeyboardButton(text="<", callback_data=f"cal:{prev_y}:{prev_m}"),
        InlineKeyboardButton(text=">", callback_data=f"cal:{next_y}:{next_m}")
    ])
    
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

@dp.message(Command("start"))
async def cmd_start(message: Message):
    kb = [
        [KeyboardButton(text="➕ Добавить день рождения", request_contact=False)],
        [KeyboardButton(text="👤 Поделиться контактом", request_contact=True)]
    ]
    markup = ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)
    
    await message.answer(
        "<b>👋 Привет! Я бот для уведомлений о днях рождения.</b>\n\n"
        "Вы можете добавить человека вручную или поделиться контактом из записной книжки.",
        reply_markup=markup
    )

@dp.message(F.text == "➕ Добавить день рождения")
async def manual_add(message: Message, state: FSMContext):
    await state.set_state(AddBirthday.waiting_for_name)
    await message.answer("Введите имя именинника:", reply_markup=types.ReplyKeyboardRemove())

@dp.message(F.contact)
async def process_contact(message: Message, state: FSMContext):
    contact = message.contact
    name = f"{contact.first_name} {contact.last_name or ''}".strip()
    await state.update_data(name=name)
    await state.set_state(AddBirthday.waiting_for_date)
    await message.answer(f"Записываем: <b>{name}</b>\nТеперь выберите дату рождения:", 
                         reply_markup=get_calendar_keyboard(),
                         reply_markup_remove=types.ReplyKeyboardRemove())

@dp.message(AddBirthday.waiting_for_name)
async def process_name(message: Message, state: FSMContext):
    await state.update_data(name=message.text)
    await state.set_state(AddBirthday.waiting_for_date)
    await message.answer(f"Имя: <b>{message.text}</b>\nВыберите дату рождения:", 
                         reply_markup=get_calendar_keyboard())

@dp.callback_query(F.data.startswith("cal:"))
async def change_calendar(callback: CallbackQuery):
    _, year, month = callback.data.split(":")
    await callback.message.edit_reply_markup(reply_markup=get_calendar_keyboard(int(year), int(month)))

@dp.callback_query(F.data.startswith("date:"))
async def process_date_selection(callback: CallbackQuery, state: FSMContext):
    date_str = callback.data.split(":")[1]
    # Normalize date to DD.MM.YYYY
    d, m, y = date_str.split(".")
    date_str = f"{int(d):02d}.{int(m):02d}.{y}"
    
    data = await state.get_data()
    name = data.get("name")
    
    add_birthday(callback.from_user.id, name, date_str)
    await state.clear()
    
    await callback.message.edit_text(f"✅ Добавлен день рождения для <b>{name}</b> на {date_str}!")
    await callback.answer()

@dp.message(Command("add"))
async def cmd_add(message: Message, state: FSMContext):
    args = message.text.split(maxsplit=2)
    if len(args) < 3:
        return await message.answer("❌ Используйте меню или формат: <code>/add [Имя] [ДД.ММ.ГГГГ]</code>")
    
    name, date_str = args[1], args[2]
    try:
        datetime.datetime.strptime(date_str, "%d.%m.%Y")
        add_birthday(message.from_user.id, name, date_str)
        await message.answer(f"✅ Добавлен день рождения для <b>{name}</b> на {date_str}!")
    except ValueError:
        await message.answer("❌ Ошибка в формате даты. Используй ДД.ММ.ГГГГ")

@dp.message(Command("list"))
async def cmd_list(message: Message):
    birthdays = get_all_birthdays()
    user_birthdays = [b for b in birthdays if b[0] == message.from_user.id]
    
    if not user_birthdays:
        return await message.answer("ℹ️ Твой список пуст.")
    
    text = "📅 <b>Твои дни рождения:</b>\n\n"
    keyboard = []
    
    now = datetime.datetime.now()
    for _, name, date_str in user_birthdays:
        try:
            bday_dt = datetime.datetime.strptime(date_str, "%d.%m.%Y")
            target_date = bday_dt.replace(year=now.year)
            if target_date < now.replace(hour=0, minute=0, second=0):
                target_date = target_date.replace(year=now.year + 1)
            age = target_date.year - bday_dt.year
            text += f"• <b>{name}</b>: {date_str} (исполнится <b>{age}</b>)\n"
        except Exception:
            text += f"• <b>{name}</b>: {date_str}\n"
        keyboard.append([InlineKeyboardButton(text=f"🗑 Удалить {name}", callback_data=f"del:{name}")])
    
    markup = InlineKeyboardMarkup(inline_keyboard=keyboard)
    await message.answer(text, reply_markup=markup)

@dp.callback_query(F.data.startswith("del:"))
async def process_delete_callback(callback: CallbackQuery):
    name = callback.data.split(":")[1]
    delete_birthday(callback.from_user.id, name)
    
    # Update the list message
    await callback.answer(f"Запись '{name}' удалена")
    
    # Re-fetch and update the message
    birthdays = get_all_birthdays()
    user_birthdays = [b for b in birthdays if b[0] == callback.from_user.id]
    
    if not user_birthdays:
        await callback.message.edit_text("ℹ️ Твой список пуст.")
        return

    text = "📅 <b>Твои дни рождения:</b>\n\n"
    keyboard = []
    now = datetime.datetime.now()
    for _, b_name, b_date in user_birthdays:
        try:
            bday_dt = datetime.datetime.strptime(b_date, "%d.%m.%Y")
            target_date = bday_dt.replace(year=now.year)
            if target_date < now.replace(hour=0, minute=0, second=0):
                target_date = target_date.replace(year=now.year + 1)
            age = target_date.year - bday_dt.year
            text += f"• <b>{b_name}</b>: {b_date} (исполнится <b>{age}</b>)\n"
        except Exception:
            text += f"• <b>{b_name}</b>: {b_date}\n"
        keyboard.append([InlineKeyboardButton(text=f"🗑 Удалить {b_name}", callback_data=f"del:{b_name}")])
    
    markup = InlineKeyboardMarkup(inline_keyboard=keyboard)
    await callback.message.edit_text(text, reply_markup=markup)

@dp.message(Command("delete"))
async def cmd_delete(message: Message):
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        return await message.answer("❌ Формат: /delete [Имя]")
    
    name = args[1]
    delete_birthday(message.from_user.id, name)
    await message.answer(f"🗑 Удалена запись для {name}")

async def main():
    logging.basicConfig(level=logging.INFO)
    init_db()
    
    scheduler = AsyncIOScheduler()
    scheduler.add_job(check_birthdays, "interval", minutes=1, args=[bot])
    scheduler.start()
    
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())

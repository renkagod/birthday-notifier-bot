import asyncio
import os
import logging
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from dotenv import load_dotenv
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from bot.database import init_db, add_birthday, get_all_birthdays, delete_birthday
from bot.scheduler import check_birthdays

load_dotenv()

TOKEN = os.getenv("BOT_TOKEN")
if not TOKEN:
    raise ValueError("No BOT_TOKEN provided in .env file")

bot = Bot(token=TOKEN, parse_mode="HTML")
dp = Dispatcher()

@dp.message(Command("start"))
async def cmd_start(message: Message):
    await message.answer(
        "<b>👋 Привет! Я бот для уведомлений о днях рождения.</b>\n\n"
        "Команды:\n"
        "<code>/add [Имя] [ДД.ММ.ГГГГ]</code> — добавить ДР\n"
        "<code>/list</code> — список всех ДР\n"
        "<code>/delete [Имя]</code> — удалить запись"
    )

@dp.message(Command("add"))
async def cmd_add(message: Message):
    args = message.text.split(maxsplit=2)
    if len(args) < 3:
        return await message.answer("❌ Формат: <code>/add [Имя] [ДД.ММ.ГГГГ]</code>")
    
    name = args[1]
    date_str = args[2]
    
    try:
        import datetime
        datetime.datetime.strptime(date_str, "%d.%m.%Y")
        add_birthday(message.from_user.id, name, date_str)
        await message.answer(f"✅ Добавлен день рождения для <b>{name}</b> на {date_str}!")
    except ValueError:
        await message.answer("❌ Ошибка в формате даты. Используй ДД.ММ.ГГГГ (например <code>25.05.1990</code>)")

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

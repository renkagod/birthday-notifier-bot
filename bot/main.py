import asyncio
import os
import logging
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import Message
from dotenv import load_dotenv
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from bot.database import init_db, add_birthday, get_all_birthdays, delete_birthday
from bot.scheduler import check_birthdays

load_dotenv()

TOKEN = os.getenv("BOT_TOKEN")
if not TOKEN:
    raise ValueError("No BOT_TOKEN provided in .env file")

bot = Bot(token=TOKEN)
dp = Dispatcher()

@dp.message(Command("start"))
async def cmd_start(message: Message):
    await message.answer(
        "👋 Привет! Я бот для уведомлений о днях рождения.\n\n"
        "Команды:\n"
        "/add [Имя] [ДД.ММ.ГГГГ] - добавить ДР\n"
        "/list - список всех ДР\n"
        "/delete [Имя] - удалить запись"
    )

@dp.message(Command("add"))
async def cmd_add(message: Message):
    args = message.text.split(maxsplit=2)
    if len(args) < 3:
        return await message.answer("❌ Формат: /add [Имя] [ДД.ММ.ГГГГ]")
    
    name = args[1]
    date_str = args[2]
    
    try:
        # Validate format
        import datetime
        datetime.datetime.strptime(date_str, "%d.%m.%Y")
        add_birthday(message.from_user.id, name, date_str)
        await message.answer(f"✅ Добавлен день рождения для {name} на {date_str}!")
    except ValueError:
        await message.answer("❌ Ошибка в формате даты. Используй ДД.ММ.ГГГГ (например 25.05.1990)")

@dp.message(Command("list"))
async def cmd_list(message: Message):
    birthdays = get_all_birthdays()
    user_birthdays = [b for b in birthdays if b[0] == message.from_user.id]
    
    if not user_birthdays:
        return await message.answer("ℹ️ Твой список пуст.")
    
    text = "📅 Твои дни рождения:\n" + "\n".join([f"• {b[1]}: {b[2]}" for b in user_birthdays])
    await message.answer(text)

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

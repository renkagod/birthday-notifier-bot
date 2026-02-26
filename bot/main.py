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
    waiting_for_year = State()
    waiting_for_month = State()
    waiting_for_day = State()

def get_year_keyboard():
    keyboard = []
    current_year = datetime.datetime.now().year
    # Show last 80 years in rows of 4
    for y in range(current_year, current_year - 80, -4):
        row = [InlineKeyboardButton(text=str(year), callback_data=f"set_year:{year}") for year in range(y, y - 4, -1)]
        keyboard.append(row)
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def get_month_keyboard(year):
    months = [
        "Янв", "Фев", "Мар", "Апр", "Май", "Июн",
        "Июл", "Авг", "Сен", "Окт", "Ноя", "Дек"
    ]
    keyboard = []
    for i in range(0, 12, 3):
        row = [InlineKeyboardButton(text=months[m], callback_data=f"set_month:{year}:{m+1}") for m in range(i, i + 3)]
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
                row.append(InlineKeyboardButton(text=str(day), callback_data=f"set_day:{day}.{month}.{year}"))
        keyboard.append(row)
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def get_main_menu():
    keyboard = [
        [InlineKeyboardButton(text="➕ Добавить вручную", callback_data="menu_add")],
        [InlineKeyboardButton(text="👤 Добавить через контакт", callback_data="menu_contact")],
        [InlineKeyboardButton(text="📅 Список всех ДР", callback_data="menu_list")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

@dp.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "<b>👋 Привет! Я бот для уведомлений о днях рождения.</b>\n\n"
        "Выберите действие:",
        reply_markup=get_main_menu()
    )

@dp.callback_query(F.data == "menu_add")
async def menu_add_manual(callback: CallbackQuery, state: FSMContext):
    await state.set_state(AddBirthday.waiting_for_name)
    await callback.message.edit_text("Введите имя именинника:", 
                                     reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                                         [InlineKeyboardButton(text="❌ Отмена", callback_data="menu_start")]
                                     ]))
    await callback.answer()

@dp.callback_query(F.data == "menu_contact")
async def menu_add_contact(callback: CallbackQuery):
    kb = [[KeyboardButton(text="👤 Отправить контакт", request_contact=True)]]
    markup = ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True, one_time_keyboard=True)
    await callback.message.answer("Нажмите кнопку ниже, чтобы поделиться контактом:", reply_markup=markup)
    await callback.answer()

@dp.callback_query(F.data == "menu_list")
async def menu_list_birthdays(callback: CallbackQuery):
    birthdays = get_all_birthdays()
    user_birthdays = [b for b in birthdays if b[0] == callback.from_user.id]
    
    if not user_birthdays:
        await callback.message.edit_text("ℹ️ Твой список пуст.", reply_markup=get_main_menu())
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
    
    keyboard.append([InlineKeyboardButton(text="🔙 В главное меню", callback_data="menu_start")])
    markup = InlineKeyboardMarkup(inline_keyboard=keyboard)
    await callback.message.edit_text(text, reply_markup=markup)
    await callback.answer()

@dp.callback_query(F.data == "menu_start")
async def back_to_menu(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("<b>Главное меню</b>\nВыберите действие:", reply_markup=get_main_menu())
    await callback.answer()

@dp.message(F.contact)
async def process_contact(message: Message, state: FSMContext):
    contact = message.contact
    name = f"{contact.first_name} {contact.last_name or ''}".strip()
    await state.update_data(name=name)
    await state.set_state(AddBirthday.waiting_for_year)
    await message.answer(f"Записываем: <b>{name}</b>\nСначала выберите <b>год</b> рождения:", 
                         reply_markup=get_year_keyboard())

@dp.message(AddBirthday.waiting_for_name)
async def process_name(message: Message, state: FSMContext):
    await state.update_data(name=message.text)
    await state.set_state(AddBirthday.waiting_for_year)
    await message.answer(f"Имя: <b>{message.text}</b>\nТеперь выберите <b>год</b> рождения:", 
                         reply_markup=get_year_keyboard())

@dp.callback_query(F.data.startswith("set_year:"))
async def process_year(callback: CallbackQuery, state: FSMContext):
    year = int(callback.data.split(":")[1])
    await state.update_data(year=year)
    await state.set_state(AddBirthday.waiting_for_month)
    await callback.message.edit_text(f"Год: <b>{year}</b>\nТеперь выберите <b>месяц</b>:", 
                                     reply_markup=get_month_keyboard(year))
    await callback.answer()

@dp.callback_query(F.data.startswith("set_month:"))
async def process_month(callback: CallbackQuery, state: FSMContext):
    _, year, month = callback.data.split(":")
    await state.update_data(month=int(month))
    await state.set_state(AddBirthday.waiting_for_day)
    await callback.message.edit_text(f"Год: <b>{year}</b>, Месяц: <b>{month}</b>\nВыберите <b>день</b>:", 
                                     reply_markup=get_day_keyboard(int(year), int(month)))
    await callback.answer()

@dp.callback_query(F.data.startswith("set_day:"))
async def process_day_selection(callback: CallbackQuery, state: FSMContext):
    date_str = callback.data.split(":")[1]
    d, m, y = date_str.split(".")
    normalized_date = f"{int(d):02d}.{int(m):02d}.{y}"
    
    data = await state.get_data()
    name = data.get("name")
    
    add_birthday(callback.from_user.id, name, normalized_date)
    await state.clear()
    
    await callback.message.edit_text(f"✅ Добавлен день рождения для <b>{name}</b> на {normalized_date}!")
    await callback.message.answer("<b>Главное меню</b>", reply_markup=get_main_menu())
    await callback.answer()

@dp.callback_query(F.data == "ignore")
async def ignore_callback(callback: CallbackQuery):
    await callback.answer()

@dp.callback_query(F.data.startswith("del:"))
async def process_delete_callback(callback: CallbackQuery):
    name = callback.data.split(":")[1]
    delete_birthday(callback.from_user.id, name)
    await callback.answer(f"Запись '{name}' удалена")
    await menu_list_birthdays(callback)

async def main():
    logging.basicConfig(level=logging.INFO)
    init_db()
    
    scheduler = AsyncIOScheduler()
    scheduler.add_job(check_birthdays, "interval", minutes=1, args=[bot])
    scheduler.start()
    
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())

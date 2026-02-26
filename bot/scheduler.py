from datetime import datetime, timedelta
import asyncio
from bot.database import get_all_birthdays

async def check_birthdays(bot):
    now = datetime.now()
    birthdays = get_all_birthdays()
    
    for user_id, name, bday_str in birthdays:
        # Assuming format DD.MM.YYYY
        try:
            bday_date = datetime.strptime(bday_str, "%d.%m.%Y").replace(year=now.year)
        except ValueError:
            continue

        # If birthday already passed this year, check for next year
        if bday_date < now.replace(hour=0, minute=0, second=0, microsecond=0):
            bday_date = bday_date.replace(year=now.year + 1)

        diff = bday_date - now
        
        # 1 week (7 days)
        if timedelta(days=7) <= diff < timedelta(days=7, minutes=1):
             await bot.send_message(user_id, f"🔔 Напоминание: у {name} день рождения через неделю ({bday_str})!")

        # 3 days
        elif timedelta(days=3) <= diff < timedelta(days=3, minutes=1):
             await bot.send_message(user_id, f"🔔 Напоминание: у {name} день рождения через 3 дня!")

        # 1 day
        elif timedelta(days=1) <= diff < timedelta(days=1, minutes=1):
             await bot.send_message(user_id, f"🔔 Напоминание: у {name} день рождения завтра!")

        # 30 minutes
        elif timedelta(minutes=30) <= diff < timedelta(minutes=31):
             await bot.send_message(user_id, f"🔔 Напоминание: у {name} день рождения через 30 минут! Готовь поздравления!")

        # 5 minutes
        elif timedelta(minutes=5) <= diff < timedelta(minutes=6):
             await bot.send_message(user_id, f"🔥 Почти пора! У {name} день рождения через 5 минут!")

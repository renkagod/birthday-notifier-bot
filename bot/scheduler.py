from datetime import datetime, timedelta
import logging
from bot.database import get_all_birthdays

async def check_birthdays(bot):
    now = datetime.now().replace(second=0, microsecond=0)
    birthdays = get_all_birthdays()
    
    for user_id, name, bday_str in birthdays:
        try:
            # Parse birthday and set it to current year
            bday_dt = datetime.strptime(bday_str, "%d.%m.%Y")
            target_date = bday_dt.replace(year=now.year, hour=0, minute=0, second=0, microsecond=0)
            
            # If birthday passed this year, look at next year
            if target_date < now.replace(hour=0, minute=0, second=0):
                target_date = target_date.replace(year=now.year + 1)
            
            # Calculate how many years old they will be
            age = target_date.year - bday_dt.year
            
            # Calculate difference in minutes
            diff = target_date - now
            minutes_to_bday = int(diff.total_seconds() / 60)
            
            # Define notification points (in minutes)
            notifications = {
                10080: f"🔔 <b>Через неделю</b> ({bday_str}) день рождения у <b>{name}</b>! Исполнится <b>{age}</b>.",
                4320: f"🔔 <b>Через 3 дня</b> день рождения у <b>{name}</b>! Исполнится <b>{age}</b>.",
                1440: f"🔔 <b>Завтра</b> день рождения у <b>{name}</b>! Исполнится <b>{age}</b>.",
                30: f"⏳ <b>Через 30 минут</b> день рождения у <b>{name}</b>! Исполнится <b>{age}</b>. Пора готовить поздравления!",
                5: f"🔥 <b>Через 5 минут</b> день рождения у <b>{name}</b>! Исполнится <b>{age}</b>.",
                0: f"🥳 <b>УРА! Сегодня {name} исполняется {age}!</b> Поздравь именинника! 🎉"
            }

            if minutes_to_bday in notifications:
                await bot.send_message(user_id, notifications[minutes_to_bday])
                logging.info(f"Sent notification to {user_id} for {name} ({minutes_to_bday} min left)")

        except Exception as e:
            logging.error(f"Error checking birthday for {name}: {e}")

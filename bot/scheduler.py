from datetime import datetime
import logging
from bot.database import iter_all_birthdays, get_user_settings

async def check_birthdays(bot):
    now = datetime.now().replace(second=0, microsecond=0)
    # Cache user settings to avoid multiple DB calls
    user_settings_cache = {}

    for user_id, name, bday_str, tg_username in iter_all_birthdays():
        try:
            if user_id not in user_settings_cache:
                user_settings_cache[user_id] = get_user_settings(user_id)
            
            settings = user_settings_cache[user_id]
            notify_time = datetime.strptime(settings['notify_time'], "%H:%M").time()
            intervals = settings['intervals'] # List of floats (days)

            bday_dt = datetime.strptime(bday_str, "%d.%m.%Y")
            target_date = bday_dt.replace(year=now.year, hour=0, minute=0, second=0, microsecond=0)
            
            if target_date < now.replace(hour=0, minute=0, second=0):
                target_date = target_date.replace(year=now.year + 1)
            
            age = target_date.year - bday_dt.year
            display_name = f"<b>{name}</b>"
            if tg_username:
                display_name += f" ({tg_username})"

            # Short-term (minutes) vs Long-term (days at specific time)
            diff = target_date - now
            diff_minutes = int(diff.total_seconds() / 60)
            
            now_date = now.replace(hour=0, minute=0, second=0, microsecond=0)
            diff_days = (target_date - now_date).days

            msg = None
            
            # 1. Midnight/Pre-midnight reminders (Always relative to 00:00)
            if diff_minutes == 30 and 0.5 in intervals:
                msg = f"⏳ <b>Через 30 минут</b> день рождения у {display_name}! (исполнится {age})"
            elif diff_minutes == 5 and 0.08 in intervals:
                msg = f"🔥 <b>Через 5 минут</b> день рождения у {display_name}!"
            elif diff_minutes == 0 and -1.0 in intervals: # NEW: Midnight flag
                msg = f"🌙 <b>С днем рождения!</b> Сегодня {display_name} исполняется {age}! 🥳"
            
            # 2. Scheduled reminders (At user's preferred time)
            elif now.time() == notify_time:
                if diff_days == 0 and 0.0 in intervals: # Daytime reminder
                    msg = f"☀️ <b>Напоминание: сегодня</b> день рождения у {display_name}! (исполнится {age}) 🎉"
                elif diff_days == 1 and 1.0 in intervals:
                    msg = f"🔔 <b>Завтра</b> день рождения у {display_name}!"
                elif diff_days == 3 and 3.0 in intervals:
                    msg = f"🔔 <b>Через 3 дня</b> день рождения у {display_name}!"
                elif diff_days == 7 and 7.0 in intervals:
                    msg = f"🔔 <b>Через неделю</b> день рождения у {display_name}!"
                elif diff_days == 30 and 30.0 in intervals:
                    msg = f"📅 <b>Через месяц</b> ({bday_str}) день рождения у {display_name}!"

            if msg:
                await bot.send_message(user_id, msg)
                logging.info("Birthday notification sent")

        except Exception as e:
            logging.error(f"Error in scheduler: {e}")

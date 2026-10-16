import logging
from datetime import datetime

from aiogram.types import InputRichMessage

from bot.database import get_user_settings, iter_all_birthdays
from bot.notifications import build_birthday_notification


async def check_birthdays(bot):
    now = datetime.now().replace(second=0, microsecond=0)
    user_settings_cache = {}

    for user_id, name, bday_str, tg_username in iter_all_birthdays():
        try:
            if user_id not in user_settings_cache:
                user_settings_cache[user_id] = get_user_settings(user_id)

            settings = user_settings_cache[user_id]
            notify_time = datetime.strptime(settings["notify_time"], "%H:%M").time()

            msg = build_birthday_notification(
                name=name,
                bday_str=bday_str,
                tg_username=tg_username,
                now=now,
                notify_time=notify_time,
                intervals=settings["intervals"],
            )

            if msg:
                await bot.send_rich_message(user_id, InputRichMessage(markdown=msg))
                logging.info("Notification sent to %s for %s", user_id, name)

        except Exception as e:
            logging.error("Error in scheduler for %s: %s", name, e)

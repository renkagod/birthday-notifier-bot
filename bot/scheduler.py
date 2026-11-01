import logging
from datetime import datetime
from itertools import groupby

from aiogram.types import InputRichMessage

from bot.database import get_user_settings, iter_user_birthdays
from bot.notifications import build_digest


async def check_birthdays(bot):
    now = datetime.now().replace(second=0, microsecond=0)

    for user_id, rows in groupby(iter_user_birthdays(), key=lambda r: r[0]):
        people = [row[1:] for row in rows]
        try:
            settings = get_user_settings(user_id)
            notify_time = datetime.strptime(settings["notify_time"], "%H:%M").time()
            msg = build_digest(people, now=now, notify_time=notify_time, intervals=settings["intervals"])
            if msg:
                await bot.send_rich_message(user_id, InputRichMessage(markdown=msg))
                logging.info("Digest sent to %s (%d people)", user_id, len(people))
        except Exception as e:
            logging.error("Error in scheduler for user %s: %s", user_id, e)

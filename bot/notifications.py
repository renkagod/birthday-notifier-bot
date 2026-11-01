"""Build the reminder digest (pure logic, testable without Telegram).

One message per user per moment: several people celebrating on the same day, or reminders
for different people due at the same time, arrive together instead of as separate messages.
"""

from __future__ import annotations

from datetime import datetime, time

from bot.dates import minutes_until
from bot.screens import (
    WEEKDAYS,
    birthday_facts,
    capitalize,
    cb,
    day_month,
    inline_url,
    is_day_interval,
    link,
    links,
    tag_url,
    turns,
    when_phrase,
)

# Long digests are cut so the message stays well within Telegram's size limit.
MAX_LINES = 20

# (minutes before midnight, interval value, lead-in)
NIGHT = [
    (30, 0.5, "Через 30 минут день рождения"),
    (5, 0.08, "Через 5 минут день рождения"),
    (0, -1.0, "Наступил день рождения"),
]


def _person(b_id: int, name: str) -> str:
    return f"**{link(name, f'view:{b_id}')}**"


def _greet(tag: str | None) -> str:
    return f" {inline_url('Написать', tag_url(tag))}" if tag else ""


def build_digest(
    people: list[tuple],
    *,
    now: datetime,
    notify_time: time,
    intervals: list[float],
) -> str | None:
    """Rich Markdown reminder due right now for one user's (id, name, date, tag) rows, or None."""
    day_values = {int(v) for v in intervals if is_day_interval(v)}
    at_notify_time = now.time().replace(second=0, microsecond=0) == notify_time

    night: list[str] = []
    today: list[str] = []
    ahead: list[tuple[int, str]] = []
    for b_id, name, date_str, tag in people:
        facts = birthday_facts(date_str, now)
        if not facts:
            continue
        target, days, age = facts
        minutes = minutes_until(target, now)
        for before, value, lead in NIGHT:
            if value in intervals and minutes == before:
                tail = turns(age, 0 if before == 0 else 1)
                extra = " Самое время поздравить первым." if before == 0 else ""
                night.append(f"{lead} — {_person(b_id, name)}{tail}.{extra}{_greet(tag)}")
        if not at_notify_time or days not in day_values:
            continue
        if days == 0:
            today.append(f"Сегодня день рождения — {_person(b_id, name)}{turns(age, 0)}.{_greet(tag)}")
        else:
            when = capitalize(when_phrase(days))
            date = "" if days == 1 else f", {day_month(target)}"
            ahead.append((days, f"**{when}**{date} — {link(name, f'view:{b_id}')}{turns(age, days)}"))

    if not (night or today or ahead):
        return None

    entries = night + today + [text for _days, text in sorted(ahead, key=lambda item: item[0])]
    shown = entries[:MAX_LINES]
    lines: list[str] = []
    for text in shown[:len(night)]:
        lines += [text, ""]
    if today or ahead:
        lines += [f"## {day_month(now)}, {WEEKDAYS[now.weekday()]}", ""]
        for text in shown[len(night):]:
            lines += [text, ""]
    if len(entries) > MAX_LINES:
        lines += [f"И ещё {len(entries) - MAX_LINES} — в списке «Все».", ""]
    lines.append(links(cb("Все", "list:0", "link"), cb("Напоминания", "settings", "link")))
    return "\n".join(lines)

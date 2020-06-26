from __future__ import annotations

import datetime as dt
import re
from dataclasses import asdict, dataclass
from typing import Match, Optional, Pattern, Tuple


class ParseError(ValueError):
    pass


@dataclass
class ParseResult:
    date: Optional[dt.date] = None
    delta: Optional[dt.timedelta] = None
    time: Optional[dt.time] = None


RT = Optional[Tuple[ParseResult, Match[str]]]


def p_minutes(now: dt.datetime, text: str) -> RT:
    pattern = r'через ([1-9][0-9]?) мин(уты|ут)?'
    if (m := re.search(pattern, text, re.I)) is not None:
        n_minutes = int(m.group(1))
        return ParseResult(delta=dt.timedelta(minutes=n_minutes)), m


def p_hours(now: dt.datetime, text: str) -> RT:
    pattern = r'через ([1-9][0-9]?) час(а|ов)?'
    if (m := re.search(pattern, text, re.I)) is not None:
        n_hours = int(m.group(1))
        return ParseResult(delta=dt.timedelta(hours=n_hours)), m


def p_days(now: dt.datetime, text: str) -> RT:
    pattern = r'через ([1-9][0-9]?) (день|дня|дней)'
    if (m := re.search(pattern, text, re.I)) is not None:
        n_days = int(m.group(1))
        date = now.date() + dt.timedelta(days=n_days)
        return ParseResult(date=date), m


def p_tomorrow(now: dt.datetime, text: str) -> RT:
    pattern = r'завтра( |$)'
    if (m := re.search(pattern, text, re.I)) is not None:
        date = now.date() + dt.timedelta(days=1)
        return ParseResult(date=date), m


def p_weekday(now: dt.datetime, text: str) -> RT:
    week_days = ('пн', 'вт', 'ср', 'чт', 'пт', 'сб', 'вс')
    pattern = rf'в ({"|".join(week_days)})'
    if (m := re.search(pattern, text, re.I)) is not None:
        weekday = week_days.index(m.group(1).lower())
        n_days = ((weekday - now.weekday()) + 7) % 7
        date = now.date() + dt.timedelta(days=n_days)
        return ParseResult(date=date), m


def p_monthday(now: dt.datetime, text: str) -> RT:
    month_names = (
        'января', 'февраля', 'марта', 'апреля', 'мая', 'июня',
        'июля', 'августа', 'сентября', 'октября', 'ноября', 'декабря',
    )
    pattern = rf'([1-9][0-9]?) ({"|".join(month_names)})'
    if (m := re.search(pattern, text, re.I)) is not None:
        try:
            date = dt.date(
                now.year,
                month_names.index(m.group(2).lower()) + 1,
                int(m.group(1)),
            )
        except ValueError:
            raise ParseError
        if date < now.date():
            date = date.replace(date.year + 1)
        return ParseResult(date=date), m


def p_time(now: dt.datetime, text: str) -> RT:
    pattern = r'в (\d\d?)((:| )(\d\d))?'
    if (m := re.search(pattern, text, re.I)) is not None:
        hours, minutes = int(m.group(1)), int(m.group(4) or 0)
        return ParseResult(time=dt.time(hours, minutes)), m


def parse_reminder(now: dt.datetime, text: str) -> Tuple[dt.datetime, str]:
    result = ParseResult()
    for func in (v for k, v in globals().items() if k.startswith('p_')):
        rv = func(now, text)
        if rv is None:
            continue

        cur_result, match = rv
        if (
            (result.date and cur_result.date) or
            (result.delta and cur_result.delta) or
            (result.time and cur_result.time)
        ):
            raise ParseError

        vars(result).update({
            k: v for k, v in asdict(cur_result).items()
            if v is not None
        })
        text = text[:match.start()] + text[match.end():]

    default_time = dt.time(12, 0)

    if result.delta is not None:
        if result.date is not None or result.time is not None:
            raise ParseError
        when = now + result.delta

    elif result.date is not None:
        if result.delta is not None:
            raise ParseError
        when = dt.datetime.combine(result.date, result.time or default_time)

    elif result.time is not None:
        when = dt.datetime.combine(now.date(), result.time)
        if when < now:
            when += dt.timedelta(days=1)

    else:
        raise ParseError

    return when, text.strip()

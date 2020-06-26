import datetime as dt

from .bot import Message
from .db import DB
from .parser import ParseError, parse_reminder


def date_fmt(v: dt.datetime) -> str:
    return dt.datetime.strftime(v, '%A, %d %b at %H:%M')


def handle_message(message: Message, db: DB) -> str:
    if message.text.startswith('/'):
        return handle_command(message, db)

    now = dt.datetime.now()
    try:
        when, what = parse_reminder(now, message.text)
    except ParseError:
        return 'Could not parse date'
    if not what:
        return 'Empy reminder'
    if when < now:
        return 'Date is in the past'

    db.save_reminder(message.chat_id, when, what)
    return f'Reminder set on {date_fmt(when)}'


def handle_command(message: Message, db: DB) -> str:
    command = message.text.strip('/')

    if command == 'list':
        rows = db.list_unsent(chat_id=message.chat_id)
        return '\n'.join(
            f'[{record_id}] {date_fmt(when)}: {reminder}'
            for record_id, when, reminder in rows
        ) if rows else 'Not found'

    elif command.startswith('remove'):
        try:
            record_id = int(command.split('remove')[1])
        except ValueError:
            return 'Invalid record id'
        else:
            is_removed = db.remove_reminder(record_id)
            if is_removed:
                return f'Removed reminder {record_id}'
            else:
                return f'Not found record with id {record_id}'

    else:
        return 'Unknown command'

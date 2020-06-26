import argparse
import contextlib
import datetime as dt
import json
import logging
import os
import re
import sqlite3
import sys
import threading
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass
from functools import partial
from typing import Any, Callable, Dict, Iterator, List, Optional, Tuple, Union

logger = logging.getLogger()


@dataclass
class Message:
    update_id: int
    chat_id: int
    text: str


class Bot:
    API_URL = 'https://api.telegram.org'

    def __init__(
        self,
        token: str,
        handler: Callable[[Message], str],
        allowed_usernames: List[str],
    ) -> None:
        self.token = token
        self.handler = handler
        self.allowed_usernames = allowed_usernames
        self._is_stopping: bool = False

    def _request(self, url: str, params: Dict[str, Union[int, str]]) -> Any:
        with urllib.request.urlopen(f'{url}?{urllib.parse.urlencode(params)}') as f:
            return json.loads(f.read().decode('utf-8'))

    def get_updates(self, offset: int = 1) -> List[Message]:
        result = self._request(
            url=f'{self.API_URL}/bot{self.token}/GetUpdates',
            params={'timeout': 10, 'offset': offset},
        )
        assert result['ok']

        return [
            Message(
                update_id=item['update_id'],
                chat_id=item['message']['chat']['id'],
                text=item['message']['text'],
            )
            for item in result['result']
            if (
                item.get('message', {}).get('text') and
                item.get('message', {}).get('from', {}).get('username') in self.allowed_usernames
            )
        ]

    def start_polling(self) -> None:
        offset = 1
        while not self._is_stopping:
            for message in self.get_updates(offset):
                self.on_message(message)
                offset = max(offset, message.update_id + 1)

    def send_message(self, chat_id: int, text: str) -> None:
        self._request(
            url=f'{self.API_URL}/bot{self.token}/sendMessage',
            params={'chat_id': str(chat_id), 'text': text},
        )

    def on_message(self, message: Message) -> None:
        logger.info('Received message %s', message)
        try:
            reply = self.handler(message)
        except Exception as e:
            logger.exception(e)
            reply = 'Error'

        logger.info('Reply %s', reply)
        self.send_message(message.chat_id, text=reply)

    def stop(self) -> None:
        self._is_stopping = True


class DB:
    def __init__(self, filename: str) -> None:
        self.filename = filename

    def create_table(self) -> None:
        with sqlite3.connect(self.filename) as conn:
            conn.execute(
                '''
                create table if not exists records (
                    id integer primary key,
                    chat_id integer,
                    datetime text,
                    reminder text,
                    sent integer default 0
                )
                '''
            )

    def save_reminder(self, chat_id: int, when: dt.datetime, what: str) -> None:
        with sqlite3.connect(self.filename) as conn:
            conn.execute(
                'insert into records (chat_id, datetime, reminder) values (?, ?, ?)',
                (chat_id, when.isoformat(), what)
            )

    @contextlib.contextmanager
    def process_ready_to_send(self) -> Iterator[List[Tuple[int, str]]]:
        now = dt.datetime.now()
        with sqlite3.connect(self.filename) as conn:
            cur = conn.cursor()
            cur.execute(
                'select chat_id, reminder from records where datetime < ? and sent = 0',
                (now.isoformat(),),
            )
            rows = cur.fetchall()
            yield rows.copy()
            if rows:
                cur.execute(
                    'update records set sent = 1 where datetime < ? and sent = 0',
                    (now.isoformat(),),
                )

    def list_future(self, chat_id: int) -> List[Tuple[int, dt.datetime, str]]:
        with sqlite3.connect(self.filename) as conn:
            cur = conn.cursor()
            cur.execute(
                'select id, datetime, reminder from records where chat_id = ? and sent = 0',
                (chat_id,),
            )
            return [
                (record_id, dt.datetime.fromisoformat(datetime), reminder)
                for record_id, datetime, reminder in cur.fetchall()
            ]

    def remove(self, record_id: int) -> bool:
        with sqlite3.connect(self.filename) as conn:
            cur = conn.cursor()
            cur.execute('delete from records where id = ?', (record_id,))
            return bool(cur.rowcount == 1)


def handle_command(message: Message, db: DB) -> str:
    command = message.text.strip('/')

    if command == 'list':
        rows = db.list_future(chat_id=message.chat_id)
        return '\n'.join(
            f'[{record_id}] {dt.datetime.strftime(when, "%A, %d %b at %H:%S")}: {reminder}'
            for record_id, when, reminder in rows
        ) if rows else 'Not found'

    elif command.startswith('remove'):
        try:
            record_id = int(command.split('remove')[1])
        except ValueError:
            return 'Invalid record id'
        else:
            is_removed = db.remove(record_id)
            if is_removed:
                return f'Removed reminder {record_id}'
            else:
                return f'Not found record with id {record_id}'

    else:
        return 'Unknown command'


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

    db.save_reminder(message.chat_id, when, what)

    return 'Reminder set on ' + dt.datetime.strftime(when, '%A, %d %b at %H:%S')


class Sender:
    def __init__(self, bot: Bot, db: DB, sleep_interval: int = 5):
        self.bot = bot
        self.db = db
        self.sleep_interval = sleep_interval
        self._is_stopping = False

    def sleep(self) -> None:
        for _ in range(self.sleep_interval):
            if self._is_stopping:
                break
            time.sleep(1)

    def send_reminders(self) -> None:
        with self.db.process_ready_to_send() as rows:
            for chat_id, reminder in rows:
                logger.info('Sending reminder to %s: %s', chat_id, reminder)
                self.bot.send_message(chat_id, reminder)

    def start(self) -> None:
        while not self._is_stopping:
            try:
                self.send_reminders()
            except Exception as e:
                logger.exception(e)

            self.sleep()

    def stop(self) -> None:
        self._is_stopping = True


class ParseError(ValueError):
    pass


def parse_reminder(now: dt.datetime, text: str) -> Tuple[dt.datetime, str]:
    default_time = dt.time(12, 0)
    date = time = delta = None

    pat = r'через ([1-9][0-9]?) мин(уты|ут)?'
    if (m := re.search(pat, text, re.I)) is not None:
        n_minutes = int(m.group(1))
        delta = dt.timedelta(minutes=n_minutes)
        text = re.sub(pat, '', text, flags=re.I)

    pat = r'через ([1-9][0-9]?) час(а|ов)?'
    if (m := re.search(pat, text, re.I)) is not None:
        n_hours = int(m.group(1))
        delta = dt.timedelta(hours=n_hours)
        text = re.sub(pat, '', text, flags=re.I)

    pat = r'через ([1-9][0-9]?) (день|дня|дней)'
    if (m := re.search(pat, text, re.I)) is not None:
        n_days = int(m.group(1))
        date = now.date() + dt.timedelta(days=n_days)
        text = re.sub(pat, '', text, flags=re.I)

    pat = r'завтра( |$)'
    if (m := re.search(pat, text, re.I)) is not None:
        date = now.date() + dt.timedelta(days=1)
        text = re.sub(pat, '', text, flags=re.I)

    week_days = ('пн', 'вт', 'ср', 'чт', 'пт', 'сб', 'вс')
    pat = rf'в ({"|".join(week_days)})'
    if (m := re.search(pat, text, re.I)) is not None:
        weekday = week_days.index(m.group(1).lower())
        n_days = ((weekday - now.weekday()) + 7) % 7
        date = now.date() + dt.timedelta(days=n_days)
        text = re.sub(pat, '', text, flags=re.I)

    month_names = (
        'января', 'февраля', 'марта', 'апреля', 'мая', 'июня',
        'июля', 'августа', 'сентября', 'октября', 'ноября', 'декабря',
    )
    pat = rf'([1-9][0-9]?) ({"|".join(month_names)})'
    if (m := re.search(pat, text, re.I)) is not None:
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
        text = re.sub(pat, '', text, flags=re.I)

    pat = r'в (\d\d?)((:| )(\d\d))?'
    if (m := re.search(pat, text, re.I)) is not None:
        hours, minutes = int(m.group(1)), int(m.group(4) or 0)
        time = dt.time(hours, minutes)
        text = re.sub(pat, '', text, flags=re.I)

    if delta is not None:
        if date is not None or time is not None:
            raise ParseError
        when = now + delta

    elif date is not None:
        if delta is not None:
            raise ParseError
        when = dt.datetime.combine(date, time or default_time)

    elif time is not None:
        when = dt.datetime.combine(now.date(), time)
        if when < now:
            when += dt.timedelta(days=1)

    else:
        raise ParseError

    return when, text


if __name__ == '__main__':
    parser = argparse.ArgumentParser('Reminder bot')
    parser.add_argument('--token', type=str, required=True, help='Telegram bot token')
    parser.add_argument('--usernames', nargs='+', required=True, help='Telegram usernames whitelist')
    parser.add_argument('--db-file', type=str, default='db.sqlite', help='DB filename')
    parser.add_argument('--admin-chat-id', type=int, default=None)
    args = parser.parse_args()

    logging.basicConfig(
        format='[%(asctime)s] %(levelname)s:%(message)s',
        level=logging.INFO,
    )

    db = DB(filename=args.db_file)
    db.create_table()

    bot = Bot(
        token=args.token,
        handler=partial(handle_message, db=db),
        allowed_usernames=args.usernames,
    )
    bot_thread = threading.Thread(target=bot.start_polling)
    bot_thread.start()

    sender = Sender(bot=bot, db=db)
    sender_thread = threading.Thread(target=sender.start)
    sender_thread.start()

    logger.info('Started')
    try:
        while True:
            time.sleep(1)

            if not bot_thread.is_alive() or not sender_thread.is_alive():
                if args.admin_chat_id is not None:
                    with contextlib.suppress(Exception):
                        bot.send_message(args.admin_chat_id, 'Error')

                logger.warning('Thread is dead, restarting in 1 min...')
                time.sleep(60)
                os.execv(sys.executable, [sys.executable] + sys.argv)

    except (KeyboardInterrupt, EOFError):
        logger.info('Shutdown')
        bot.stop()
        sender.stop()

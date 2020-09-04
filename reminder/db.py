import contextlib
import datetime as dt
import sqlite3
from typing import Iterator, List, Tuple


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
            conn.commit()

    @contextlib.contextmanager
    def process_ready_to_send(self, now: dt.datetime) -> Iterator[List[Tuple[int, str]]]:
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
                conn.commit()

    def list_unsent(self, chat_id: int) -> List[Tuple[int, dt.datetime, str]]:
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

    def remove_reminder(self, record_id: int) -> bool:
        with sqlite3.connect(self.filename) as conn:
            cur = conn.cursor()
            cur.execute('delete from records where id = ?', (record_id,))
            conn.commit()
            return bool(cur.rowcount == 1)

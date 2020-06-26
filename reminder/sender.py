import logging
import time

from .bot import Bot
from .db import DB

logger = logging.getLogger(__name__)


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

import argparse
import contextlib
import logging
import os
import sys
import threading
import time
from functools import partial

from .bot import Bot
from .db import DB
from .handlers import handle_message
from .sender import Sender

if __name__ == '__main__':
    arg_parser = argparse.ArgumentParser('Reminder bot')
    arg_parser.add_argument('--token', type=str, required=True, help='Telegram bot token')
    arg_parser.add_argument('--usernames', nargs='+', required=True, help='Telegram usernames whitelist')
    arg_parser.add_argument('--db-file', type=str, default='db.sqlite', help='DB filename')
    arg_parser.add_argument('--admin-chat-id', type=int, default=None)
    args = arg_parser.parse_args()

    logging.basicConfig(
        format='[%(asctime)s] %(levelname)s:%(message)s',
        level=logging.INFO,
    )
    logger = logging.getLogger(__name__)

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

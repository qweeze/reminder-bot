import json
import logging
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Union

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

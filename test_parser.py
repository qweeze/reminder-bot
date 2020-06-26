import datetime as dt

import pytest

from bot import parse_reminder


@pytest.mark.parametrize(
    ['text', 'expected'], [
        ('через 5 мин',
            dt.datetime(2020, 5, 26, 12, 35)),
        ('через 2 дня в 11:00',
            dt.datetime(2020, 5, 28, 11, 0)),
        ('через 1 час',
            dt.datetime(2020, 5, 26, 13, 30)),
        ('через 2 дня',
            dt.datetime(2020, 5, 28, 12, 0)),
        ('в 21:20',
            dt.datetime(2020, 5, 26, 21, 20)),
        ('в пт в 21:20',
            dt.datetime(2020, 5, 29, 21, 20)),
        ('завтра в 8:25',
            dt.datetime(2020, 5, 27, 8, 25)),
        ('в 8 10',
            dt.datetime(2020, 5, 27, 8, 10)),
        ('в 21',
            dt.datetime(2020, 5, 26, 21, 0)),
        ('15 апреля в 21:21',
            dt.datetime(2021, 4, 15, 21, 21)),
        ('1 сентября в 8',
            dt.datetime(2020, 9, 1, 8, 0)),
    ]
)
def test_parser(text, expected):
    now = dt.datetime(2020, 5, 26, 12, 30)
    for text_fmt in (text.lower(), text.upper()):
        when, what = parse_reminder(now, text_fmt)
        assert when == expected
        assert what.strip() == ''


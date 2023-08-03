#!/usr/bin/env python3

import logging
logging.basicConfig(level=logging.DEBUG)

from dsmr_parser import telegram_specifications
from dsmr_parser.parsers import TelegramParser

telegram_txt = ''

with open('/var/meterd/telegram.txt', 'r') as raw_telegram:

    for line in raw_telegram:
        line = line.strip()
        line += '\r\n'
        telegram_txt += line

telegram_str = (telegram_txt)

parser = TelegramParser(telegram_specifications.V5, False)

telegram = parser.parse(telegram_str)

#print(telegram)

for obj in telegram:
    if type(obj[1]) == list:
        continue

    print('{} ({}): {}'.format(obj[0], type(obj[1].value), obj[1].value))

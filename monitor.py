#!/usr/bin/env python3

import os
import sys
import logging
import time
import pause
import sqlitesink
import influxsink
import datetime
import serial
from dsmr_parser import telegram_specifications
from dsmr_parser.parsers import TelegramParser
from dsmr_parser.clients import SerialReader

config = None
logger = None

def process_telegram(telegram):
    timestamp = None

    for attr,value in telegram:
        if attr == 'P1_MESSAGE_TIMESTAMP':
            timestamp = int(value.value.timestamp())

    if timestamp is None:
        timestamp = time.time()

    # Call the sinks
    sqlitesink.process_telegram(timestamp, telegram)
    influxsink.process_telegram(timestamp, telegram)

def file_loop():
    if 'meter' not in config:
        raise Exception('Missing "meter" section in the configuration')

    if 'p1_file' not in config['meter']:
        raise Exception('Missing "p1_file" item in the "meter" section of the configuration')

    p1_file = config['meter']['p1_file']

    while True:
        telegram_txt = ''

        with open(p1_file, 'r') as p1_fd:
            for line in p1_fd:
                line = line.strip()
                line += '\r\n'
                telegram_txt += line

        telegram_str = (telegram_txt)
        parser = TelegramParser(telegram_specifications.V5, False)
        telegram = parser.parse(telegram_str)

        mark = datetime.datetime.now()

        process_telegram(telegram)

        elapsed = datetime.datetime.now() - mark

        logger.debug('Telegram processing took {}'.format(elapsed))

        pause.until(time.time() + 1)

def serial_loop():
    if 'meter' not in config:
        raise Exception('Missing "meter" section in the configuration')

    serial_settings = dict()

    for setting in ['port', 'speed', 'bits', 'parity', 'rts_cts', 'xon_xoff']:
        if setting not in config['meter']:
            raise Exception('Missing "{}" value in "meter" section of the configuration'.format(setting))

    port = config['meter']['port']

    serial_settings['baudrate'] = config['meter']['speed']
  
    if config['meter']['bits'] == 7:
        serial_settings['bytesize'] = serial.SEVENBITS
    elif config['meter']['bits'] == 8:
        serial_settings['bytesize'] = serial.EIGHTBITS
    else:
        raise Exception('Unsupport byte size of {} bits specified in the configuration'.format(config['meter']['bits']))

    if config['meter']['parity'] == 'none':
        serial_settings['parity'] = serial.PARITY_NONE
    elif config['meter']['parity'] == 'odd':
        serial_settings['parity'] = serial.PARITY_ODD
    elif config['meter']['parity'] == 'even':
        serial_settings['parity'] = serial.PARITY_EVEN
    else:
        raise Exception('Unsupported parity setting "{}" specified in the configuration'.format(config['meter']['parity']))

    if config['meter']['rts_cts']:
        serial_settings['rtscts'] = 1
        rts_cts = 'on'
    else:
        serial_settings['rtscts'] = 0
        rts_cts = 'off'

    if config['meter']['xon_xoff']:
        serial_settings['xonxoff'] = 1
        xon_xoff = 'on'
    else:
        serial_settings['xonxoff'] = 0
        xon_xoff = 'off'

    # This setting is the same for all smart meters
    serial_settings['stopbits'] = serial.STOPBITS_ONE
    serial_settings['timeout'] = 20

    logger.info('Reading telegrams from serial port {} at {}bps (parity {}, {} bits/byte, RTS/CTS {}, XON/XOFF {})'.format(port, serial_settings['baudrate'], config['meter']['parity'], serial_settings['bytesize'], rts_cts, xon_xoff))

    # Run the loop
    while True:
        serial_reader = SerialReader(device=port, serial_settings=serial_settings, telegram_specification=telegram_specifications.V5)

        try:
            for telegram in serial_reader.read():
                mark = datetime.datetime.now()

                process_telegram(telegram)

                elapsed = datetime.datetime.now() - mark

                logger.debug('Telegram processing took {}'.format(elapsed))
        except Exception as e:
            logger.error('Exception while accessing serial device ({})'.format(e))

def run_monitor():
    logger.info('Monitor loop starting')

    try:
        serial_loop()
    except Exception as e:
        logger.error('Monitor loop exited with an exception ({})'.format(e))
    finally:
        logger.info('Monitor loop ending')

def init_monitor(in_config, in_logger):
    global config
    global logger 

    config = in_config
    logger = in_logger

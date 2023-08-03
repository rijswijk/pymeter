#!/usr/bin/env python3

import os
import sys
import logging
import sqlite3

logger = None

# Database handles
raw_db = None
fivemin_db = None
hourly_db = None
consumed_db = None

# How often do we store total consumed counters?
total_interval = 300

# Is this sink active?
active = False

# Which counters to track
raw_counters = []
consumed_counters = []

# Averages for raw counters
averages_fivemin = dict()
averages_hourly = dict()

# Mapping of DSMR field names to counters           = (counter, sqlite3_table, unit)
dsmr_map = dict()

# Consumption counters
dsmr_map['ELECTRICITY_USED_TARIFF_1']               = ('1.8.1', 'CONSUMED_1_8_1', 'kWh')
dsmr_map['ELECTRICITY_USED_TARIFF_2']               = ('1.8.2', 'CONSUMED_1_8_2', 'kWh')
dsmr_map['ELECTRICITY_USED_TARIFF_3']               = ('1.8.3', 'CONSUMED_1_8_3', 'kWh')
dsmr_map['ELECTRICITY_USED_TARIFF_4']               = ('1.8.4', 'CONSUMED_1_8_4', 'kWh')
dsmr_map['HOURLY_GAS_METER_READING']                = ('24.2.1', 'CONSUMED_24_2_1', 'm3')

# Production counters
dsmr_map['ELECTRICITY_DELIVERED_TARIFF_1']          = ('2.8.1', 'PRODUCED_2_8_1', 'kWh')
dsmr_map['ELECTRICITY_DELIVERED_TARIFF_2']          = ('2.8.2', 'PRODUCED_2_8_2', 'kWh')
dsmr_map['ELECTRICITY_DELIVERED_TARIFF_3']          = ('2.8.3', 'PRODUCED_2_8_3', 'kWh')
dsmr_map['ELECTRICITY_DELIVERED_TARIFF_4']          = ('2.8.4', 'PRODUCED_2_8_4', 'kWh')

# Raw counters
dsmr_map['CURRENT_ELECTRICITY_USAGE']               = ('1.7.0', 'RAW_1_7_0', 'kW')
dsmr_map['CURRENT_ELECTRICITY_DELIVERY']            = ('2.7.0', 'RAW_2_7_0', 'kW')
dsmr_map['INSTANTANEOUS_VOLTAGE_L1']                = ('32.7.0', 'RAW_32_7_0', 'V')
dsmr_map['INSTANTANEOUS_VOLTAGE_L2']                = ('52.7.0', 'RAW_52_7_0', 'V')
dsmr_map['INSTANTANEOUS_VOLTAGE_L3']                = ('72.7.0', 'RAW_72_7_0', 'V')
dsmr_map['INSTANTANEOUS_CURRENT_L1']                = ('31.7.0', 'RAW_31_7_0', 'A')
dsmr_map['INSTANTANEOUS_CURRENT_L2']                = ('51.7.0', 'RAW_51_7_0', 'A')
dsmr_map['INSTANTANEOUS_CURRENT_L3']                = ('71.7.0', 'RAW_71_7_0', 'A')
dsmr_map['INSTANTANEOUS_ACTIVE_POWER_L1_POSITIVE']  = ('21.7.0', 'RAW_21_7_0', 'kW')
dsmr_map['INSTANTANEOUS_ACTIVE_POWER_L2_POSITIVE']  = ('41.7.0', 'RAW_41_7_0', 'kW')
dsmr_map['INSTANTANEOUS_ACTIVE_POWER_L3_POSITIVE']  = ('61.7.0', 'RAW_61_7_0', 'kW')
dsmr_map['INSTANTANEOUS_ACTIVE_POWER_L1_NEGATIVE']  = ('22.7.0', 'RAW_22_7_0', 'kW')
dsmr_map['INSTANTANEOUS_ACTIVE_POWER_L2_NEGATIVE']  = ('42.7.0', 'RAW_42_7_0', 'kW')
dsmr_map['INSTANTANEOUS_ACTIVE_POWER_L3_NEGATIVE']  = ('62.7.0', 'RAW_62_7_0', 'kW')

def process_insert(timestamp, table, value, unit, db, db_desc):
    if db is None:
        return

    try:
        cur = db.cursor()

        query = "INSERT INTO {} (timestamp, value, unit) VALUES ({},{},'{}');".format(table, timestamp, value, unit)

        cur.execute(query)
    except Exception as e:
        logger.error('Failed to insert value into table {} in the {} database ({})'.format(table, db_desc, e))

def process_raw_counter(timestamp, table, value, unit):
    process_insert(timestamp, table, value, unit, raw_db, 'raw')

    # Process 5-minute average
    if timestamp % 300 == 0:
        acc,count = averages_fivemin[table]

        avg = float(acc/count)

        averages_fivemin[table] = (0, 0)

        process_insert(timestamp, table, avg, unit, fivemin_db, '5-minute average')

    acc,count = averages_fivemin[table]
    acc += value
    count += 1
    averages_fivemin[table] = (acc, count)

    # Process hourly average
    if timestamp % 3600 == 0:
        acc,count = averages_hourly[table]

        avg = float(acc/count)

        averages_hourly[table] = (0, 0)

        process_insert(timestamp, table, avg, unit, hourly_db, 'hourly average')

    acc,count = averages_hourly[table]
    acc += value
    count += 1
    averages_hourly[table] = (acc, count)

def process_consumed_counter(timestamp, table, value, unit):
    if timestamp % total_interval != 0 or consumed_db is None:
        return

    process_insert(timestamp, table, value, unit, consumed_db, 'consumption/production')

def process_telegram(timestamp, telegram):
    if not active:
        return

    for attr,value in telegram:
        if attr in dsmr_map:
            counter,table,unit = dsmr_map[attr]

            if counter in raw_counters:
                process_raw_counter(timestamp, table, value.value, unit)
            elif counter in consumed_counters:
                process_consumed_counter(timestamp, table, value.value, unit)

    # For efficiency reasons, commit to the databases only once
    if raw_db is not None:
        raw_db.commit()

    if fivemin_db is not None:
        fivemin_db.commit()

    if hourly_db is not None:
        hourly_db.commit()

    if consumed_db is not None:
        consumed_db.commit()

def add_raw_counter(counter):
    counter_found = False
    table = None

    for key,val in zip(dsmr_map.keys(), dsmr_map.values()):
        if val[0] == counter:
            counter_found = True

            logger.info('Adding raw counter {}, which maps to {}, is stored in table {} and measured in {}'.format(counter, key, val[1], val[2]))

            table = val[1]
            break

    if not counter_found:
        logger.warning('No mapping for raw counter {}, not adding it'.format(counter))
        return

    raw_counters.append(counter)
    averages_fivemin[table] = (0,0)
    averages_hourly[table] = (0,0)

def add_consumed_counter(counter):
    counter_found = False

    for key,val in zip(dsmr_map.keys(), dsmr_map.values()):
        if val[0] == counter:
            counter_found = True

            logger.info('Adding consumption counter {}, which maps to {}, is stored in table {} and measured in {}'.format(counter, key, val[1], val[2]))
            break

    if not counter_found:
        logger.warning('No mapping for consumption counter {}, not adding it'.format(counter))
        return

    consumed_counters.append(counter)

def init_sink(in_config, in_logger):
    global logger 
    global raw_db
    global fivemin_db
    global hourly_db
    global consumed_db
    global total_interval
    global active

    config = in_config
    logger = in_logger

    logger.info('Initialising sqlite3 sink')

    if 'legacy_database' not in config:
        logger.info('No configuration for sqlite3 sink found, disabling it')
        return

    if 'raw_db' not in config['legacy_database']:
        logger.warning('No raw measurement database configured for the sqlite3 sink')
    else:
        raw_db = sqlite3.connect(config['legacy_database']['raw_db'])
        logger.info('Opened {} as sqlite3 database for raw measurement data'.format(config['legacy_database']['raw_db']))
        active = True

    if 'fivemin_avg' not in config['legacy_database']:
        logger.info('No 5-minute average database configured for the sqlite3 sink')
    else:
        fivemin_db = sqlite3.connect(config['legacy_database']['fivemin_avg'])
        logger.info('Opened {} as sqlite3 database for 5-minute averages of raw measurement data'.format(config['legacy_database']['fivemin_avg']))

    if 'hourly_avg' not in config['legacy_database']:
        logger.info('No hourly average database configured for the sqlite3 sink')
    else:
        hourly_db = sqlite3.connect(config['legacy_database']['hourly_avg'])
        logger.info('Opened {} as sqlite3 database for hourly averages of raw measurement data'.format(config['legacy_database']['hourly_avg']))

    if 'total_consumed' not in config['legacy_database']:
        logger.warning('No total consumed database configured for the sqlite3 sink')
    else:
        consumed_db = sqlite3.connect(config['legacy_database']['total_consumed'])
        logger.info('Opened {} as sqlite3 database for total consumed data'.format(config['legacy_database']['total_consumed']))
        active = True

    if active:
        logger.info('At least one raw or total consumed database open, sqlite3 sink is now active')

        # Add counters
        if 'current_consumption_id' in config['legacy_database']:
            add_raw_counter(config['legacy_database']['current_consumption_id'])

        if 'current_production_id' in config['legacy_database']:
            add_raw_counter(config['legacy_database']['current_production_id'])

        if 'other_raw_counters' in config['legacy_database']:
            for counter in config['legacy_database']['other_raw_counters']:
                add_raw_counter(counter)

        if 'consumption' in config['legacy_database']:
            for key in config['legacy_database']['consumption'].keys():
                if 'id' in config['legacy_database']['consumption'][key]:
                    add_consumed_counter(config['legacy_database']['consumption'][key]['id'])

        if 'production' in config['legacy_database']:
            for key in config['legacy_database']['production'].keys():
                if 'id' in config['legacy_database']['production'][key]:
                    add_consumed_counter(config['legacy_database']['production'][key]['id'])

        if 'total_interval' in config['legacy_database']:
            total_interval = config['legacy_database']['total_interval']

        logger.info('Inserting consumption/production values into sqlite3 database every {}s'.format(total_interval))

    logger.info('Initialisation of sqlite3 sink complete')

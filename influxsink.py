#!/usr/bin/env python3

import os
import sys
import logging
import influxdb_client
from influxdb_client import InfluxDBClient, Point, WritePrecision
from influxdb_client.client.write_api import ASYNCHRONOUS

logger = None

# InfluxDB configuration
token = None
org = None
url = None
bucket = None

active = False

# Mapping of DSMR field names to InfluxDB           = (field, tags+values)
dsmr_map = dict()

# Consumption counters
dsmr_map['ELECTRICITY_USED_TARIFF_1']               = ('electricity_used', [('tariff', '1')])
dsmr_map['ELECTRICITY_USED_TARIFF_2']               = ('electricity_used', [('tariff', '2')])
dsmr_map['ELECTRICITY_USED_TARIFF_3']               = ('electricity_used', [('tariff', '3')])
dsmr_map['ELECTRICITY_USED_TARIFF_4']               = ('electricity_used', [('tariff', '4')])
dsmr_map['HOURLY_GAS_METER_READING']                = ('gas', [])

# Production counters
dsmr_map['ELECTRICITY_DELIVERED_TARIFF_1']          = ('electricity_produced', [('tariff', '1')])
dsmr_map['ELECTRICITY_DELIVERED_TARIFF_2']          = ('electricity_produced', [('tariff', '2')])
dsmr_map['ELECTRICITY_DELIVERED_TARIFF_3']          = ('electricity_produced', [('tariff', '3')])
dsmr_map['ELECTRICITY_DELIVERED_TARIFF_4']          = ('electricity_produced', [('tariff', '4')])

# Raw counters
dsmr_map['CURRENT_ELECTRICITY_USAGE']               = ('total_power_used', [])
dsmr_map['CURRENT_ELECTRICITY_DELIVERY']            = ('total_power_produced', [])
dsmr_map['INSTANTANEOUS_VOLTAGE_L1']                = ('voltage', [('phase', 'l1')])
dsmr_map['INSTANTANEOUS_VOLTAGE_L2']                = ('voltage', [('phase', 'l2')])
dsmr_map['INSTANTANEOUS_VOLTAGE_L3']                = ('voltage', [('phase', 'l3')])
dsmr_map['INSTANTANEOUS_CURRENT_L1']                = ('current', [('phase', 'l1')])
dsmr_map['INSTANTANEOUS_CURRENT_L2']                = ('current', [('phase', 'l2')])
dsmr_map['INSTANTANEOUS_CURRENT_L3']                = ('current', [('phase', 'l3')])
dsmr_map['INSTANTANEOUS_ACTIVE_POWER_L1_POSITIVE']  = ('power_pos', [('phase', 'l1')])
dsmr_map['INSTANTANEOUS_ACTIVE_POWER_L2_POSITIVE']  = ('power_pos', [('phase', 'l2')])
dsmr_map['INSTANTANEOUS_ACTIVE_POWER_L3_POSITIVE']  = ('power_pos', [('phase', 'l3')])
dsmr_map['INSTANTANEOUS_ACTIVE_POWER_L1_NEGATIVE']  = ('power_neg', [('phase', 'l1')])
dsmr_map['INSTANTANEOUS_ACTIVE_POWER_L2_NEGATIVE']  = ('power_neg', [('phase', 'l2')])
dsmr_map['INSTANTANEOUS_ACTIVE_POWER_L3_NEGATIVE']  = ('power_neg', [('phase', 'l3')])

def process_telegram(timestamp, telegram):
    if not active:
        return

    try:
        influx_writer = influxdb_client.InfluxDBClient(url=url, token=token, org=org)
        write_api = influx_writer.write_api(write_options=ASYNCHRONOUS)

        for attr,value in telegram:
            if attr in dsmr_map:
                field,tags = dsmr_map[attr]

                point = Point("smart_meter")
                point = point.field(field, value.value)
                
                for tag,val in tags:
                    point = point.tag(tag, val)

                write_api.write(bucket=bucket, org=org, record=point)
    except Exception as e:
        logger.error('Failed to send data to InfluxDB ({})'.format(e))

def init_sink(in_config, in_logger):
    global logger 
    global token
    global org
    global url
    global active
    global bucket

    config = in_config
    logger = in_logger

    logger.info('Initialising InfluxDB sink')

    if 'influx' not in config:
        logger.info('No configuration for InfluxDB sink found, disabling it')
        return

    if 'token' not in config['influx']:
        logger.error('Missing mandatory "token" field in InfluxDB configuration section')
        return

    token = config['influx']['token']

    if 'org' not in config['influx']:
        logger.error('Missing mandatory "org" field in InfluxDB configuration section')
        return

    org = config['influx']['org']

    if 'url' not in config['influx']:
        logger.error('Missing mandatory "url" field in InfluxDB configuration section')
        return

    url = config['influx']['url']

    if 'bucket' not in config['influx']:
        logger.error('Missing mandatory "bucket" field in InfluxDB configuration section')

    bucket = config['influx']['bucket']

    active = True
    logger.info('Initialisation of InfluxDB sink complete')

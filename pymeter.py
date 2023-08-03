#!/usr/bin/env python3

import os
import sys
import libconf
import logging
import argparse
import monitor
import sqlitesink
import influxsink

# Default configuration
default_config = '/etc/pymeter.conf'

# Configure logging
def configure_log(config):
    if 'logging' in config:
        loglevel = int(config['logging'].get('loglevel', 3))
        filelog = config['logging'].get('filelog', None)

        pylevel = logging.INFO

        if loglevel == 1:
            pylevel = logging.ERROR
        elif loglevel == 2:
            pylevel = logging.WARNING
        elif loglevel == 3:
            pylevel = logging.INFO
        elif loglevel == 4:
            pylevel = logging.DEBUG

        logfmt = '%(asctime)s [%(levelname)s] %(message)s'
        datefmt = '%Y-%m-%d %H:%M:%S'

        if filelog is not None:
            logging.basicConfig(filename=filelog, level=pylevel, format=logfmt, datefmt=datefmt)
        else:
            logging.basicConfig(level=pylevel, format=logfmt, datefmt=datefmt)

    return logging.getLogger('pymeter')

def main():
    # Process command-line arguments
    argparser = argparse.ArgumentParser(description = 'Python smart meter monitoring daemon')

    argparser.add_argument('-c, --config', nargs=1, help='configuration file to use', type=str, metavar='config_file', dest='config_file', required=False, default=[default_config])

    args = argparser.parse_args()

    # Load configuration
    try:
        with open(args.config_file[0], 'r') as cfg_fd:
            config = libconf.load(cfg_fd)
    except Exception as e:
        sys.stderr.write('Failed to load configuration from {} ({})\n'.format(args.config_file, e))

    # Configure and enable logging
    logger = configure_log(config)

    logger.info('Starting the Python smart meter monitoring tool')

    try:
        monitor.init_monitor(config, logger)
        sqlitesink.init_sink(config, logger)
        influxsink.init_sink(config, logger)
        monitor.run_monitor()
    finally:
        logger.info('Exiting the Python smart meter monitoring tool')

if __name__ == "__main__":
    main()

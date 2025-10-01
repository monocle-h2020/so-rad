#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Data downloads
"""

import os
import sys
import logging
import argparse
import inspect
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(inspect.getfile(inspect.currentframe())))))
from initialisation import db_init, datasets_init
import functions.config_functions as cf_func
import functions.download_functions as df
from functions.db_functions import connect_db, column_names
import datetime
import time
from redis import Redis
from rq import Queue

def parse_args():
    """parse command line arguments"""
    parser = argparse.ArgumentParser()
    parser.add_argument('-c', '--config_file', required=False,
                        help="config file providing program settings",
                        default=u"../config.ini")
    parser.add_argument('-l', '--local_config_file', required=False,
                        help="system-specific config overrides providing program settings",
                        default=u"../config-local.ini")
    parser.add_argument('--start', required=False,
                        help="Start time of request (date time YYYYMMDDTHHmmss in UTC")
    parser.add_argument('--end', required=False,
                        help="End time of request (date time YYYYMMDDTHHmmss in UTC")
    parser.add_argument('-f', '--format', required=False, default='hdf',
                        help="Choose csv or hdf output format")
    parser.add_argument('-d', '--debug', required=False, action='store_true',
                        help="set log level to debug")


    args = parser.parse_args()

    if not os.path.exists(args.config_file):
        raise IOError("Config file not found at {0}".format(args.config_file))
    if not os.path.exists(args.local_config_file):
        raise IOError("Local config override file not found at {0}".format(args.local_config_file))

    return args


if __name__ == '__main__':
    args = parse_args()
    conf = cf_func.read_config(args.config_file)
    # start logging to stdout
    log = logging.getLogger()
    handler = logging.StreamHandler(sys.stdout)
    if args.debug:
        log.setLevel(logging.DEBUG)
        handler.setLevel(logging.DEBUG)
    else:
        log.setLevel(logging.INFO)
        handler.setLevel(logging.INFO)

    formatter = logging.Formatter('%(asctime)s| %(levelname)s | %(name)s | %(message)s')
    handler.setFormatter(formatter)
    log.addHandler(handler)

    # update config with local overrides
    conf = cf_func.update_config(conf, args.local_config_file, verbosity=False)

    db_dict = db_init(conf['DATABASE'])
    dataset_dict = datasets_init(conf['DOWNLOAD'])

    # connect to redis queue
    sorad_q = Queue('sorad_q', connection=Redis())

    # previous 24 hours
    today = datetime.datetime.now()
    if args.start is None:
        log.info("No start time given, default to last 24H")
        start_time = datetime.datetime.now()-datetime.timedelta(hours=24)
        end_time = datetime.datetime.now()
    else:
        try:
            start_time = datetime.datetime.strptime(args.start, "%Y%m%dT%H%M%S")
            end_time = datetime.datetime.strptime(args.end, "%Y%m%dT%H%M%S")
        except ValueError:
            raise ValueError(f"Could not parse timestamp")

    log.info(f"Requesting database entries from {start_time.isoformat()} to {end_time.isoformat()}")

    platform_id = conf['EXPORT']['platform_id']
    outfile = os.path.join(conf['DOWNLOAD'].get('storage_path'),
                          df.filename_from_dates(platform_id,
                                                 start_time, end_time,
                                                 format='csv'))

    df.hdf_from_web_request(conf, start_time, end_time, platform_id)

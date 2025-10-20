#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Background data export and status update

This starts a manager thread which checks the database for updates and exports them to the remote parseserver configured.

Note: it should not be possible to create database locks due to queue management in sqlite3. Mileage may vary. The data uploader should recover from any failed attempts.

The config[-local].ini file will provide any keys required to access the remote store. These are not shown in system logs.
"""

import os
import sys
import traceback
import logging
import argparse
import inspect
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(inspect.getfile(inspect.currentframe())))))
import time
from initialisation import db_init
import functions.config_functions as cf_func
from thread_managers.export_manager import ParseExportManager

def parse_args():
    """parse command line arguments"""
    parser = argparse.ArgumentParser()
    parser.add_argument('-c', '--config_file', required=False,
                        help="config file providing program settings",
                        default=u"../config.ini")
    parser.add_argument('-l', '--local_config_file', required=False,
                        help="system-specific config overrides providing program settings",
                        default=u"../config-local.ini")
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
    export_dict = conf['EXPORT']

    pem = ParseExportManager(export_dict, db_dict)
    pem.start()

    log.info("Run export manager for 10s")
    time.sleep(10)

    pem.stop()



#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Data export functions

This can be called from the command line to force upload of data (scenario: So-Rad has been running offline, run to catch up after re-connecting it.
If called from command line without the force_manual attribute (specifying how many records to upload),
  this script will run in test-mode, showing whether any records remain to be uploaded and checking connectivity to local and remote data stores.

Note: it is possible for this process to create a database lock, so it should be timed not to interfere with creation of new records.
If the main app is locked out of the databse it will ignore and recover but the new record will be lost.
Similarly, this process will only try a few times to update the database to mark a record as uploaded.

The config-local.ini file will provide any keys required to access the remote store. These should be kept out of system logs.
"""

import os
import sys
import traceback
import logging
import argparse
import inspect
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(inspect.getfile(inspect.currentframe())))))
import functions.db_functions as db_func
import functions.config_functions as cf_func
from initialisation import db_init
from functions.export_functions import run_export, update_status_parse_server


def parse_args():
    """parse command line arguments"""
    parser = argparse.ArgumentParser()
    parser.add_argument('-c', '--config_file', required=False,
                        help="config file providing program settings",
                        default=u"../config.ini")
    parser.add_argument('-l', '--local_config_file', required=False,
                        help="system-specific config overrides providing program settings",
                        default=u"../config-local.ini")
    parser.add_argument('-f', '--force_upload', required=False, type=int, default=0,
                        help="force upload of set number of records to remote server (defaults to 0)")
    parser.add_argument('-s', '--source', required=False, type=str, default=None,
                        help="path to a specific database file rather than the one in current use")
    parser.add_argument('-d', '--debug', required=False, action='store_true',
                        help="set log level to debug")
    parser.add_argument('-u', '--update', required=False, action='store_true',
                        help="Update remote status record")

    args = parser.parse_args()

    if not os.path.exists(args.config_file):
        raise IOError("Config file not found at {0}".format(args.config_file))
    if not os.path.exists(args.local_config_file):
        raise IOError("Local config override file not found at {0}".format(args.local_config_file))
    if (args.source is not None) and (not os.path.exists(args.config_file)):
        raise IOError("Database file not found at {0}".format(args.source))

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
    conf = cf_func.update_config(conf, args.local_config_file)

    db = db_init(conf['DATABASE'])
    if args.source is not None:
        db['file'] = args.source

    if args.force_upload > 0:
        limit = args.force_upload
        test_run = False
    else:
        limit = 1
        test_run = True

    if not args.update:
        export_result, status_code, successes = run_export(conf, db, limit=limit, test_run=test_run)
        log.info(f"{successes} records uploaded")
    else:
        export_result, status_code = update_status_parse_server(conf, db)
        log.info(f"status upload success: {export_result}")

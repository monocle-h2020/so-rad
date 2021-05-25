#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Database Functions

Connects to the database, creates a cursor, commits data and closes the connection to it.
"""
import os
import sys
import traceback
import logging
import sqlite3
import argparse
import json
import requests
import config_functions as cf_func
import db_functions as db_func


def db_init(db_config):
    """set up and test sqlite database connection. Return dictionary with database items"""
    db = {}
    db['used'] = db_config.getboolean('use_database')
    # If it is used, check the type of db
    if db['used']:
        try:
            assert db_config.get('database_type') == "sqlite3"
        except AssertionError:
            msg = "database_type {0} not recognized. Only sqlite3 is supported".format(db_config['database_type'])
            log.critical(msg)
            raise AssertionError(msg)

        # Create tables (only if necessary)
        db['file'] = db_config.get('database_path')
        try:
            db_func.create_tables(db)  # won't harm existing tables
        except Exception as err:
            msg = "Error connecting to database: \n {0}".format(err)
            log.critical(msg)
            raise Exception(msg)
    return db


def run_test(conf):
    "Excecute when script is called from command line: test db connection and report on number of records available"
    db = db_init(conf['DATABASE'])
    n_total, n_new, record = identify_new_local_records(db, limit=1)
    log.info("records={0}, not_uploaded={1}".format(n_total, n_new))
    if record is not None:
        log.info("last local-only record: {0}".format(records))


def run_manual(conf, limit):
    """Execute when script is called from command line with 'manual' attribute. This will immediate try to upload a number of records"""
    db = db_init(conf['DATABASE'])
    export_config_dict = conf['EXPORT']
    n_total, n_new, records, header_meta, header_rad = identify_new_local_records(db, limit=limit)
    log.info(records)
    for r in records:
        record_json = make_json(header_meta, r)  # one metadata record in json
        export_to_parse_server(export_config_dict, record_json)


def column_names(conn, cur, table="sorad_metadata"):
    sql = """SELECT name FROM PRAGMA_TABLE_INFO(?)"""
    cur.execute(sql, (table,))
    columns = cur.fetchall()
    if columns is not None:
        columns = [c[0] for c in columns]
    log.debug(columns)
    return columns


def identify_new_local_records(db, limit=10):
    """report on total and new (not uploaded) records, latest record"""
    n_total = 0
    n_uploaded = 0
    conn, cur = db_func.connect_db(db)

    header_meta = column_names(conn, cur, table="sorad_metadata")
    header_rad = column_names(conn, cur, table="sorad_radiometry")

    # query number of radiometry samples in database
    sql_n_total = """SELECT count(*) FROM sorad_metadata WHERE n_rad_obs > 0"""
    cur.execute(sql_n_total)
    n_total = cur.fetchone()[0]

    # query number of radiometry samples not yet uploaded
    sql_n_not_inserted = """SELECT count(*) FROM sorad_metadata WHERE n_rad_obs > 0 AND (sos_inserted IS NULL OR sos_inserted=0)"""
    cur.execute(sql_n_not_inserted)
    n_not_inserted = cur.fetchone()[0]

    # query youngest record not yet uploaded
    sql_last_not_inserted = """SELECT * FROM sorad_metadata WHERE n_rad_obs > 0 AND (sos_inserted IS NULL OR sos_inserted=0) ORDER BY id_ DESC LIMIT ?"""
    cur.execute(sql_last_not_inserted, (limit,))
    all_not_inserted = cur.fetchall()
    last_not_inserted = all_not_inserted[0]
    conn.close()

    return n_total, n_not_inserted, all_not_inserted, header_meta, header_rad


def make_json(header, record):
    """convert a record to JSON"""
    record_as_dict = dict(zip(header, record))
    json_record = json.dumps(record_as_dict)
    log.info(json_record)


def export_to_parse_server(export_config_dict, json_record):
    """attempt to upload a record to a remote Parse server"""
    parse_app_url = export_config_dict.get('parse_url')  # something like https:1.2.3.4:port/parse/classes/sorad
    parse_app_id = export_config_dict.get('parse_app_id')
    platform_id = export_config_dict.get('platform_id')  # TODO bolt this on to the record, and a bunch of other metadata as well as the actual measurement

    headers = {'content-type': 'application/json',
               'X-Parse-Application-Id': parse_app_id}
    response = requests.post(parse_app_url, data=json_record, headers=headers)

    return response


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
    args = parser.parse_args()

    if not os.path.exists(args.config_file):
        raise IOError("Config file not found at {0}".format(args.config_file))

    return args


if __name__ == '__main__':
    args = parse_args()
    conf = cf_func.read_config(args.config_file)
    # start logging to stdout
    log = logging.getLogger()
    log.setLevel(logging.INFO)
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(logging.INFO)
    formatter = logging.Formatter('%(asctime)s|%(levelname)s| %(message)s')
    handler.setFormatter(formatter)
    log.addHandler(handler)

    # update config
    conf = cf_func.update_config(conf, args.local_config_file)

    # run test
    if args.force_upload > 0:
        run_manual(conf, args.force_upload)
    else:
        run_test(conf)

else:
    log = logging.getLogger()  # import root logger

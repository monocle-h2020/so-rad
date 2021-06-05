#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Data export functions

For routine operation from a parent script, call the run_manual function, passing the general (parsed) config object
Data from the local database will be inspected and any missing metadata elements will be added based on what is provided in the config(-local).ini file.

Can be called from the command line to force upload of data (scenario: So-Rad has been running offline,
  you want to upload all data after connecting it via a phone during deployment, or after retrieving it).
If called from command line without the force_manual attribute (specifying how many records to upload),
  this script will run in test-mode, showing whether any records remain to be uploaded and checking connectivity to local and remote data stores.

It is possible for this process to create a database lock, so it is best to run it while not also storing new records (run as part of main_app loop, or stop the main app first)
The main app will ignore and recover from a database lock but the new record will be lost.
We cannot open the database in read-only mode to work around this because we want to store an upload succes in the database itself to ignore such records in future attempts.
Similarly, it is possible for the main_app to create a database lock while this process tries to store an upload result, which would also not be ideal.
When run as part of the main_app loop, it is advisable to include a limit on the number of records to process: your ship might be approaching shore, and have a poor data connection at first.
While uploads are still slow and possibly time out, it would be nice to continue taking measurements. There will be plenty of time to upload all the buffered data on subsequent cycles, or once the ship is in port.

The config-local.ini file will provide any keys required to access the remote store.
"""

import os
import sys
import traceback
import logging
import sqlite3
import argparse
import json
import uuid
import requests
import config_functions as cf_func
import db_functions as db_func
from numpy import unique

def db_init(db_config):
    """set up and test sqlite database connection. Return dictionary with database config"""
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


def run_export(conf, limit=1, test_run=True, dbfile=None):
    """
    Main function
    """
    db = db_init(conf['DATABASE'])
    if dbfile is not None:
        db['file'] = dbfile

    export_config_dict = conf['EXPORT']
    n_total, n_new, records, header = identify_new_local_records(db, limit=limit)
    log.debug("records={0}, not_uploaded={1}".format(n_total, n_new))

    if 'sample_uuid' not in header:
        # match records to add a single sample_uuid to records with identical metadata_id
        i = header.index('metadata_id')
        meta_ids = unique([record[i] for record in records])
        sample_uuids = dict(zip(meta_ids, [str(uuid.uuid1()) for m in meta_ids]))
        header.append('sample_uuid')
        for j, record in enumerate(records):
            records[j] = record + (sample_uuids[record[i]],)

    for i, record in enumerate(records):
        record_json = add_metadata(export_config_dict, record, header)  # add metadata and return json
        log.debug("{0}/{1} JSON formatted record: {2}".format(i, len(records)-1, record_json))

        if not test_run:
            export_to_parse_server(export_config_dict, record_json)


def add_metadata(export_config_dict, record, header):
    """make complete data record"""
    record_as_dict = dict(zip(header, record))

    # metadata from export section of config (operator-defined)
    record_as_dict['platform_id']       = export_config_dict.get('platform_id')
    record_as_dict['owner_contact']     = export_config_dict.get('owner_contact')
    record_as_dict['operator_contact']  = export_config_dict.get('operator_contact')
    record_as_dict['license']           = export_config_dict.get('license')
    record_as_dict['license_reference'] = export_config_dict.get('license_reference')

    # add the following if not already present
    if 'processing_level' not in record_as_dict:
        record_as_dict['processing_level'] = 0

    json_record = json.dumps(record_as_dict)

    return json_record


def export_to_parse_server(export_config_dict, json_record):
    """attempt to upload a record to a remote Parse server"""
    parse_app_url = export_config_dict.get('parse_url')  # something like https:1.2.3.4:port/parse/classes/sorad
    parse_app_id = export_config_dict.get('parse_app_id')

    headers = {'content-type': 'application/json',
               'X-Parse-Application-Id': parse_app_id}
    response = requests.post(parse_app_url, data=json_record, headers=headers)

    return response


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
    if limit is None:
        limit = n_not_inserted

    # query records not yet uploaded, youngest records first up to any specified limit. Includes metadata + radiometry
    sql_meta = """SELECT meta.id_ FROM sorad_metadata meta WHERE meta.n_rad_obs > 0 AND (meta.sos_inserted IS NULL OR meta.sos_inserted=0) ORDER BY meta.id_ DESC LIMIT ?"""
    cur.execute(sql_meta, (limit,))
    meta_ids = cur.fetchall()

    join_sql = "INNER JOIN sorad_metadata meta ON meta.id_ = rad.metadata_id"
    log.debug("retrieving {0} records".format(limit))
    sql_last_not_inserted = """SELECT * FROM sorad_radiometry rad {join} WHERE rad.metadata_id IN ({sqlm})""".format(join=join_sql, sqlm=sql_meta)
    cur.execute(sql_last_not_inserted, (limit,))

    all_not_inserted = cur.fetchall()
    last_not_inserted = all_not_inserted[0]

    conn.close()

    return n_total, n_not_inserted, all_not_inserted, header_rad+header_meta


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

    formatter = logging.Formatter('%(asctime)s|%(levelname)s| %(message)s')
    handler.setFormatter(formatter)
    log.addHandler(handler)

    # update config with local overrides
    conf = cf_func.update_config(conf, args.local_config_file)

    if args.force_upload > 0:
        limit = args.force_upload
        test_run = False
    else:
        limit = 1
        test_run = True

    run_export(conf, limit=limit, test_run=test_run)

else:
    log = logging.getLogger('export')  # import root logger
    log.setLevel(logging.INFO)

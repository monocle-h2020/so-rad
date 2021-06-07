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
import time

TIMEOUT=1.5  # timeout for getting any response update from the remote server to prevent main program gettting stuck too long.


def db_init(db_config, dbfile):
    """set up and test local sqlite database connection. Return dictionary with database config"""
    db = {}
    db['used'] = db_config.getboolean('use_database')
    # If it is used, check the type of db
    try:
        assert db_config.get('database_type') == "sqlite3"
    except AssertionError:
        msg = "database_type {0} not recognized. Only sqlite3 is supported".format(db_config['database_type'])
        log.critical(msg)
        raise AssertionError(msg)

    # either use the db defined in config (default) or the alternative provided from the command line
    db['file'] = db_config.get('database_path')
    if dbfile is not None:
        db['file'] = os.path.abspath(dbfile)
        log.info("User-specified database: {0}".format(dbfile))

    conn, cur = db_func.connect_db(db)
    try:
        header_meta = column_names(conn, cur, table="sorad_metadata")
        header_rad = column_names(conn, cur, table="sorad_radiometry")
        db['header'] = header_rad + header_meta
    except Exception as err:
        msg = "Error connecting to database: \n {0}".format(err)
        log.critical(msg)
        conn.close()
        raise Exception(msg)

    conn.close()

    if 'sos_inserted' in header_meta:
        log.debug("Database format < June 2021")
        db['export_success_field']  = 'sos_inserted'
        db['export_attempts_field'] = 'sos_insertion_attempts'
    else:
        log.debug("Databse format > June 2021")
        db['export_success_field']  = 'export_success'
        db['export_attempts_field'] = 'export_attempts'

    # location info may also have changed with different versions
    if 'location' not in header_meta:
       if 'gps_lat' in header_meta:
           db['lat_field'] = 'gps_lat'
           db['lon_field'] = 'gps_long'
       else:
           log.critical("Lat/lon fields not recognised in database")

    if 'time' not in header_meta:
       if 'gps_time' in header_meta:
           db['time_field'] = 'gps_time'
       else:
           log.critical("time field not recognised in database")

    return db


def run_export(conf, limit=1, test_run=True, dbfile=None):
    """
    Main function
    """
    db = db_init(conf['DATABASE'], dbfile)

    export_config_dict = conf['EXPORT']
    n_total, n_new, records = identify_new_local_records(db, limit=limit)
    log.debug("records={0}, not_uploaded={1}".format(n_total, n_new))

    if 'sample_uuid' not in db['header']:
        # match records to add a single sample_uuid to records with identical metadata_id
        i = db['header'].index('metadata_id')
        meta_ids = unique([record[i] for record in records])
        sample_uuids = dict(zip(meta_ids, [str(uuid.uuid1()) for m in meta_ids]))
        db['header'].append('sample_uuid')
        for j, record in enumerate(records):
            records[j] = record + (sample_uuids[record[i]],)

    for i, record in enumerate(records):
        record_json = add_metadata(export_config_dict, record, db)  # add metadata and return json
        log.debug("{0}/{1} JSON formatted record: {2}".format(i, len(records)-1, record_json))

        if test_run:
            continue

        response = export_to_parse_server(export_config_dict, record_json)
        log.debug("Remote server response was: {0}".format(response))
        if (response.status_code >= 200) and (response.status_code < 300):
            log.info("Record {0} uploaded succesfully".format(json.loads(record_json)['id_']))
            export_result = True
        else:
            log.debug("Export failed, try again later")
            export_result = False

        update_local_db(db, json.loads(record_json)['id_'], export_result, record_json)


def update_local_db(db, metadata_id, export_result, record_json):
    """
    update the local db once a record export attempt has been completed. Try to access the local database several times to circumvent temporary locks.
    """
    conn, cur = db_func.connect_db(db)
    record_dict = json.loads(record_json)
    log.debug(record_dict)
    #attempts = record_dict[db['export_attempts_field']] += 1
    attempts = 1
    attempts_field= db['export_attempts_field']
    success_field = db['export_success_field']

    sql_update = f"""UPDATE sorad_metadata SET {success_field} = ?, {attempts_field} = {attempts} WHERE id_ = ?"""

    db_update_attempt = 0
    done = False
    while (not done) and (db_update_attempt < 5):
        try:
            cur.execute(sql_update, (export_result, metadata_id))
            conn.commit()
            done = True
            log.info(f"Updated local db record {metadata_id}")
        except Exception as msg:
            log.exception(msg)
            time.sleep(0.2) * db_update_attempt**2
            db_update_attempt += 1
    conn.close()
    return


def add_metadata(export_config_dict, record, db):
    """make complete data record"""
    record_as_dict = dict(zip(db['header'], record))

    # metadata from export section of config (operator-defined)
    record_as_dict['platform_id']       = export_config_dict.get('platform_id')
    record_as_dict['owner_contact']     = export_config_dict.get('owner_contact')
    record_as_dict['operator_contact']  = export_config_dict.get('operator_contact')
    record_as_dict['license']           = export_config_dict.get('license')
    record_as_dict['license_reference'] = export_config_dict.get('license_reference')

    # add the following if not already present
    if 'processing_level' not in record_as_dict:
        record_as_dict['processing_level'] = 0

    # create location object
    if 'location' not in record_as_dict:
        record_as_dict['location'] = json.dumps({'__type': 'GeoPoint',
                                                 'latitude': record_as_dict[db['lat_field']],
                                                 'longitude': record_as_dict[db['lon_field']]})
    if 'time' not in record_as_dict:
        record_as_dict['time'] = record_as_dict[db['time_field']]

    json_record = json.dumps(record_as_dict)

    return json_record


def export_to_parse_server(export_config_dict, json_record):
    """attempt to upload a record to a remote Parse server"""
    parse_app_url = export_config_dict.get('parse_url')  # something like https:1.2.3.4:port/parse/classes/sorad
    parse_app_id = export_config_dict.get('parse_app_id')  # ask the parse server admin for this key

    headers = {'content-type': 'application/json',
               'X-Parse-Application-Id': parse_app_id}
    response = requests.post(parse_app_url, data=json_record, headers=headers, timeout=TIMEOUT)  # timeout of 1.5 seconds prevents main program loop from getting stuck too long

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

    # query number of radiometry samples in database
    sql_n_total = """SELECT count(*) FROM sorad_metadata WHERE n_rad_obs > 0"""
    cur.execute(sql_n_total)
    n_total = cur.fetchone()[0]

    # query number of radiometry samples not yet uploaded
    sql_n_not_inserted = """SELECT count(*) FROM sorad_metadata WHERE n_rad_obs > 0 AND ({success} IS NULL OR {success}=0)""".\
                         format(success=db['export_success_field'])

    cur.execute(sql_n_not_inserted)
    n_not_inserted = cur.fetchone()[0]
    if limit is None:
        limit = n_not_inserted

    # query records not yet uploaded, youngest records first up to any specified limit. Includes metadata + radiometry
    #  can we try records with a high number of export tries, last? To prevent getting stuck on a possibly corrupt record?
    sql_meta = """SELECT meta.id_ FROM sorad_metadata meta WHERE meta.n_rad_obs > 0 AND ({success} IS NULL OR {success}=0) ORDER BY meta.id_ DESC LIMIT ?""".\
               format(success=db['export_success_field'])

    cur.execute(sql_meta, (limit,))
    meta_ids = cur.fetchall()
    join_sql = "INNER JOIN sorad_metadata meta ON meta.id_ = rad.metadata_id"
    log.debug("retrieving {0} sample(s) containing {1} records".format(limit, len(meta_ids)))
    sql_last_not_inserted = """SELECT * FROM sorad_radiometry rad {join} WHERE rad.metadata_id IN ({sqlm})""".format(join=join_sql, sqlm=sql_meta)
    cur.execute(sql_last_not_inserted, (limit,))

    all_not_inserted = cur.fetchall()
    last_not_inserted = all_not_inserted[0]

    conn.close()

    return n_total, n_not_inserted, all_not_inserted


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

    run_export(conf, limit=limit, test_run=test_run, dbfile=args.source)

else:
    log = logging.getLogger('export')  # import root logger
    log.setLevel(logging.INFO)

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Data export functions

For routine operation from a parent script call the run_export function, passing the general config object
Data from the local database will be inspected and any missing metadata elements will be added to records based on what is provided in the config(-local).ini file.

This can be called from the command line to force upload of data (scenario: So-Rad has been running offline, run to catch up after re-connecting it.
If called from command line without the force_manual attribute (specifying how many records to upload),
  this script will run in test-mode, showing whether any records remain to be uploaded and checking connectivity to local and remote data stores.

Note: it is possible for this process to create a database lock, so it should be timed not to interfere with creation of new records.
If the main app is locked out of the databse it will ignore and recover but the new record will be lost.
Similarly, this process will only try a few times to update the database to mark a record as uploaded.

When run as part of the main_app loop, it is advisable to include a limit on the number of records to process: your ship might be approaching shore, and have a poor data connection at first.
While uploads are still slow and possibly time out, it would be nice to continue taking measurements. There will be plenty of time to upload all the buffered data on subsequent cycles, or once the ship is in port.

The recommended (and currently implemented) way to run this code is on small data batches whenever the main program loop needs to wait anyway.

The config-local.ini file will provide any keys required to access the remote store. These should be kept out of system logs.
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
from . import db_functions as db_func
from numpy import unique
import time
import datetime
#from requests_toolbelt.utils import dump

TIMEOUT=5  # timeout for getting a response on data upload. 
TIMEOUT_SHORT = 1 # timeout for getting response on connectivity tests, status queries

log = logging.getLogger('export')
#log.setLevel('DEBUG')

def run_export(export_config_dict, db, limit=1, test_run=True, version=None, update_local=True, fail_limit=10):
    """
    Main function

    :test_run bool:  will only read, not export or write
    :version float:  will limit activity to data associated with a specific sorad_version in the db
    :update_local bool: update the local db file with the export status (success/fail) and number of attempts to export
    """
    n_total, n_new, records = identify_new_local_records(db, limit=limit, version=version)
    log.debug("records={0}, not_uploaded={1}".format(n_total, n_new))

    successes = 0
    failures = 0
    export_result = None
    response_code = None

    if n_new == 0:
        return export_result, response_code, successes

    if db['add_sample_uuid']:
        log.debug("Adding sample_uuid")
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
            export_result = None
            response_code = None
            continue

        export_result, response_code, response = export_to_parse_server(export_config_dict, record_json)
        log.debug("Remote server response was: {0}".format(response_code))

        #respdata = dump.dump_all(response)
        #log.debug(respdata.decode('utf-8'))  # dump the http request (super-debug!)

        if export_result:
            log.debug(f"{i}/{len(records)} Record {json.loads(record_json)['id_']} uploaded succesfully")
            successes += 1
            if update_local:
                update_local_db(db, json.loads(record_json)['id_'], export_result, record_json, test_run)

        else:
            log.debug("Data upload failed, try again later")
            update_local_db(db, json.loads(record_json)['id_'], export_result, record_json)
            failures += 1
            if failures >= fail_limit:
                return export_result, response_code, successes


    return export_result, response_code, successes


def update_local_db(db, metadata_id, export_result, record_json, test_run=False):
    """
    update the local db once a record export attempt has been completed. Try to access the local database several times to circumvent temporary locks.
    """
    log = logging.getLogger('export.updatelocaldb')
    rec = json.loads(record_json)
    conn, cur = db_func.connect_db(db)
    record_dict = json.loads(record_json)
    attempts_field= db['export_attempts_field']
    success_field = db['export_success_field']
    attempts = rec[attempts_field]
    if attempts is None:
        attempts = 1
    else:
        attempts = int(attempts) + 1
    log.debug(f"update record {metadata_id} with attempts {rec[attempts_field]} -> {attempts} and succes={export_result}")
    sql_update = f"""UPDATE sorad_metadata SET {success_field} = ?, {attempts_field} = {attempts} WHERE id_ = ?"""

    db_update_attempt = 0
    done = False
    while (not done) and (db_update_attempt < 5):
        try:
            if test_run:
                cur.execute(sql_update, (export_result, metadata_id))
                conn.rollback()
            else:
                cur.execute(sql_update, (export_result, metadata_id))
                conn.commit()
                done = True
                log.debug(f"Updated local db record {metadata_id}")
        except Exception as msg:
            log.warning(msg)
            time.sleep(0.2) * db_update_attempt**2
            db_update_attempt += 1
    conn.close()
    return


def add_metadata(export_config_dict, record, db):
    """make complete data record"""
    record_as_dict = dict(zip(db['header'], record))

    # metadata from export section of config (operator-defined)
    record_as_dict['content']           = "observation"
    record_as_dict['platform_id']       = export_config_dict['platform_id']
    record_as_dict['owner_contact']     = export_config_dict['owner_contact']
    record_as_dict['operator_contact']  = export_config_dict['operator_contact']
    record_as_dict['license']           = export_config_dict['license']
    record_as_dict['license_reference'] = export_config_dict['license_reference']
    record_as_dict['platform_uuid']     = export_config_dict['platform_uuid']

    # add the following if not already present
    if 'processing_level' not in record_as_dict:
        record_as_dict['processing_level'] = 0

    for key, val in record_as_dict.items():
        # replace gps1_ with gps_ in keys
        if 'gps1_' in key:
            record_as_dict[key.replace('gps1_', 'gps_')] = record_as_dict.pop(key)
            try:
                del record_as_dict[key.replace('gps1_', 'gps2_')]
            except: pass

    # create location object
    if 'location' not in record_as_dict:
        record_as_dict['location'] = json.dumps({'__type': 'GeoPoint',
                                                 'latitude': record_as_dict['gps_lat'],
                                                 'longitude': record_as_dict['gps_long']})
    if 'time' not in record_as_dict:
        record_as_dict['time'] = record_as_dict['gps_time']
        del record_as_dict['gps_time']

    if 'time_source' not in record_as_dict:
        record_as_dict['time_source'] = 'GNSS'  # So-Rad always takes time/pos from a GNSS device.

    if 'sensor_type' not in record_as_dict:
        record_as_dict['sensor_type'] = 'trios_ramses'  # when implementing other sensors derive from radiometry config - protocol (= pytrios)

    json_record = json.dumps(record_as_dict)

    return json_record


def export_to_parse_server(export_config_dict, json_record):
    """attempt to upload a record to a remote Parse server"""
    parse_app_url = export_config_dict['parse_url']  # something like https://1.2.3.4:port/parse/classes/sorad
    parse_app_id = export_config_dict['parse_app_id']  # ask the parse server admin for this key
    parse_clientkey = export_config_dict['parse_clientkey']
    headers = {'content-type': 'application/json',
               'X-Parse-Application-Id': parse_app_id,
               'X-Parse-Client-Key': parse_clientkey}

    try:
        response = requests.post(parse_app_url, data=json_record, headers=headers, timeout=TIMEOUT)  # timeout of 1.5 seconds prevents main program loop from getting stuck too long
        if (response.status_code >= 200) and (response.status_code < 300):
            return True, response.status_code, response
        else:
            return False, response.status_code, response

    except requests.exceptions.ReadTimeout:
        log.warning("Timeout while uploading data to remote server")
        return False, None, None
    except Exception as err:
        log.warning("Unhandled exception while uploading data to remote server")
        #log.exception(err)
        return False, None, None


def update_on_parse_server(export_config_dict, json_record, objectId):
    """attempt to upload a record to a remote Parse server"""
    parse_app_url = export_config_dict['parse_url'] + f"/{objectId}"   # something like https://1.2.3.4:port/parse/classes/sorad/dfjwf3df
    parse_app_id = export_config_dict['parse_app_id']                  # ask the parse server admin for this key
    parse_clientkey = export_config_dict['parse_clientkey']
    headers = {'content-type': 'application/json',
               'X-Parse-Application-Id': parse_app_id,
               'X-Parse-Client-Key': parse_clientkey}

    try:
        response = requests.put(parse_app_url, data=json_record, headers=headers, timeout=TIMEOUT)
        if (response.status_code >= 200) and (response.status_code < 300):
            return True, response.status_code
        else:
            return False, response.status_code
    except requests.exceptions.ReadTimeout:
        log.warning("Timeout while updating status on remote server")
        return False, None
    except:
        log.warning("Unhandled exception while updating status on remote server")
        return False, None


def update_status_parse_server(export_config_dict, db):
    "Update latest status update on Parse server. A status update has the 'content' field set to 'status' and only contains a metadata record"

    parse_app_url = export_config_dict['parse_url']  # something like https://1.2.3.4:port/parse/classes/sorad
    parse_app_id = export_config_dict['parse_app_id']  # ask the parse server admin for this key and store it in local-config.ini
    platform_id = export_config_dict['platform_id']
    parse_clientkey = export_config_dict['parse_clientkey']
    headers = {'content-type': 'application/json',
               'X-Parse-Application-Id': parse_app_id,
               'X-Parse-Client-Key': parse_clientkey}

    data =   json.dumps({"where":{"platform_id":platform_id, "content": "status"}, "order": "-updatedAt", "limit": 1, "keys": "updatedAt,gps_time,pc_time"})
    try:
        response = requests.get(parse_app_url, data=data, headers=headers, timeout=TIMEOUT_SHORT)
        if (response.status_code < 200) or (response.status_code) > 299:
            # the request failed this time
            return False, None
    except requests.exceptions.ReadTimeout:
        log.warning("Timeout while getting status record from remote server")
        return False, None
    except:
        log.warning("Unhandled exception while getting status record from remote server")
        return False, None

    # collect data from local db
    sql_meta = """SELECT * FROM sorad_metadata meta ORDER BY meta.id_ DESC LIMIT 1"""
    conn, cur = db_func.connect_db(db)
    cur.execute(sql_meta)
    meta_local = cur.fetchall()  # list containing only the latest local db record, if any
    conn.close()
    if len(meta_local) > 0:
        meta_local = meta_local[0] # latest local db record
    else:
        # no data in local database
        return False, None

    meta_as_dict = dict(zip(db['header_meta'], meta_local))
    meta_as_dict['content']           = "status"
    meta_as_dict['platform_id']       = export_config_dict['platform_id']
    meta_as_dict['platform_uuid']     = export_config_dict['platform_uuid']
    meta_as_dict['owner_contact']     = export_config_dict['owner_contact']
    meta_as_dict['operator_contact']  = export_config_dict['operator_contact']

    for key, val in meta_as_dict.items():
        # replace gps1_ with gps_ in keys
        if 'gps1_' in key:
            meta_as_dict[key.replace('gps1_', 'gps_')] = meta_as_dict.pop(key)
            try:
                del meta_as_dict[key.replace('gps1_', 'gps2_')]
            except: pass

    # create location object
    if 'location' not in meta_as_dict:
        meta_as_dict['location'] = json.dumps({'__type': 'GeoPoint',
                                                 'latitude': meta_as_dict['gps_lat'],
                                                 'longitude': meta_as_dict['gps_long']})
    if 'time' not in meta_as_dict:
        meta_as_dict['time'] = meta_as_dict['gps_time']
        del meta_as_dict['gps_time']

    if 'time_source' not in meta_as_dict:
        meta_as_dict['time_source'] = 'GNSS'  # So-Rad always takes time/pos from a GNSS device.

    if 'sensor_type' not in meta_as_dict:
        meta_as_dict['sensor_type'] = 'trios_ramses'  # when implementing other sensors derive from radiometry config - protocol (= pytrios)

    meta_json = json.dumps(meta_as_dict)

    # inspect the remote server response
    response = response.json()
    if len(response['results']) == 0:
        # request succeeded but no object was found (remote store was likely cleared, or this is a new platform ID). Attempt to upload a new status record.
        export_result, resultcode, response = export_to_parse_server(export_config_dict, meta_json)
        if not export_result:
            log.debug("Status record creation failed, try again later")
        else:
            log.debug("New status record created at remote store")

    else:
        # get time of last update and corresponding objectID and update with latest system info
        response = response['results'][0]
        last_update = datetime.datetime.strptime(response['updatedAt'], '%Y-%m-%dT%H:%M:%S.%fZ')
        objectId = response['objectId']
        log.debug(f"Last update record on remote server ID {objectId} at {last_update} (server time)")
        export_result, resultcode = update_on_parse_server(export_config_dict, meta_json, objectId)

    return export_result, resultcode


def identify_new_local_records(db, limit=10, version=None):
    """report on total and new (not uploaded) records, latest record"""
    log = logging.getLogger('export.scanlocal')

    n_total = 0
    n_uploaded = 0
    conn, cur = db_func.connect_db(db)

    # query number of radiometry samples in database
    sql_n_total = """SELECT count(*) FROM sorad_metadata WHERE n_rad_obs > 0"""
    cur.execute(sql_n_total)
    n_total = cur.fetchone()[0]

    # query number of radiometry samples in database with specific software version
    if version is not None:
        sql_n_version = """SELECT count(*) FROM sorad_metadata WHERE n_rad_obs > 0 AND sorad_version = ? AND ({success} IS NULL OR {success}=0)""".format(success=db['export_success_field'])

        cur.execute(sql_n_version, (version,))
        n_version = cur.fetchone()[0]

    if logging.getLevelName(log.level) == 'DEBUG':
        sql_all_versions = """SELECT sorad_version, count(*) FROM sorad_metadata WHERE n_rad_obs > 0 GROUP BY sorad_version"""
        cur.execute(sql_all_versions)
        versions = cur.fetchall()
        for ver in versions:
            log.info(f"{ver}")

    # query number of radiometry samples not yet uploaded
    if version is not None:
        sql_n_not_inserted = """SELECT count(*) FROM sorad_metadata WHERE n_rad_obs > 0 AND ({success} IS NULL OR {success}=0) AND sorad_version = {version}""".\
                             format(success=db['export_success_field'], version=version)
    else:
        sql_n_not_inserted = """SELECT count(*) FROM sorad_metadata WHERE n_rad_obs > 0 AND ({success} IS NULL OR {success}=0)""".\
                             format(success=db['export_success_field'], version=version)

    cur.execute(sql_n_not_inserted)
    n_not_inserted = cur.fetchone()[0]
    if limit is None:
        limit = n_not_inserted
    if limit == 0:
       # skip retrieving any records, just return db stats
       return n_total, n_not_inserted, None

    # query records not yet uploaded, youngest records first up to any specified limit. Includes metadata + radiometry
    #  can we try records with a high number of export tries, last? To prevent getting stuck on a possibly corrupt record?
    if version is not None:
        sql_meta = """SELECT meta.id_ FROM sorad_metadata meta WHERE meta.n_rad_obs > 0 AND ({success} IS NULL OR {success}=0) AND sorad_version = {version} ORDER BY meta.id_ DESC LIMIT ?""".\
                   format(success=db['export_success_field'], version=version)
    else:
        sql_meta = """SELECT meta.id_ FROM sorad_metadata meta WHERE meta.n_rad_obs > 0 AND ({success} IS NULL OR {success}=0) ORDER BY meta.id_ DESC LIMIT ?""".\
                   format(success=db['export_success_field'])

    cur.execute(sql_meta, (limit,))
    meta_ids = cur.fetchall()
    join_sql = "INNER JOIN sorad_metadata meta ON meta.id_ = rad.metadata_id"
    log.debug("retrieving {0} sample(s) containing {1} records".format(limit, len(meta_ids)))
    sql_last_not_inserted = """SELECT * FROM sorad_radiometry rad {join} WHERE rad.metadata_id IN ({sqlm})""".format(join=join_sql, sqlm=sql_meta)
    cur.execute(sql_last_not_inserted, (limit,))

    all_not_inserted = cur.fetchall()

    conn.close()

    return n_total, n_not_inserted, all_not_inserted

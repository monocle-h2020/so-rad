#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Data download functions

Support downloads via web interface
- database dumps for a given timeframe
- HDF for a given timeframe
"""

import os
import sys
import logging
import logging.handlers
import sqlite3
import datetime
import functions.db_functions as db_func

log = logging.getLogger('download')
#log.setLevel('DEBUG')


def init_job_logger(logfilepath):
    """
    Separate logging for jobs from redis queue
    """
    logging.basicConfig(level='INFO', stream=sys.stdout)
    filehandler = logging.handlers.RotatingFileHandler(logfilepath, mode='a',
                                                       maxBytes=1024*2024,
                                                       backupCount=5)
    filehandler.setLevel('INFO')
    log = logging.getLogger('worker')
    log.addHandler(filehandler)
    return log

def csv_from_web_request(conf, start_time, end_time, platform_id):
    """
    Handle a csv generation request from the web service (via redis queue).
    conf is the config read by configparser containing 'DATABASE' and 'DOWNLOAD' sections
    """
    data_folder = conf['DOWNLOAD'].get('storage_path')
    logfilename = os.path.join(data_folder, 'csv_log.txt')
    db_dict = {'file': conf['DATABASE'].get('database_path')}

    try:
        log = init_job_logger(logfilename)
        conn, cur = db_func.connect_db(db_dict)
        meta_columns = db_func.column_names(conn, cur, table="sorad_metadata")
        data_columns = db_func.column_names(conn, cur, table="sorad_radiometry")
        conn.close()

        records = identify_records(db_dict, start_time, end_time)

        outfile = os.path.join(data_folder,
                               filename_from_dates(platform_id,
                                                   start_time, end_time,
                                                   format='csv'))

        save_to_csv(records, outfile, meta_columns, data_columns)

        log.info(f"Saved {outfile}")

    except Exception as err:
        print(err)


def filename_from_dates(platform_id, start_time, end_time, format='csv'):
    """Generate filename from dates"""
    start_str = datetime.datetime.strftime(start_time, "%Y%m%dT%H%M%S")
    end_str =   datetime.datetime.strftime(end_time,   "%Y%m%dT%H%M%S")
    out_filepath = f"{platform_id}_{start_str}-{end_str}.{format}"
    return out_filepath


def save_to_csv(records, destination_file, meta_columns, data_columns):
    """
    Save records to a csv file
    """
    # adapt header to database columns
    header = ",".join(meta_columns+data_columns)
    meas_index = len(meta_columns) + data_columns.index('measurement') # where is the spectrum array

    with open(destination_file, 'w') as op:
        op.write(header + '\n')
        for r in records:
             dataline = ",".join([str(v).replace("[","").replace("]","") for v in r])
             op.write(dataline + '\n')


def identify_records(db_dict, start_time=None, end_time=None):
    """
    Collect information on database records within a given timeframe
    """
    conn, cur = db_func.connect_db(db_dict)
    conn.set_trace_callback(log.info)

    # query number of radiometry samples in database
    sql_n_total = """SELECT count(*) FROM sorad_metadata WHERE n_rad_obs > 0"""
    cur.execute(sql_n_total)
    n_total = cur.fetchone()[0]

    # query records in timeframe
    # SELECT gps_time FROM sorad_metadata WHERE gps_time BETWEEN '2025-09-30 08:00:00' and '2025-09-30 12:00:00'
    sql = """SELECT meta.*, rad.*
              FROM sorad_metadata meta
               LEFT JOIN sorad_radiometry rad
                ON rad.metadata_id = meta.id_
             WHERE meta.n_rad_obs > 0
              AND meta.gps_time BETWEEN ? and ?
             ORDER BY meta.gps_time ASC
           """
    try:
        assert isinstance(start_time, datetime.datetime)
        assert isinstance(end_time, datetime.datetime)
    except AssertionError:
        raise ValueError(f"Start and end of request must be an instance of datetime.datetime, not {type(start_time)}, {type(end_time)}")

    start_str = datetime.datetime.strftime(start_time, '%Y-%m-%d %H:%M:%S')
    end_str = datetime.datetime.strftime(end_time, '%Y-%m-%d %H:%M:%S')

    cur.execute(sql, (start_str, end_str))
    returned = cur.fetchall()
    conn.close()
    log.info(f"{len(returned)} results returned from database")

    return returned

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
import sqlite3
import datetime
from . import db_functions as db_func

log = logging.getLogger('download')
#log.setLevel('DEBUG')

def save_to_csv(records, data_folder, platform_id, start_time, end_time, meta_columns, data_columns):
    """
    Save records to a csv file
    """
    if len(records) == 0:
        log.info("No records to save")
        return

    # make filename friendly labels
    start_str = datetime.datetime.strftime(start_time, "%Y%m%dT%H%M%S")
    end_str =   datetime.datetime.strftime(end_time,   "%Y%m%dT%H%M%S")

    out_filepath = os.path.join(os.path.dirname(data_folder),
                                f"{platform_id}_{start_str}-{end_str}.csv")
    header = ",".join(meta_columns+data_columns)
    meas_index = len(meta_columns) + data_columns.index('measurement') # where is the spectrum array

    with open(out_filepath, 'w') as op:
        op.write(header + '\n')
        for r in records:
             dataline = ",".join([str(v).replace("[","").replace("]","") for v in r])
             op.write(dataline + '\n')


def identify_records(db, start_time=None, end_time=None):
    """
    Collect information on database records within a given timeframe
    """

    conn, cur = db_func.connect_db(db)
    conn.set_trace_callback(log.info)

    # query number of radiometry samples in database
    sql_n_total = """SELECT count(*) FROM sorad_metadata WHERE n_rad_obs > 0"""
    cur.execute(sql_n_total)
    n_total = cur.fetchone()[0]

    # query records in timeframe
    sql = """SELECT meta.*, rad.*
              FROM sorad_metadata meta
               LEFT JOIN sorad_radiometry rad
                ON rad.metadata_id = meta.id_
             WHERE meta.n_rad_obs > 0
              AND meta.gps_time >= ?
              AND meta.gps_time < ?
             ORDER BY meta.gps_time ASC
           """

    try:
        assert isinstance(start_time, datetime.datetime)
        assert isinstance(end_time, datetime.datetime)
    except AssertionError:
        raise ValueError("Start and end of request must be an instance of datetime.datetime")

    cur.execute(sql, (start_time.isoformat(), end_time.isoformat()))
    returned = cur.fetchall()
    conn.close()
    log.info(f"{len(returned)} results returned from database")

    return returned

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
import h5py

log = logging.getLogger('download')
#log.setLevel('DEBUG')


def hdf_from_web_request(conf, start_time, end_time, platform_id):
    """
    Handle an hdf generation request from the web service (via redis queue).
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

        save_to_hdf(records, outfile, meta_columns, data_columns)

        log.info(f"Saved {outfile}")

    except Exception as err:
        log.exception(err)


def extract_arrays_from_records(records, meta_columns, data_columns):
    """
    Parse the database records to numpy arrays
    records: list of records returned from database
    meta_columns: columns in the sorad_metadata table
    data_columns: column names of the sorad_radiometry table
    """
    # identify and harmonize all data types,
    # from the order in which they appear in database columns
    db_columns = meta_columns + data_columns

    # parse spectra
    spectra_index = db_columns.index('measurement')
    spectra = []
    corrupt = []
    for i, r in enumerate(records):
        spectrum = r[spectra_index] # comma+space-separated string
        spectrum = spectrum.replace("[","").replace("]","").split(", ")
        if 'None' in spectrum:
            # these spectra are corrupt, mark record for deletion
            corrupt.append(i)
        else:
            spectrum = [int(s) for s in spectrum]
            spectra.append(spectrum)

    sample_uuids =    [rec[db_columns.index('sample_uuid')] for i, rec in enumerate(records) if i not in corrupt]   # str
    times =           [rec[db_columns.index('gps_time')] for i, rec in enumerate(records) if i not in corrupt]      # str -> datetime below
    lats =            [rec[db_columns.index('gps_lat')] for i, rec in enumerate(records) if i not in corrupt]       # float
    lons =            [rec[db_columns.index('gps_long')] for i, rec in enumerate(records) if i not in corrupt]      # float
    gps_speeds =      [rec[db_columns.index('gps_speed')] for i, rec in enumerate(records) if i not in corrupt]     # float
    tilt_avgs =       [rec[db_columns.index('tilt_avg')] for i, rec in enumerate(records) if i not in corrupt]      # float
    tilt_stds =       [rec[db_columns.index('tilt_std')] for i, rec in enumerate(records) if i not in corrupt]      # float
    rel_view_azs =    [rec[db_columns.index('rel_view_az')] for i, rec in enumerate(records) if i not in corrupt]   # float
    sensor_ids =      [rec[db_columns.index('sensor_id')] for i, rec in enumerate(records) if i not in corrupt]     # str
    inttimes =        [rec[db_columns.index('inttime')] for i, rec in enumerate(records) if i not in corrupt]       # int

    # parse timestamps, comply with mlb format
    times = [datetime.datetime.strptime(t, '%Y-%m-%d %H:%M:%S.%f') for t in times]
    # datetag is fractional days from 1900
    datetag_reference = datetime.datetime(1900,1,1,0,0,0)
    datetag_timedeltas = [t - datetag_reference for t in times]
    datetags = [t.days + (t.seconds/(24.*60.*60.)) + (t.microseconds/(1000000.*24.*60.*60.)) for t in datetag_timedeltas]
    # datetag2 = YYYYjjj where jjj is day of year
    datetag2s = [float(datetime.datetime.strftime(t, '%Y%j')) for t in times]
    # timetags
    timetag2s = [float(datetime.datetime.strftime(t, "%H%M%S.%f")[:-3]) for t in times]
    # not stored in local db: platform_ids, platform_uuids, ed_inttime, ls_inttime, lt_inttime

    return sample_uuids, \
      times, datetags, datetag2s, timetag2s, \
      lats, lons, \
      gps_speeds, \
      tilt_avgs, tilt_stds, \
      rel_view_azs, \
      inttimes, \
      sensor_ids, spectra

def save_to_hdf(records, destination_file, meta_columns, data_columns):
    """
    Save records to a hdf format, e.g. for ingestion by HyperCP
    """
    # adapt header to database columns

    # Store core Sorad metadata, including sensor integration times in a dataframe
    #d = access.meta_l0_dataframe(sample_uuids, platform_ids, platform_uuids, time, lat, lon, gps_speed, tilt_avg, tilt_std, rel_view_az, ed_inttime, ls_inttime, lt_inttime, sensor_ids)
    sample_uuids, times, datetags, datetag2s, timetag2s, \
      lats, lons, \
      gps_speeds, \
      tilt_avgs, tilt_stds, \
      rel_view_azs, \
      inttimes, \
      sensor_ids, spectra = extract_arrays_from_records(records, meta_columns, data_columns)

    # create HDF root structure
    f = h5py.File(destination_file, "w")

    # root attributes
    f.attrs["WAVELENGTH_UNITS"] = "nm"
    f.attrs["LI_UNITS"] = "count"
    f.attrs["LT_UNITS"] = "count"
    f.attrs["ES_UNITS"] = "count"
    #f.attrs["SATPYR_UNITS"] = "count"  # include if needed, but no relation to So-Rad
    f.attrs["RAW_FILE_NAME"] = ""       # there is no upstream file
    f.attrs["PROCESSING_LEVEL"] = "0"
    f.attrs["CAST"] = datetime.datetime.strftime(times[0], "%Y%m%d_%H")
    f.attrs["TIME-STAMP"] = datetime.datetime.strftime(times[0],'%a %b %d %H:%M:%S %Y')

    # metadata group
    gp = f.create_group("sorad")
    gp.attrs['PLATFORM_ID'] = platform_id
    gp.attrs['CalFileName'] = None
    gp.attrs['FrameType'] = 'Not Required'

    # add datasets
    n_samples = len(sample_uuids)
    gp.create_dataset('DATETAG2', data=datetag2s)
    gp.create_dataset('TIMETAG2', data=timetag2s)

    gp.create_dataset('LATITUDE', data=lats)
    gp.attrs['LATITUDE_UNITS'] = 'degrees'
    gp.create_dataset('LONGITUDE', data=lons)
    gp.attrs['LONGITUDE_UNITS'] = 'degrees'
    gp.createdataset('REL_AZ', data=rel_view_azs)
    gp.attrs['REL_AZ_UNITS'] = 'degrees'
    gp.create_dataset('TILT', data=tilt_avgs)
    gp.attrs['TILT_UNITS'] = 'degrees'
    gp.create_dataset('TILT_STD', data=tilt_stds)
    gp.attrs['TILT_STD_UNITS'] = 'degrees'
    gp.create_dataset('GPS_SPEED', data=gps_speeds)
    gp.attrs['GPS_SPEED_UNITS'] = 'm/s'

    f.close()

    # create sensor l0 groups
    #l0_data = {sensor_ids[0]: ed_h,  sensor_ids[1]: ls_h, sensor_ids[2]: lt_h} # l0 data in dict

    #for s in range(len(sensor_ids)):  # loop over sensor types
    #    init_sensor_group(root, l0_data, sensor_ids[s], config_path, cal_path, d_h)

    # write to file
    #hdf_filename =  str(platform_ids[0]) + '_' + f"{datetime_i.strftime('%Y-%m-%d')}"  + '_' + str(hours_of_sampling[h]).zfill(2) + '_L1A.hdf'
    #root.attributes["L1A_FILENAME"] = hdf_filename
    #root.writeHDF5(os.path.join(storage_path, hdf_filename))





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


def init_job_logger(logfilepath):
    """
    Separate logging for jobs from redis queue
    """
    logging.basicConfig(level='INFO', stream=sys.stdout)
    filehandler = logging.handlers.RotatingFileHandler(logfilepath, mode='a',
                                                       maxBytes=1024*2024,
                                                       backupCount=5)
    formatter = logging.Formatter('%(asctime)s| %(levelname)s | %(name)s | %(message)s')
    filehandler.setFormatter(formatter)
    filehandler.setLevel('INFO')
    log = logging.getLogger('worker')
    log.addHandler(filehandler)
    return log

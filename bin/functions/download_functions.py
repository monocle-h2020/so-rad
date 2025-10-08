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
from numpy import unique, nanmean, argmin, argmax, nan
from collections import OrderedDict

log = logging.getLogger('download')
#log.setLevel('DEBUG')


def hdf_from_web_request(storage_path, database_path,
                         start_time, end_time,
                         platform_id, platform_uuid,
                         save_if_empty=False):
    """
    Handle an hdf generation request from the web service (via redis queue).
    conf is the config read by configparser containing 'DATABASE' and 'DOWNLOAD' sections
    """
    logfilename = os.path.join(storage_path, 'csv_log.txt')
    # make a dummy db_dict just to get db cursor
    db_dict = {'file': database_path}

    try:
        log = init_job_logger(logfilename)
        conn, cur = db_func.connect_db(db_dict)
        meta_columns = db_func.column_names(conn, cur, table="sorad_metadata")
        data_columns = db_func.column_names(conn, cur, table="sorad_radiometry")
        conn.close()

        records = identify_records(db_dict, start_time, end_time)
        if len(records) == 0 and not save_if_empty:
            log.info(f"No records in timeframe")
            return

        sets, sensors = parse_records(records, meta_columns, data_columns)
        if len(sets) == 0 and not save_if_empty:
            log.info(f"No complete samples in timeframe")
            return

        destination_file = os.path.join(storage_path,
                                        filename_from_dates(platform_id,
                                                            start_time, end_time,
                                                            format='hdf'))

        save_to_hdf(sets, sensors, destination_file, platform_id, platform_uuid)

        log.info(f"Saved {destination_file}")

    except Exception as err:
        log.exception(err)


def save_to_hdf(sets, sensors, destination_file, platform_id, platform_uuid):
    """
    Save records to a hdf format, e.g. for ingestion by HyperCP
    """
    # create HDF root structure
    f = h5py.File(destination_file, "w")

    # root attributes
    # f.attrs["WAVELENGTH_UNITS"] = "nm"
    f.attrs["LI_UNITS"] = "count"
    f.attrs["LT_UNITS"] = "count"
    f.attrs["ES_UNITS"] = "count"
    #f.attrs["SATPYR_UNITS"] = "count"  # include if needed, but no relation to So-Rad
    f.attrs["RAW_FILE_NAME"] = ""       # there is no upstream file
    f.attrs["PROCESSING_LEVEL"] = "0"
    start_time = [v['gps_time'] for k,v in sets.items()][0]
    f.attrs["CAST"] = datetime.datetime.strftime(start_time, "%Y%m%d_%H")
    f.attrs["TIME-STAMP"] = datetime.datetime.strftime(start_time, "%a %b %d %H:%M:%S %Y")

    # metadata group
    meta = f.create_group("sorad")
    meta.attrs['PLATFORM_ID'] = platform_id
    # meta.attrs['CalFileName'] = "n/a"
    meta.attrs['FrameType'] = 'Not Required'

    # add datasets
    n_samples = len(sets)
    meta.create_dataset('DATETAG', data=[v['datetag2'] for k,v in sets.items()], dtype='f')
    meta.create_dataset('TIMETAG2', data=[v['timetag2'] for k,v in sets.items()], dtype='f')
    meta.create_dataset('LATITUDE', data=[v['latitude'] for k,v in sets.items()], dtype='f')
    meta.attrs['LATITUDE_UNITS'] = 'degrees'
    meta.create_dataset('LONGITUDE', data=[v['longitude'] for k,v in sets.items()], dtype='f')
    meta.attrs['LONGITUDE_UNITS'] = 'degrees'
    meta.create_dataset('REL_AZ', data=[v['rel_view_az'] for k,v in sets.items()], dtype='f')
    meta.attrs['REL_AZ_UNITS'] = 'degrees'
    meta.create_dataset('TILT', data=[v['tilt_avg'] for k,v in sets.items()], dtype='f')
    meta.attrs['TILT_UNITS'] = 'degrees'
    meta.create_dataset('TILT_STD', data=[v['tilt_std'] for k,v in sets.items()], dtype='f')
    meta.attrs['TILT_STD_UNITS'] = 'degrees'
    meta.create_dataset('GPS_SPEED', data=[v['gps_speed'] for k,v in sets.items()], dtype='f')
    meta.attrs['GPS_SPEED_UNITS'] = 'm/s'
    meta.create_dataset('SAMPLE_UUID', data=[v['sample_uuid'] for k,v in sets.items()], dtype=h5py.string_dtype())

    # Sensor groups
    # naming convention: ES (ed), LI (LS), LT (lt)
    LI  = f.create_group(f"SAM_{sensors['ls']}.ini")
    LI.create_dataset('DATETAG', data=[v['datetag2'] for k,v in sets.items()], dtype='f')
    LI.create_dataset('TIMETAG2', data=[v['timetag2'] for k,v in sets.items()], dtype='f')
    LI.attrs['FrameType'] = str(sensors['ls'])
    LI.attrs['RadianceTerm1'] = 'LI'   # Satlantic naming legacy
    LI.attrs['RadianceTerm2'] = 'Ls'   # Gordon/Mobley naming legacy
    LI.create_dataset('L0', data= [v['ls'] for k,v in sets.items()], dtype='i8')
    LI.attrs['L0_units'] = 'count'
    LI.create_dataset('INTTIME', data= [v['ls_inttime'] for k,v in sets.items()], dtype='i8')
    LI.attrs['INTTIME_UNITS'] = 'ms'

    ES  = f.create_group(f"SAM_{sensors['ed']}.ini")
    ES.create_dataset('DATETAG', data=[v['datetag2'] for k,v in sets.items()], dtype='f')
    ES.create_dataset('TIMETAG2', data=[v['timetag2'] for k,v in sets.items()], dtype='f')
    ES.attrs['FrameType'] = str(sensors['ed'])
    ES.attrs['RadianceTerm1'] = 'ES'   # Satlantic naming legacy
    ES.attrs['RadianceTerm2'] = 'Ed'   # Gordon/Mobley naming legacy
    ES.create_dataset('L0', data= [v['ed'] for k,v in sets.items()], dtype='i8')
    ES.attrs['L0_units'] = 'count'
    ES.create_dataset('INTTIME', data= [v['ed_inttime'] for k,v in sets.items()], dtype='i8')
    ES.attrs['INTTIME_UNITS'] = 'ms'

    LT  = f.create_group(f"SAM_{sensors['lt']}.ini")
    LT.create_dataset('DATETAG', data=[v['datetag2'] for k,v in sets.items()], dtype='f')
    LT.create_dataset('TIMETAG2', data=[v['timetag2'] for k,v in sets.items()], dtype='f')
    LT.attrs['FrameType'] = str(sensors['lt'])
    LT.attrs['RadianceTerm1'] = 'LT'   # Satlantic naming legacy
    LT.attrs['RadianceTerm2'] = 'Lt'   # Gordon/Mobley naming legacy
    LT.create_dataset('L0', data= [v['lt'] for k,v in sets.items()], dtype='i8')
    LT.attrs['L0_units'] = 'count'
    LT.create_dataset('INTTIME', data= [v['lt_inttime'] for k,v in sets.items()], dtype='i8')
    LT.attrs['INTTIME_UNITS'] = 'ms'

    # write to file
    f.attrs["L0_FILENAME"] = os.path.basename(destination_file)
    f.close()


def parse_records(records, meta_columns, data_columns):
    """
    Parse the database records to measurement sets.

    records: list of records returned from database
    meta_columns: columns in the sorad_metadata table
    data_columns: column names of the sorad_radiometry table
    """
    # identify and harmonize all data types,
    # from the order in which they appear in database columns
    db_columns = meta_columns + data_columns

    uuid_column = db_columns.index('sample_uuid')
    sample_uuids = [rec[uuid_column] for rec in records]   # list(str)
    # build dictionary of measurement sets to split out sensor records
    # and identify Lt, Ed, Ls signals
    # dict key is the uuid
    # a little extra work is needed to ensure we maintain the sort order (np.unique does not)
    unique_sample_uuids = []
    for sample_uuid in sample_uuids:
        if sample_uuid not in unique_sample_uuids:
            unique_sample_uuids.append(sample_uuid)

    sets = OrderedDict.fromkeys(unique_sample_uuids)

    for uuid in unique_sample_uuids:
        # first identify all records with this uuid
        uuid_set_indices = [j for j, x in enumerate(sample_uuids) if x == uuid]
        # first record in sample - to grab metadata from
        r = records[uuid_set_indices[0]]

        # skip incomplete samples
        if len(uuid_set_indices) != 3:
            log.warning(f"Only {len(uuid_set_indices)} records found with uuid={uuid}, skipping this sample.")
            continue

        # prepare to structure records for this sample
        sensor_id_ix = db_columns.index('sensor_id')
        inttime_ix =   db_columns.index('inttime')
        spectrum_index = db_columns.index('measurement')
        sensor_ids =   []
        inttimes =     []
        spectra =      []
        intensities =  []
        corrupt = False

        for j in uuid_set_indices:
            sensor_ids.append(records[j][sensor_id_ix])
            inttime =         records[j][inttime_ix]
            inttimes.append(inttime)

            spectrum = records[j][spectrum_index] # comma+space-separated string
            spectrum = spectrum.replace("[","").replace("]","").split(", ")
            if 'None' in spectrum:
                # skip incomplete measurements
                corrupt = True
            else:
                spectrum = [int(s) for s in spectrum]
                spectra.append(spectrum)
                # get average uncalibrated intensity normalised by integration time to determine signal strength
                intensities.append(nanmean(spectrum) / float(inttime))

        if corrupt:
            log.warning(f"None values found in at least one uuid={uuid} spectrum, skipping this sample.")
            continue

        # add measurement set with metadata
        record_time = datetime.datetime.strptime(r[db_columns.index('gps_time')], '%Y-%m-%d %H:%M:%S.%f')

        sets[uuid] = {'sample_uuid': uuid,
                      'gps_time':    record_time,
                      'datetag2':    float(datetime.datetime.strftime(record_time, '%Y%j')),
                      'timetag2':    float(datetime.datetime.strftime(record_time, "%H%M%S.%f")[:-3]),
                      'latitude':    r[db_columns.index('gps_lat')],
                      'longitude':   r[db_columns.index('gps_long')],
                      'gps_speed':   r[db_columns.index('gps_speed')],
                      'tilt_avg':    r[db_columns.index('tilt_avg')],
                      'tilt_std':    r[db_columns.index('tilt_std')],
                      'rel_view_az': r[db_columns.index('rel_view_az')],
                      'intensities': intensities,
                      'sensor_ids':  sensor_ids,
                      'inttimes':    inttimes,
                      'spectra':     spectra,
                      'indices':     uuid_set_indices
                     }

        for key in ['tilt_avg', 'tilt_std', 'rel_view_az']:
            if sets[uuid][key] is None:
                sets[uuid][key] = nan

    # determine which sensor is Lt, Ls, Ed (increasing order of intensity)
    sensors_flat =     [x for k,v in sets.items() for x in v['sensor_ids']]
    intensities_flat = [x for k,v in sets.items() for x in v['intensities']]
    unique_sensors = unique(sensors_flat)

    sensor_map = {}
    for s in unique_sensors:
        sensor_map[s] = 0
    for s, i in zip(sensors_flat, intensities_flat):
        sensor_map[s] += i

    sensors = {}
    sensors['lt'] = min(sensor_map, key=sensor_map.get)
    sensors['ed'] = max(sensor_map, key=sensor_map.get)
    sensors['ls'] = list(set(unique_sensors) - set([sensors['lt'], sensors['ed']]))[0]

    # assign radiance signals to sets
    for uuid in unique(sample_uuids):
        ls_ix = sets[uuid]['sensor_ids'].index(sensors['ls'])
        lt_ix = sets[uuid]['sensor_ids'].index(sensors['lt'])
        ed_ix = sets[uuid]['sensor_ids'].index(sensors['ed'])
        sets[uuid]['ls'] = sets[uuid]['spectra'][ls_ix]
        sets[uuid]['lt'] = sets[uuid]['spectra'][lt_ix]
        sets[uuid]['ed'] = sets[uuid]['spectra'][ed_ix]
        sets[uuid]['ls_inttime'] = sets[uuid]['inttimes'][ls_ix]
        sets[uuid]['lt_inttime'] = sets[uuid]['inttimes'][lt_ix]
        sets[uuid]['ed_inttime'] = sets[uuid]['inttimes'][ed_ix]

    return sets, sensors


def csv_from_web_request(storage_path, database_path,
                         start_time, end_time,
                         platform_id, platform_uuid,
                         save_if_empty=False):
    """
    Handle a csv generation request from the web service (via redis queue).
    conf is the config read by configparser containing 'DATABASE' and 'DOWNLOAD' sections
    """
    logfilename = os.path.join(storage_path, 'csv_log.txt')
    # make a dummy db_dict just to get db cursor
    db_dict = {'file': database_path}

    try:
        log = init_job_logger(logfilename)
        conn, cur = db_func.connect_db(db_dict)
        meta_columns = db_func.column_names(conn, cur, table="sorad_metadata")
        data_columns = db_func.column_names(conn, cur, table="sorad_radiometry")
        conn.close()

        records = identify_records(db_dict, start_time, end_time)
        if len(records) == 0 and not save_if_empty:
            log.info(f"No records in timeframe")
            return

        outfile = os.path.join(storage_path,
                               filename_from_dates(platform_id,
                                                   start_time, end_time,
                                                   format='csv'))

        save_to_csv(records, outfile, meta_columns, data_columns, platform_id, platform_uuid)

        log.info(f"Saved {outfile}")

    except Exception as err:
        print(err)


def filename_from_dates(platform_id, start_time, end_time, format='csv'):
    """Generate filename from dates"""
    start_str = datetime.datetime.strftime(start_time, "%Y%m%dT%H%M%S")
    end_str =   datetime.datetime.strftime(end_time,   "%Y%m%dT%H%M%S")
    out_filepath = f"{platform_id}_{start_str}-{end_str}_L0.{format}"
    return out_filepath


def save_to_csv(records, destination_file, meta_columns, data_columns):
    """
    Save records to a csv file
    """
    # adapt header to database columns
    header = [platform_id, platform_uuid] + ",".join(meta_columns+data_columns)

    with open(destination_file, 'w') as op:
        op.write(header + '\n')
        for r in records:
             dataline = [platform_id, platform_uuid] + \
                        ",".join([str(v).replace("[","").replace("]","") for v in r])
             op.write(dataline + '\n')


def identify_records(db_dict, start_time=None, end_time=None):
    """
    Collect information on database records within a given timeframe
    """
    conn, cur = db_func.connect_db(db_dict)
    conn.set_trace_callback(log.info)

    # query records in timeframe
    # SELECT gps_time FROM sorad_metadata WHERE gps_time BETWEEN '2025-09-30 08:00:00' and '2025-09-30 12:00:00'
    sql = """SELECT meta.*, rad.*
              FROM sorad_metadata meta
               LEFT JOIN sorad_radiometry rad
                ON rad.metadata_id = meta.id_
             WHERE meta.n_rad_obs = 3
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
    log.info(f"{len(returned)} complete records returned from database.")

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

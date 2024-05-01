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
import uuid

log = logging.getLogger() #import root logger

def connect_db(db_dict):
    """Connect to the sqlite3 database file

    :param db_dict: database information dictionary
    :type db_dict: dictionary
    :raises Exception: Exception
    :return: conn, cur
    :rtype: sqlite3 object, sqlite3 cursor
    """
    try:
        # connect to db file
        conn = sqlite3.connect(db_dict['file'], timeout=5)
        cur = conn.cursor()
        cur.execute('pragma journal_mode=wal')
    except Exception as err:
        msg = "Error connecting to database file at: {0}".format(db_dict['file'])
        log.error(msg)
        log.exception(err)
        raise Exception(msg)
    return conn, cur

def reset_export_succes_count_for_version(conn, cur, db_dict, version=None):
    """Use with caution. Reset the export success status of records in the local db so that they will be re-uploaded. To prevent duplicates, these records should already be removed from the remote store"""
    attempts_field= db_dict['export_attempts_field']
    success_field = db_dict['export_success_field']
    if version is None:
        log.error("You must supply a specific sorad_version with this function")
    sql = f"""UPDATE sorad_metadata SET {success_field}=0, {attempts_field}=0 WHERE sorad_version = ?"""
    cur.execute(sql, (version,))
    conn.commit()


def database_info(conn, cur):
    """describe the data in the database"""
    # first and last entry
    sql = """SELECT * FROM sorad_metadata WHERE n_rad_obs > 0 ORDER BY pc_time ASC LIMIT 1"""
    cur.execute(sql)
    log.info(f"First data entry: {cur.fetchone()}")
    sql = """SELECT * FROM sorad_metadata WHERE n_rad_obs > 0 ORDER BY pc_time DESC LIMIT 1"""
    cur.execute(sql)
    log.info(f"Last data entry: {cur.fetchone()}")


def column_names(conn, cur, table="sorad_metadata"):
    """retrieve column names from an sqlite3 db table"""
    sql = """SELECT name FROM PRAGMA_TABLE_INFO(?)"""
    cur.execute(sql, (table,))
    columns = cur.fetchall()
    if columns is not None:
        columns = [c[0] for c in columns]
    log.debug(columns)
    return columns


def create_tables(db_dict):
    "Create database and tables, if they don't already exist"
    if not os.path.exists(db_dict['file']):
        if not os.path.isdir(os.path.dirname(db_dict['file'])):
            try:
                os.makedirs(os.path.dirname(db_dict['file']))
            except:
                log.warning("Could not create path to database location: {0}".format(db_dict['file']))
                return

    # the following should create a new database file if it does not already exist
    conn, cur = connect_db(db_dict)
    # test whether table exists
    sql ="""CREATE TABLE IF NOT EXISTS sorad_metadata
            (id_ integer PRIMARY KEY AUTOINCREMENT NOT NULL,
            sample_uuid text,
            pc_time datetime, gps_time datetime, gps_fix integer,
            gps_lat float, gps_long float, gps_speed float,
            platform_bearing float,
            sun_azimuth float, sun_elevation float,
            rel_view_az float,
            motor_temp float, driver_temp float,
            pi_cpu_temp float,
            tilt_avg float, tilt_std float,
            bearing_accuracy float, sorad_version float,
            batt_v float, inside_temp float, inside_rel_hum float, n_rad_obs integer,
            export_success bool, export_attempts integer)"""

    cur.execute(sql)

    sql ="""CREATE TABLE IF NOT EXISTS sorad_radiometry
            (metadata_id integer NOT NULL,
            sensor_id text, inttime integer,
            measurement text,
            FOREIGN KEY(metadata_id) REFERENCES sorad_metadata(id_))"""
    cur.execute(sql)
    conn.commit()
    conn.close()


def commit_db(db_dict, verbose, values, trigger_id, spectra_data, software_version=0):
    """Commit all the required values to the database object, or just gps/meta data if sensor data aren't available"""
    try:
        conn, cur = connect_db(db_dict)

        sample_uuid = str(uuid.uuid1())

        if (trigger_id is None) or (spectra_data is None):
            cur.execute("""INSERT INTO sorad_metadata(sample_uuid, pc_time, gps_time, gps_fix, gps_lat, gps_long, gps_speed,
                           platform_bearing, sun_azimuth, sun_elevation, rel_view_az, pi_cpu_temp,
                           tilt_avg, tilt_std,
                           bearing_accuracy, sorad_version,
                           batt_v, inside_temp, inside_rel_hum, motor_temp, driver_temp,
                           n_rad_obs, export_success, export_attempts)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL, NULL)""", \
                           (sample_uuid, trigger_id, values['dt'], values['fix'], values['lat0'], values['lon0'], values['speed'],
                            values['ship_bearing_mean'], values['solar_az'], values['solar_el'],
                            values['rel_view_az'], values['pi_temp'],
                            values['tilt_avg'], values['tilt_std'], values['accHeading'], software_version,
                            values['batt_voltage'], values['inside_temp'], values['inside_rh'], values['motor_temp'], values['driver_temp']))

            sample_id = cur.lastrowid
            conn.commit()
            conn.close()
            return sample_id

        elif (trigger_id) is not None and (spectra_data is not None):
            cur.execute("""INSERT INTO sorad_metadata(sample_uuid, pc_time, gps_time, gps_fix, gps_lat, gps_long, gps_speed,
                           platform_bearing, sun_azimuth, sun_elevation, rel_view_az, pi_cpu_temp,
                           tilt_avg, tilt_std,
                           bearing_accuracy, sorad_version,
                           batt_v, inside_temp, inside_rel_hum, motor_temp, driver_temp,
                           n_rad_obs, export_success, export_attempts)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL)""", \
                           (sample_uuid, trigger_id, values['dt'], values['fix'], values['lat0'], values['lon0'], values['speed'],
                            values['ship_bearing_mean'], values['solar_az'], values['solar_el'],
                            values['rel_view_az'], values['pi_temp'],
                            values['tilt_avg'], values['tilt_std'],
                            values['accHeading'], software_version,
                            values['batt_voltage'], values['inside_temp'], values['inside_rh'], values['motor_temp'], values['driver_temp'], len(spectra_data)))

            sample_id = cur.lastrowid

            for n in range(len(spectra_data)):
                cur.execute("""INSERT INTO sorad_radiometry(metadata_id,
                                   sensor_id, inttime, measurement) VALUES(?,?,?,?)""",
                                   (sample_id, spectra_data[n][0],
                                    spectra_data[n][1], spectra_data[n][2]))

            conn.commit()
            conn.close()
            return sample_id

        else:
            log.warning("Ended up where we should not have in db_functions. No data stored.")

    except Exception as m:
        log.warning("Exception ignored in db commit: \n{0}".format(m))
        traceback.print_exc(file=sys.stdout)

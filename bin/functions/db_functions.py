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
        conn = sqlite3.connect(db_dict['file'])
        cur = conn.cursor()
    except Exception as err:
        msg = "Error connecting to database: \n {0}".format(err)
        log.critical(msg)
        raise Exception(msg)
    return conn, cur


def create_tables(db_dict):
    "Create database and tables, if they don't already exist"
    if not os.path.exists(db_dict['file']):
        if not os.path.isdir(os.path.dirname(db_dict['file'])):
            try:
                os.makedirs(os.path.dirname(db_dict['file']))
            except:
                log.warning("Could not create path to database location: {0}".format(db_dict['file']))
                raise

    # the following should create a new database file if it does not already exist
    conn, cur = connect_db(db_dict)
    # test whether table exists
    sql ="""CREATE TABLE IF NOT EXISTS sorad_metadata
            (id_ integer PRIMARY KEY AUTOINCREMENT NOT NULL,
            pc_time datetime, gps1_time datetime,
            gps2_time datetime, gps1_fix integer,
            gps2_fix integer, gps1_lat float,
            gps1_long float, gps2_lat float,
            gps2_long float, gps1_speed float,
            gps2_speed float, platform_bearing float,
            sun_azimuth float, sun_elevation float,
            motor_temp float, driver_temp float,
            pi_cpu_temp float, tilt float,
            pitch float, roll float,
            bearing_accuracy float, sorad_version float,
            batt_v float, rel_hum float, n_rad_obs integer,
            sos_inserted bool, sos_insertion_attempts integer)"""
    cur.execute(sql)

    sql ="""CREATE TABLE IF NOT EXISTS sorad_radiometry
            (metadata_id integer NOT NULL,
            sensor_id text, integr_time integer,
            measurement text,
            FOREIGN KEY(metadata_id) REFERENCES sorad_metadata(id_))"""
    cur.execute(sql)
    conn.close()


def commit_db(db_dict, verbose, gps1_dict, gps2_dict, trigger_id, ship_bearing, sun_azi, sun_elev, spectra_data, batt_v=0, pi_cpu_temp=0, motor_temp=0, driver_temp=0, tilt=0, pitch=0, roll=0, software_version=0, rel_hum=0):
    """Commit all the required values to the database object, or just gps/meta data if sensor data isn't available"""
    try:
        # if db is being used
        if db_dict['used']:
            if gps1_dict['poll_rate'] == 0:
                pr1 = 0
            else:
                pr1 = int(1000/gps1_dict['poll_rate'])
            if gps2_dict['used']:
                if gps2_dict['poll_rate'] == 0:
                   pr2 = 0
                else:
                   pr2 = int(1000/gps2_dict['poll_rate'])
            else:
                   pr2 = None

            conn, cur = connect_db(db_dict)
            if (trigger_id is None) or (spectra_data is None):
                cur.execute("""INSERT INTO sorad_metadata(pc_time, gps1_time, gps2_time,
                               gps1_fix, gps2_fix, gps1_lat, gps1_long, gps2_lat,
                               gps2_long, gps1_speed, gps2_speed,
                               platform_bearing, sun_azimuth, sun_elevation, pi_cpu_temp,
                               tilt, pitch, roll, bearing_accuracy, sorad_version, batt_v, rel_hum, motor_temp, driver_temp, n_rad_obs, sos_inserted, sos_insertion_attempts)
                               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL, NULL)""", \
                               (trigger_id, gps1_dict['datetime'], gps2_dict['datetime'], gps1_dict['fix'],
                                gps2_dict['fix'], gps1_dict['latitude'], gps1_dict['longitude'],
                                gps2_dict['latitude'], gps2_dict['longitude'],
                                gps1_dict['speed'], gps2_dict['speed'],
                                str(ship_bearing), str(sun_azi), str(sun_elev),
                                str(pi_cpu_temp), str(tilt), str(pitch), str(roll),
                                gps1_dict['bearing_accuracy'], str(software_version), str(batt_v), str(rel_hum),
                                str(motor_temp), str(driver_temp)))
                sample_id = cur.lastrowid
                conn.commit()
                conn.close()
                return sample_id

                            # """INSERT INTO sorad_metadata(trigger_id, gps1_datetime, gps2_datetime,
                            #    gps1_fix, gps2_fix, gps1_latitude, gps1_longitude, gps2_latitude,
                            #    gps2_longitude, gps1_poll_rate, gps2_poll_rate, gps1_speed, gps2_speed,
                            #    ship_bearing, sun_azimuth, sun_elevation, motor_temp, driver_temp, n_obs)
                            #    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL)"""

            else:
                cur.execute("""INSERT INTO sorad_metadata(pc_time, gps1_time, gps2_time,
                               gps1_fix, gps2_fix, gps1_lat, gps1_long, gps2_lat,
                               gps2_long, gps1_speed, gps2_speed,
                               platform_bearing, sun_azimuth, sun_elevation, pi_cpu_temp,
                               tilt, pitch, roll, bearing_accuracy, sorad_version, batt_v, rel_hum, motor_temp, driver_temp, n_rad_obs, sos_inserted, sos_insertion_attempts)
                               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL)""", \
                               (trigger_id, gps1_dict['datetime'], gps2_dict['datetime'], gps1_dict['fix'],
                                gps2_dict['fix'], gps1_dict['latitude'], gps1_dict['longitude'],
                                gps2_dict['latitude'], gps2_dict['longitude'],
                                gps1_dict['speed'], gps2_dict['speed'],
                                str(ship_bearing), str(sun_azi), str(sun_elev),
                                str(pi_cpu_temp), str(tilt), str(pitch), str(roll),
                                gps1_dict['bearing_accuracy'], str(software_version), str(batt_v), str(rel_hum),
                                str(motor_temp), str(driver_temp), len(spectra_data)))

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
            log.warning("Ended up where we should not have in db_functions")
            log.info("db used:{0} | gps poll rates: {1}, {2}".format(db_dict['used'], gps1_dict['poll_rate'], gps2_dict['poll_rate']))


    except Exception as m:
        log.warning("Exception ignored in db commit: \n{0}".format(m))
        traceback.print_exc(file=sys.stdout)

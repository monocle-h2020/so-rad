#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Check Functions

Functions to see if system components are ready.
Checks are included to check

-GPS accuracy is suffient
-Ship heading is accurate
-Radiometers are ready (sample interval has passed, not currently waiting for data), separate check for Ed sensor sampling interval
-Motor has no active alarm
-Speed is above limit set for sampling
-Sun elevation is above limit set for sampling
-External battery voltage is sufficient
-CPU temperature
-Connectivity to remote data store (for data upload)
-Internet connectivity
"""

import datetime
import requests
import json
from numpy import nan
#import motor_controller_functions as motor_func
import functions.motor_controller_functions as motor_func
import logging

log = logging.getLogger('checks')


def check_remote_data_store(conf):
    "Check for response from remote Parse server. Look for last logged/updated record from this instrument. Return connection status and time of last update"
    export_config_dict = conf['EXPORT']
    parse_app_url = export_config_dict.get('parse_url')  # something like https:1.2.3.4:port/parse/classes/sorad
    parse_app_id = export_config_dict.get('parse_app_id')  # ask the parse server admin for this key and store it in local-config.ini
    platform_id = export_config_dict.get('platform_id')
    parse_clientkey = export_config_dict.get('parse_clientkey')
    headers = {'content-type': 'application/json',
               'X-Parse-Application-Id': parse_app_id,
               'X-Parse-Client-Key': parse_clientkey}

    # some tested examples
    # data = json.dumps({"where":{"platform_id":platform_id}})  # returns all records of this platform
    # data =   json.dumps({"where":{"platform_id":platform_id, "content":"status"}, "order": "-updatedAt", "limit": 1, "keys": "updatedAt"})
    data =   json.dumps({"where":{"platform_id":platform_id}, "order": "-updatedAt", "limit": 1, "keys": "updatedAt"})
    # data = json.dumps({"where":{"platform_id":platform_id}, "limit": 0, "count": 1})
    try:
        response = requests.get(parse_app_url, data=data, headers=headers, timeout=5.0)  # timeout of 5 s prevents main program loop from getting stuck too long
        if (response.status_code >= 200) and (response.status_code) < 300:
            if len(response.json()['results']) > 0:
                # e.g. '2021-06-08T14:59:27.101Z'
                last_update = datetime.datetime.strptime(response.json()['results'][0]['updatedAt'], '%Y-%m-%dT%H:%M:%S.%fZ')
                return True, last_update
            else:
                return True, None
        else:
            return False, None
    except requests.exceptions.ReadTimeout:
        log.warning("Timeout connecting to remote data store")
        return False, None
    except Exception as err:
        log.warning("Unhandled exception connecting to remote data store")
        log.exception(err)
        return False, None


def check_internet():
    try:
        response = requests.get('http://one.one.one.one', verify=True, timeout=0.5)
        if response.status_code == requests.codes.ok:
            return True
        else:
            return False
    except Exception as e:
            return False


def check_gps(gps):
    "Verify that GPSes have recent and accurate data"
    if gps['manager'] is None:
        return False
    lat, lon = gps['manager'].lat, gps['manager'].lon
    gps_fix = gps['manager'].fix
    if None in [lat, lon, gps_fix]:
        return False
    if gps_fix <2 :
        return False
    else:
        return True


def check_heading(gps, bearing_fixed):
    "Verify that gps derived heading is usable"
    if bearing_fixed:
        return True

    if gps['manager'] is None:
        return False

    if gps['protocol'] == "rtk":
        if (gps['manager'].flags_headVehValid == 1) and \
           (gps['manager'].accHeading < gps['heading_accuracy_limit']) and \
           (gps['manager'].heading is not None) and \
           (gps['manager'].heading != 1):
            return True

    elif gps['protocol'] == "pyubx2":
        if (check_gps(gps)) and \
            (gps['manager'].flag_relPosHeadingValid == 1) and \
            (gps['manager'].accHeading < gps['heading_accuracy_limit']) and \
            (gps['manager'].heading is not None):
            return True

    elif gps['protocol'] in ['nmea0183', 'djim350']:
        if gps['manager'].speed is None:
            return False
        elif gps['manager'].speed >= gps['heading_speed_limit']:
            if gps['manager'].heading is None:
                return False
            else:
                return True

    return False


def check_speed(sample_dict, gps):
    "Verify that speed is above set limit"
    return gps['manager'].speed >= float(sample_dict['sampling_speed_limit'])


def check_motor(motor):
    "Verify that Motor has no alarm"
    # read register 128: present alarm code
    response = motor_func.read_command(motor['serial'], 1, 3, 128, 2)
    alarm = int.from_bytes(response[3:7], byteorder='big')
    if alarm > 0:
        return False, alarm
    else:
        return True, alarm


def check_sensors(rad_dict, prev_sample_time, radiometry_manager):
    """Verify that the radiometers fall under the criteria to take a measurement"""
    if radiometry_manager is None:
        return True
    else:
        if radiometry_manager.busy:
            return False
        elif prev_sample_time is None:
            return True
        elif prev_sample_time is nan:
            return True
        elif not radiometry_manager.check_and_restore_sensor_number():
            return False
        elif datetime.datetime.now().timestamp() - prev_sample_time.timestamp() > rad_dict['sampling_interval']:
            return True
        else:
            return False


def check_sun(sample_dict, solar_azimuth, solar_elevation):
    """Check that the sun is in an optimal position"""
    result = True
    if solar_elevation is None:
        return False
    if solar_azimuth is None:
        return False
    if solar_elevation >= sample_dict['solar_elevation_limit']:
        return True
    else:
        return False


def check_ed_sampling(use_rad, rad, ready, values):
    "Check whether conditions for periodic Ed sampling are met"
    try:
        assert values['solar_el'] is not None
        assert use_rad
        assert rad['ed_sampling']
        assert ready['gps']
        assert values['solar_el'] >= rad['ed_sampling_min_solar_elevation_deg']
    except AssertionError:
        return False
    return True


def check_battery(bat_manager, battery):
    """Check whether battery voltage is OK
    returns:
        -1: Unknown
        0: OK
        1: LOW
        2: CRITICAL
    """
    bat_voltage = bat_manager.batt_voltage
    if bat_voltage is None:
        return -1
    elif bat_voltage >= battery['battery_low_th_V']:
        return 0
    elif bat_voltage >= battery['battery_crit_th_V']:
        return 1
    else:
        return 2

def check_pi_cpu_temperature():
    """Get the temperature of the cpu"""
    f = open("/sys/class/thermal/thermal_zone0/temp", "r")
    t = float(f.readline().strip())/1000.0
    return t

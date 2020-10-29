#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Check Functions

Functions to see if system components are ready.
The system components include GPS sensors, radiometers and motor controller.
"""
import datetime
from numpy import nan
#import motor_controller_functions as motor_func
import functions.motor_controller_functions as motor_func


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


def check_heading(gps):
    "Verify that gps derived heading is usable"
    if gps['manager'] is None:
        return False

    if gps['protocol'] == "rtk":
        if (gps['manager'].flags_headVehValid == 1) and (gps['manager'].accHeading < gps['heading_accuracy_limit']) and (gps['manager'].heading is not None):
            return True

    elif gps['protocol'] == 'nmea0183':
        if gps['manager'].speed >= gps['heading_speed_limit']:
            return True

    return False


def check_speed(sample_dict, gps):
    "Verify that speed is above set limit"
    return gps['manager'].speed >= float(sample_dict['sampling_speed_limit'])


def check_motor(motor_manager):
    "Verify that Motor is in optimal position and there is no alarm"
    # read register 128: present alarm code
    response = motor_func.read_command(motor['serial'], 1, 3, 128, 2)
    alarm = int.from_bytes(response[3:7], byteorder='big')
    if alarm > 0:
        return False
    else:
        return motor_manager.within_step_thresh()


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
    return solar_elevation >= sample_dict['solar_elevation_limit']


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
    import os
    import time
    temp = os.popen("vcgencmd measure_temp").readline()
    temp = temp.replace("temp=","")
    temp = temp.replace("'C","")
    return temp

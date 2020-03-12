#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Check Functions

Functions to see if system components are ready.
The system components include GPS sensors, radiometers and motor controller.
"""
import datetime


def check_gps(gps_managers, gps_protocol):
    "Verify that GPSes have recent and accurate data"
    if (len(gps_managers) == 2):
        lat_lons = [gps_managers[0].lat, gps_managers[0].lon, gps_managers[1].lat, gps_managers[1].lon]
        gps_fixes = [gps_manager.fix for gps_manager in gps_managers]
        if min(gps_fixes)<2:
            return False
    # TODO add case for 1 gps under NMEA protocol
    elif (len(gps_managers) == 1 and gps_protocol == "rtk"):
        lat_lons = [gps_managers[0].lat, gps_managers[0].lon]
        gps_fixes = [gps_manager.fix for gps_manager in gps_managers]
        if min(gps_fixes)<1:
            return False
    else:
        return False
    if None in lat_lons:
        return False
    else:
        return True


def check_heading(gps_managers, gps_heading_accuracy_limit, gps_protocol):
    "Verify that gps derived heading is usable"
    # TODO: extend with check for single or dual NMEA GPS
    if (len(gps_managers) == 1) and (gps_protocol == "rtk"):

        if (gps_managers[0].flags_headVehValid == 1) and (gps_managers[0].accHeading < gps_heading_accuracy_limit) and (gps_managers[0].heading is not None):
            return True
    else:
        return False

    return False


def check_speed(sample_dict, gps_managers):
    "Verify that speed is above set limit"
    speeds = [gps_manager.speed for gps_manager in gps_managers]
    return min(speeds) > float(sample_dict['sampling_speed_limit'])


def check_motor(motor_manager):
    "Verify that Motor is in optimal position"
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
        elif not radiometry_manager.check_and_restore_sensor_number():
            return False
        elif datetime.datetime.now() - prev_sample_time > datetime.timedelta(seconds=rad_dict['sampling_interval']):
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

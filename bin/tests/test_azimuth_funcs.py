#!/usr/bin/env python
"""
Azimuth Calculations tests (old and new version)
"""

import os
import sys
import numpy
import math
import logging
import argparse
from dateutil import parser as dtparser
import datetime
import inspect
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(inspect.getfile(inspect.currentframe())))))
import functions.azimuth_functions as az
from functions.config_functions import read_config, update_config
import ephem


def parse_args():
    """parse command line arguments"""
    cfparser = argparse.ArgumentParser()
    cfparser.add_argument('-c', '--config_file', required=False,
                        help="config file providing program settings",
                        default=u"../config.ini")
    cfparser.add_argument('-l', '--local_config_file', required=False,
                        help="system-specific config overrides providing program settings",
                        default=u"../config-local.ini")
    cfparser.add_argument('--ship_heading', required=False, help="Ship heading", type=float, default=0.0)
    cfparser.add_argument('--lat', required=False, help="Latitude", type=float, default=0.0)
    cfparser.add_argument('--lon', required=False, help="Longitude", type=float, default=0.0)
    cfparser.add_argument('--datetime', required=False, help="Date and time in iso format", type=str, default="2023-06-11T12:00:00")
    cfparser.add_argument('--cw_limit', required=False, help="Longitude", type=float, default=None)
    cfparser.add_argument('--ccw_limit', required=False, help="Longitude", type=float, default=None)
    cfparser.add_argument('--motor_home', required=False, help="Longitude", type=float, default=None)

    args = cfparser.parse_args()

    return args


if __name__ == '__main__':
    # start logging to stdout
    log = logging.getLogger()
    handler = logging.StreamHandler(sys.stdout)
    log.setLevel(logging.INFO)
    handler.setLevel(logging.INFO)
    formatter = logging.Formatter('%(asctime)s| %(levelname)s | %(name)s | %(message)s')
    handler.setFormatter(formatter)
    log.addHandler(handler)

    # read command line arguments
    args = parse_args()
    log.info(args)

    # Parse the config file
    if not os.path.exists(args.config_file):
        raise IOError("Config file not found at {0}".format(args.config_file))
    else:
        conf = read_config(args.config_file)

    # update config
    if not os.path.exists(args.local_config_file):
        log.warning("Local config file not found at {0}. Only using defaults".format(args.local_config_file))
    else:
        conf = update_config(conf, args.local_config_file)

    motor_conf = conf['MOTOR']

    motor_dict = {}

    # read / override from configs
    motor_dict['steps_per_degree'] = float(motor_conf['steps_per_degree'])

    if args.cw_limit is None:
        motor_dict['cw_limit'] = int(motor_conf['cw_limit_deg'])
    else:
        motor_dict['cw_limit'] = int(args.cw_limit)

    if args.ccw_limit is None:
        motor_dict['ccw_limit'] = int(motor_conf['ccw_limit_deg'])
    else:
        motor_dict['ccw_limit'] = int(args.ccw_limit)


    if args.motor_home is None:
        motor_dict['home_pos'] = int(motor_conf['home_pos'])
    else:
        motor_dict['home_pos'] = int(args.motor_home)

    dt = dtparser.parse(args.datetime)
    datetime_=dt
    log.info(dt)

    lat = float(args.lat)
    lon = float(args.lon)
    ship_bearing = float(args.ship_heading)

    altitude = 0.
    motor_pos_steps = 0

    solar_az, solar_el = az.solar_az_el(lat, lon, altitude, datetime_)
    log.info(f"solar az: {solar_az}, solar el: {solar_el}")

    solar_az_deg, solar_el_deg, motor_angles = az.calculate_positions(lat, lon, altitude, dt, ship_bearing, motor_dict, motor_pos_steps)
    solar_az_deg2, solar_el_deg2, motor_angles2 = az.calculate_positions2(lat, lon, altitude, dt, ship_bearing, motor_dict, motor_pos_steps)

    log.info(f"solar_az_deg: {solar_az_deg:.2f}")
    log.info(f"solar_el_deg: {solar_el_deg:.2f}\n")
    log.info(f"target_motor_pos_step: {motor_angles['target_motor_pos_step']} | target_motor_pos_step2: {motor_angles2['target_motor_pos_step']}")
    log.info(f"target_motor_pos_rel_az_deg: {motor_angles['target_motor_pos_rel_az_deg']} | target_motor_pos_rel_az_deg2: {motor_angles2['target_motor_pos_rel_az_deg']}")
    for key,val in motor_angles2.items():
        log.info(f"{key}: {val}")

    log.info(motor_dict['ccw_limit'] <= motor_angles2['opt1_view_to_motor_angle'] <= motor_dict['cw_limit'])

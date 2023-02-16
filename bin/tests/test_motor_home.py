#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
A simple test to check motor connectivity.

Created on Wed Aug 21 09:22:46 2019
@author: stsi
"""
import sys
import os
import time
import inspect
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(inspect.getfile(inspect.currentframe())))))
import serial.tools.list_ports as list_ports
from initialisation import motor_init
from main_app import parse_args
import functions.motor_controller_functions as motor_func
import functions.config_functions as cf

if __name__ == '__main__':
    args = parse_args()
    conf = cf.read_config(args.config_file)
    conf = cf.update_config(conf, args.local_config_file)

    ports = list_ports.comports()
    motor = motor_init(conf['MOTOR'], ports)
    print("Motor will turn {0} steps per degree of rotation".format(motor['steps_per_degree']))

    # Get the current motor pos and if not at HOME move it to HOME
    motor_deg_pos = motor_func.get_motor_pos(motor['serial'])  # in degrees
    if motor_deg_pos is None:
        print("No answer from motor. Exit")
        sys.exit(1)
    else:
        print("Motor position: {0}".format(motor_deg_pos))

    # get default motor movement instructions
    motor_commands_dict = motor_func.commands
    motor_commands_dict['speed_command'].value = hex(2000)[2:].zfill(8)  # default 2000
    motor_commands_dict['accel_command'].value = hex(1500)[2:].zfill(8)  # default 1500
    motor_commands_dict['decel_command'].value = hex(1500)[2:].zfill(8)  # default 1500

    if motor_deg_pos != motor['home_pos']:
        t0 = time.perf_counter()
        moving, motor_step_pos = motor_func.motor_moving(motor['serial'], motor['home_pos'], tolerance=300)
        motor_deg_pos = float(motor_step_pos) / motor['steps_per_degree']

        print("Homing motor.. {0} --> {1}".format(motor_deg_pos, motor['home_pos']))
        motor_func.rotate_motor(motor_commands_dict, motor['home_pos'], motor['serial'])

        moving = True
        while moving and (time.perf_counter()-t0<5):
            moving, motor_step_pos = motor_func.motor_moving(motor['serial'], motor['home_pos'], tolerance=300)
            motor_deg_pos = float(motor_step_pos) / motor['steps_per_degree']
            if moving is None:
                moving = True  # assume we are not done
            print("..homing motor.. {}".format(motor_deg_pos))
            time.sleep(1)
        print("..done")
    else:
        print("Motor in home position (not corrected for offset)")
        moving, motor_step_pos = motor_func.motor_moving(motor['serial'], motor['home_pos'], tolerance=300)
        motor_deg_pos = float(motor_step_pos) / motor['steps_per_degree']

    sys.exit(0)

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
from main_app import parse_args, read_config
import functions.motor_controller_functions as motor_func


if __name__ == '__main__':
    args = parse_args()
    conf = read_config(args.config_file)
    ports = list_ports.comports()
    motor = motor_init(conf['MOTOR'], ports)

    # Get the current motor pos and if not at HOME move it to HOME
    motor_pos = motor_func.get_motor_pos(motor['serial'])
    if motor_pos != motor['home_pos']:
        t0 = time.clock()
        print("Homing motor.. {0} --> {1}".format(motor_pos, motor['home_pos']))
        motor_func.return_home(motor['serial'])  # FIXME replace with rotate function to home pos as set in config
        moving = True
        while moving and (time.clock()-t0<5):
            moving, motor_pos = motor_func.motor_moving(motor['serial'], motor['home_pos'], tolerance=300)
            if moving is None:
                moving = True  # assume we are not done
            print("..homing motor..")
            time.sleep(1)
        print("..done")
    else:
        print("Motor in home position")
    time.sleep(0.1)


    # Wiggle +/- 90 degrees
    angles = [9000, 0, -9000, 0, 9000, 0, -9000, 0]
    for target_pos in angles:
        print("Adjust motor angle ({0} --> {1})".format(motor_pos, target_pos))
        # Rotate the motor to the new position
        motor_func.rotate_motor(motor_func.commands, target_pos, motor['serial'])
        moving = True
        t0 = time.clock()  # timeout reference
        while moving and time.clock()-t0 < 5:
            moving, motor_pos = motor_func.motor_moving(motor['serial'], target_pos, tolerance=300)
            if moving is None:
                moving = True
                log.info("..moving motor.. {0} --> {1}".format(motor_pos, target_pos))
            time.sleep(2)

        time.sleep(1)

    sys.exit(0)

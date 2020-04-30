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
        t0 = time.perf_counter()
        print("Homing motor.. {0} --> {1}".format(motor_pos, motor['home_pos']))
        motor_func.return_home(motor['serial'])  # FIXME replace with rotate function to home pos as set in config
        moving = True
        while moving and (time.perf_counter()-t0<5):
            moving, motor_step_pos = motor_func.motor_moving(motor['serial'], motor['home_pos'], tolerance=300)
            motor_deg_pos = float(motor_step_pos) / motor['steps_per_degree']
            if moving is None:
                moving = True  # assume we are not done
            print("..homing motor..")
            time.sleep(1)
        print("..done")
    else:
        print("Motor in home position")
    time.sleep(0.1)


    # Wiggle right/left
    angles = [5, -5, 15, -15, 30, -30, 90, -90, 0]
    
    # get default motor movement instructions and double speed
    motor_commands_dict = motor_func.commands
    motor_commands_dict['speed_command'].value = hex(4000)[2:].zfill(8)  # default 2000
    motor_commands_dict['accel_command'].value = hex(5000)[2:].zfill(8)  # default 1500
    motor_commands_dict['decel_command'].value = hex(5000)[2:].zfill(8)  # default 1500

    for target_deg_pos in angles:
        print("Adjust motor angle ({0} --> {1})".format(motor_pos, target_deg_pos))
        # Rotate the motor to the new position
        target_step_pos = int(target_deg_pos * motor['steps_per_degree'])
        motor_func.rotate_motor(motor_commands_dict, target_step_pos, motor['serial'])
        moving = True
        t0 = time.perf_counter()  # timeout reference
        while moving and time.perf_counter()-t0 < 5:
            moving, motor_step_pos = motor_func.motor_moving(motor['serial'], target_step_pos, tolerance=int(motor['steps_per_degree']*3))
            motor_deg_pos = float(motor_step_pos) / motor['steps_per_degree']
            if moving is None:
                moving = True
                log.info("..moving motor.. {0} --> {1}".format(motor_deg_pos, target_deg_pos))
            time.sleep(0.2)

        time.sleep(0.1)

    sys.exit(0)

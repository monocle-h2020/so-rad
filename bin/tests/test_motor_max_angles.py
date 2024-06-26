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
import logging

if __name__ == '__main__':
    args = parse_args()
    conf = cf.read_config(args.config_file)
    conf = cf.update_config(conf, args.local_config_file)

    # start logging to stdout
    log = logging.getLogger()
    handler = logging.StreamHandler(sys.stdout)
    log.setLevel(logging.INFO)
    handler.setLevel(logging.INFO)
    formatter = logging.Formatter('%(asctime)s| %(levelname)s | %(name)s | %(message)s')
    handler.setFormatter(formatter)
    log.addHandler(handler)

    ports = list_ports.comports()
    motor = motor_init(conf['MOTOR'], ports)
    log.info("Motor will turn {0} steps per degree of rotation".format(motor['steps_per_degree']))

    # Get the current motor pos and if not at HOME move it to HOME
    motor_step_pos = motor_func.get_motor_pos(motor['serial'])
    if motor_step_pos is None:
        log.info("No answer from motor. Exit")
        sys.exit(1)
    else:
        log.info(f"Motor position: {motor_step_pos} steps")


    home_pos_step = int(motor['home_pos'] / motor['steps_per_degree'])

    # get default motor movement instructions
    motor_commands_dict = motor_func.commands
    motor_commands_dict['speed_command'].value = hex(2000)[2:].zfill(8)  # default 2000
    motor_commands_dict['accel_command'].value = hex(1500)[2:].zfill(8)  # default 1500
    motor_commands_dict['decel_command'].value = hex(1500)[2:].zfill(8)  # default 1500

    motor_deg_pos = int(float(motor_step_pos) / motor['steps_per_degree'])

    if motor_deg_pos != motor['home_pos']:
        t0 = time.perf_counter()
        moving, motor_step_pos = motor_func.motor_moving(motor['serial'], home_pos_step, tolerance=300)
        motor_deg_pos = float(motor_step_pos) / motor['steps_per_degree']
        print(f"Homing motor.. {motor_deg_pos} ({motor_step_pos}) --> {motor['home_pos']} ({home_pos_step})")
        motor_func.rotate_motor(motor_commands_dict, home_pos_step, motor['serial'])
        moving = True

        while moving and (time.perf_counter()-t0<5):
            moving, motor_step_pos = motor_func.motor_moving(motor['serial'], home_pos_step, tolerance=300)
            motor_deg_pos = float(motor_step_pos) / motor['steps_per_degree']
            if moving is None:
                moving = True  # assume we are not done
            log.info(f"..homing motor.. {motor_deg_pos} ({motor_step_pos})")
            time.sleep(1)
        log.info("..done")
    else:
        log.info("Motor in home position (not corrected for offset)")
        moving, motor_step_pos = motor_func.motor_moving(motor['serial'], home_pos_step, tolerance=300)
        motor_deg_pos = float(motor_step_pos) / motor['steps_per_degree']
    time.sleep(0.1)


    # Wiggle right/left
    log.info(f"motor home pos offset: {motor['home_pos']} ({home_pos_step})")
    log.info(f"motor counter-clockwise limit: {motor['ccw_limit']} (NOT offset-corrected)")
    log.info(f"motor clockwise limit: {motor['cw_limit']} (NOT offset-corrected)")

    angles = [motor['ccw_limit'], motor['cw_limit']]
    #angles = [0, motor['ccw_limit'], 0, motor['cw_limit']]

    continuous = True
    while continuous == True:
        for target_deg_pos in angles:
            target_step_pos = int(target_deg_pos * motor['steps_per_degree'])
            log.info(f"Adjust motor angle ({motor_deg_pos:3.3f} --> {target_deg_pos}) steps: {motor_step_pos} -> {target_step_pos}")
            # Rotate the motor to the new position
            motor_func.rotate_motor(motor_commands_dict, target_step_pos, motor['serial'])
            moving = True
            t0 = time.perf_counter()  # timeout reference
            while moving and time.perf_counter()-t0 < 5:
                moving, motor_step_pos = motor_func.motor_moving(motor['serial'], target_step_pos, tolerance=int(motor['steps_per_degree']*3))
                if motor_step_pos is None:
                    moving is True
                    time.sleep(0.1)
                    continue

                motor_deg_pos = float(motor_step_pos) / motor['steps_per_degree']
                if moving is None:
                    moving = True
                    log.info("..moving motor.. {0:3.3f} --> {1}".format(motor_deg_pos, target_deg_pos))
                time.sleep(0.1)

            time.sleep(0.5)

    sys.exit(0)

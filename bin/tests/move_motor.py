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

# get default motor movement instructions
motor_commands_dict = motor_func.commands
motor_commands_dict['speed_command'].value = hex(2000)[2:].zfill(8)  # default 2000
motor_commands_dict['accel_command'].value = hex(1500)[2:].zfill(8)  # default 1500
motor_commands_dict['decel_command'].value = hex(1500)[2:].zfill(8)  # default 1500

def run():
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
        log.info("Motor position: {0}".format(motor_step_pos))

    log.info(f"motor home pos offset configured: {motor['home_pos']}")
    log.info(f"motor counter-clockwise limit: {motor['ccw_limit']}")
    log.info(f"motor clockwise limit: {motor['cw_limit']}")
    log.info("Note: offset and limits are only used during So-Rad operation. Use this script to test suitable limits")

    units = 'degrees'
    use_offset = True
    s = 'awaiting input'
    while s != 'x':
        motor_step_pos = motor_func.get_motor_pos(motor['serial'])  # in degrees
        motor_deg_pos = motor_step_pos / motor['steps_per_degree']
        s = input(f"Pos {motor_deg_pos}d ({motor_step_pos} steps). Units: {units}. Enter target position (integer) or switch units ([d]egrees or [s]teps). [x] to quit.\n")
        if s == 'd':
            units = 'degrees'
        elif s == 's':
            units = 'steps'
        elif s == 'x':
            break
        else:
            try:
                target_pos = int(s)
                move(target_pos, units, motor)
            except Exception as e:
                log.exception(e)
                log.info("input must be an integer or either [d]egrees or [s]teps to change units. [x] to quit.")


def move(target_pos, units, motor):
    'Move the motor to a given position.'
    log = logging.getLogger()
    if units == 'degrees':
        target_deg_pos = target_pos
        target_step_pos = int(target_deg_pos * motor['steps_per_degree'])
    else:
        target_step_pos = target_pos
        target_deg_pos = int(target_step_pos / motor['steps_per_degree'])

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


if __name__ == '__main__':
    run()

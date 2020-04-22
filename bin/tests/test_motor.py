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
import initialisation
import main_app


if __name__ == '__main__':
    args = main_app.parse_args()
    conf = main_app.read_config(args.config_file)
    ports = list_ports.comports()
    motor = initialisation.motor_init(conf['MOTOR'], ports)

    # Get the current motor pos and if not at HOME move it to HOME
    motor_pos = motor_func.get_motor_pos(motor['serial'])
    if motor_pos != motor['home_pos']:
        t0 = time.clock()
        log.info("Homing motor.. {0} --> {1}".format(motor_pos, motor['home_pos']))
        motor_func.return_home(motor['serial'])  # FIXME replace with rotate function to home pos as set in config
        moving = True
        while moving and (time.clock()-t0<5):
            moving = motor_func.motor_moving(motor['serial'], motor['home_pos'], tolerance=300)[0]
            if moving is None:
                moving = True  # assume we are not done
            log.info("..homing motor..")
            time.sleep(1)
        log.info("..done")
    else:
        log.info("Motor in home position")
    time.sleep(0.1)

    sys.exit(0)
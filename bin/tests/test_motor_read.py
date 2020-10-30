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
import codecs

test_duration = 3600
print("Run test for {0} seconds. Press CTRL-C to stop".format(test_duration))

if __name__ == '__main__':
    args = parse_args()
    conf = read_config(args.config_file)
    ports = list_ports.comports()
    motor = motor_init(conf['MOTOR'], ports)
    stpd = float(motor['steps_per_degree'])

    t0 = time.time()
    while time.time() - t0 < test_duration:

        # read register 128: present alarm code
        response = motor_func.read_command(motor['serial'], 1, 3, 128, 2)
        # print(response, len(response), type(response))  # bytes class
        #slave_id = int(response[0])
        #function_code = int(response[1])
        length = int(response[2])
        alarm = int.from_bytes(response[3:3+length], byteorder='big')

        # read register 204-205: Detection position
        response = motor_func.read_command(motor['serial'], 1, 3, 204, 2)
        length = int(response[2])
        detpos = float(int.from_bytes(response[3:3+length], byteorder='big'))
        detpos_deg = detpos/stpd % 360.0

        # read register 214-215: Torque monitor (ratio current/max)
        response = motor_func.read_command(motor['serial'], 1, 3, 214, 2)
        length = int(response[2])
        torq = int.from_bytes(response[3:3+length], byteorder='big')
        torq_ratio = float(100.0*torq/4294967295)

        # read register 222-223: Target position
        response = motor_func.read_command(motor['serial'], 1, 3, 222, 2)
        length = int(response[2])
        tarpos = float(int.from_bytes(response[3:3+length], byteorder='big'))
        tarpos_deg = tarpos/stpd  % 360.0

        print("Alarm: {0} \t Position: {1} ({2:2.2f})\t Torque: {3:2.2f}% \t Target {4} ({5:2.2f})".\
               format(alarm, detpos, detpos_deg, torq_ratio, tarpos, tarpos_deg))
    sys.exit(0)

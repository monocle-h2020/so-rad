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

if __name__ == '__main__':
    args = parse_args()
    conf = read_config(args.config_file)
    ports = list_ports.comports()
    motor = motor_init(conf['MOTOR'], ports)

    # read register 128: present alarm code
    num_reg = 2
    response = motor_func.read_command(motor['serial'], 1, 3, 128, num_reg)
    print(response, len(response), type(response))  # bytes class
    slave_id = int(response[0])
    function_code = int(response[1])
    length = int(response[2])
    alarm = int.from_bytes(response[3:3+length], byteorder='big')
    print("Alarm code: {0}".format(alarm))

    # read register 204-205: Detection position
    num_reg = 2
    response = motor_func.read_command(motor['serial'], 1, 3, 204, num_reg)
    print(response, len(response), type(response))  # bytes class
    slave_id = int(response[0])
    function_code = int(response[1])
    length = int(response[2])
    alarm = int.from_bytes(response[3:3+length], byteorder='big')
    print("Detection position: {0}".format(alarm))

    # read register 214-215: Torque monitor (ratio current/max)
    num_reg = 2
    response = motor_func.read_command(motor['serial'], 1, 3, 214, num_reg)
    print(response, len(response), type(response))  # bytes class
    slave_id = int(response[0])
    function_code = int(response[1])
    length = int(response[2])
    alarm = int.from_bytes(response[3:3+length], byteorder='big')
    print("Torque ratio: {0}".format(alarm))

    # read register 222-223: Target position
    num_reg = 2
    response = motor_func.read_command(motor['serial'], 1, 3, 222, num_reg)
    print(response, len(response), type(response))  # bytes class
    slave_id = int(response[0])
    function_code = int(response[1])
    length = int(response[2])
    alarm = int.from_bytes(response[3:3+length], byteorder='big')
    print("Target position: {0}".format(alarm))

    sys.exit(0)

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
import codecs


if __name__ == '__main__':
    args = parse_args()
    conf = cf.read_config(args.config_file)
    conf = cf.update_config(conf, args.local_config_file)

    ports = list_ports.comports()
    motor = motor_init(conf['MOTOR'], ports)

    # read temperature of motor driver and motor
    num_reg = 4
    response = motor_func.read_command(motor['serial'], 1, 3, 248, num_reg)
    print(response, len(response))  # 13 hex values
    #response = codecs.encode(response, 'hex')  # 26 bytes
    #print(response, len(response))
    slave_id = int(response[0])
    function_code = int(response[1])
    length = int(response[2])
    driver_temp = int.from_bytes(response[3:7], byteorder='big')/10.0
    motor_temp = int.from_bytes(response[7:11], byteorder='big')/10.0
    print("Driver: {0}C \t Motor: {1}C".format(driver_temp, motor_temp))

    sys.exit(0)

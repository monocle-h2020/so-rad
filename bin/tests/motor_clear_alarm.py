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
    stpd = float(motor['steps_per_degree'])

    # read register 128: present alarm code
    response = motor_func.read_command(motor['serial'], 1, 3, 128, 2)
    length = int(response[2])
    alarm = int.from_bytes(response[3:3+length], byteorder='big')
    print("Alarm status: {0}".format(alarm))

    if alarm>0:
        print("Attempting to clear alarm.".format(alarm))
        # write register 125 (7D): driver input command, bit 7 = ALM-RST
        response = motor_func.read_command(motor['serial'], 1, 6, 125, 128)
        length = int(response[2])
        #print(response)

        # read register 128: present alarm code
        response = motor_func.read_command(motor['serial'], 1, 3, 128, 2)
        length = int(response[2])
        alarm = int.from_bytes(response[3:3+length], byteorder='big')
        print("Alarm status: {0}".format(alarm))

    print("Return to home position")
    # write register 125 (7D): driver input command, bit 7 = ZHOME
    response = motor_func.read_command(motor['serial'], 1, 6, 125, 16)
    #length = int(response[2])
    #print(response)

    sys.exit(0)

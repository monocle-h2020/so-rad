#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
A simple test to check connectivity to the solar charger and read current battery charge

Created on Wed Aug 21 09:22:46 2019
@author: stsi
"""
import os
import sys
import time
import inspect
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(inspect.getfile(inspect.currentframe())))))
import serial.tools.list_ports as list_ports
import initialisation
from main_app import parse_args
import functions.config_functions as cf

if __name__ == '__main__':
    args = parse_args()
    conf = cf.read_config(args.config_file)
    conf = cf.update_config(conf, args.local_config_file)

    ports = list_ports.comports()
    battery, batman = initialisation.battery_init(conf['BATTERY'], ports)

    if batman is None:
        print("No Battery manager configured")
        sys.exit(0)

    batman.start()
    time.sleep(1)
    try:
        lastupdate = batman.last_update
        for i in range(100):
            lastupdate_new = batman.last_update
            if lastupdate_new > lastupdate:
                print(batman, batman.serial.inWaiting())
                lastupdate = lastupdate_new
            time.sleep(0.1)
    except (KeyboardInterrupt, SystemExit):
        batman.stop()
        sys.exit()

    batman.stop()
    sys.exit(0)


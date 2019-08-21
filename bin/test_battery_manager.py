#!/usr/bin/env python2
# -*- coding: utf-8 -*-
"""
Created on Wed Aug 21 09:22:46 2019

@author: stsi
"""
import serial.tools.list_ports as list_ports
import initialisation
import main_app
import time
import sys

if __name__ == '__main__':
    args = main_app.parse_args()
    conf = main_app.read_config(args.config_file)
    ports = list_ports.comports()
    battery, batman = initialisation.battery_init(conf['BATTERY'], ports)

    batman.start()
    time.sleep(1)
    try:
        lastupdate = batman.last_update
        while True:
            lastupdate_new = batman.last_update
            if lastupdate_new > lastupdate:
                print(batman, batman.serial.inWaiting())
                lastupdate = lastupdate_new
            time.sleep(0.01)
    except (KeyboardInterrupt, SystemExit):
        batman.stop()
        batman.thread.join()
        sys.exit()

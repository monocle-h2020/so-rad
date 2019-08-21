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

if __name__ == '__main__':
    args = main_app.parse_args()
    conf = main_app.read_config(args.config_file)
    ports = list_ports.comports()
    battery, Bat_manager = initialisation.battery_init(conf['BATTERY'])
    batman = Bat_manager(battery)
    
    for i in (50):
        print(batman.lastupdate, batman.lastline)
        time.sleep(1)


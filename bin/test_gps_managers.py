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
from thread_managers.gps_manager import GPSManager

if __name__ == '__main__':
    args = main_app.parse_args()
    conf = main_app.read_config(args.config_file)
    ports = list_ports.comports()
    gps = initialisation.gps_init(conf['GPS'], ports)


    gps_ports = [port for key, port in gps.items() if 'serial' in key]
    # Instantiate GPS monitoring threads
    if len(gps_ports) > 0:
        gps_managers = []
        for port in gps_ports:
            gps_manager = GPSManager()
            gps_manager.add_serial_port(port)
            gps_manager.start()
            gps_managers.append(gps_manager)
    else:
        print("Check GPS sensors and Motor connection settings")
    time.sleep(0.1)

    # Start the GPS checker thread
    #gps_checker_manager = GPSChecker(gps_managers)
    #gps_checker_manager.start()

    while True:
        try:
            for gpsman in gps_managers:
                print(gpsman.serial_ports[0], gpsman.last_update, gpsman.lat, gpsman.lon, gpsman.speed, gpsman.fix)
                time.sleep(0.05)
        except (KeyboardInterrupt, SystemExit):
            for gps_manager in gps_managers:
                print("Stopping GPS manager thread")
                del(gps_manager)
            sys.exit(0)
        except Exception:
            raise

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
A simple test to check GPS connectivity
This test is specifically for a dual-GPS setup (likely obsolete soon!)

Created on Wed Aug 21 09:22:46 2019
@author: stsi
"""
import os
import time
import sys
import inspect
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(inspect.getfile(inspect.currentframe())))))
import serial.tools.list_ports as list_ports
import initialisation
import main_app


def run_test():
    args = main_app.parse_args()
    conf = main_app.read_config(args.config_file)
    ports = list_ports.comports()
    for port, desc, hwid in sorted(ports):
        print("port info: {0} {1} {2}".format(port, desc, hwid))

    print("connecting to gps ports")
    gps = initialisation.gps_init(conf['GPS'], ports)

    print(gps['serial1'])

    print("showing a few blocks of gps data, if available")
    for i in range(10):
        print(i, gps['serial1'].port, gps['serial1'].inWaiting())
        print(i, gps['serial1'].port, gps['serial1'].read(100))

    print("starting gps managers")
    if gps['manager'] is not None:
        gps['manager'].add_serial_port(gps['serial1'])
        gps['manager'].start()
    else:
        print("No GPS manager identified")
    time.sleep(0.1)

    print("Showing gps manager data, CTRL-C to stop")
    print("Ports used: {0}".format(gps['manager'].serial_ports))
    while True:
        try:
            print(gps['manager'].last_update, gps['manager'].lat, gps['manager'].lon, gps['manager'].speed, gps['manager'].fix)
            time.sleep(0.5)
        except (KeyboardInterrupt, SystemExit):
            print("Stopping GPS manager thread")
            gps['manager'].stop()
            sys.exit(0)
        except Exception:
            raise

if __name__ == '__main__':
    run_test()

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
from thread_managers.gps_manager import GPSManager
import RPi.GPIO as GPIO


def gpio_off():
    GPIO.setmode(GPIO.BOARD)
    pins = [11,12,13,15]  # FIXME: get from configs
    GPIO.setup(pins, GPIO.OUT)
    GPIO.output(pins, GPIO.LOW)
    GPIO.cleanup()
    print("done")

def run_test():
    args = main_app.parse_args()
    conf = main_app.read_config(args.config_file)
    ports = list_ports.comports()
    print("connecting to gps ports")
    gps = initialisation.gps_init(conf['GPS'], ports)

    print(gps['serial1'], gps['serial2'])

    print("showing a few blocks of gps data, if available")
    for gserial in [gps['serial1'], gps['serial2']]:
        for i in range(10):
            print(i, gserial.port, gserial.inWaiting())
            print(i, gserial.port, gserial.read(100))

    print("starting gps managers")
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
    # gps_checker_manager = GPSChecker(gps_managers)
    # gps_checker_manager.start()

    print("showing gps manager data, CTRL-C to stop")
    while True:
        try:
            for gpsman in gps_managers:
                print(gpsman.serial_ports[0].port, gpsman.last_update, gpsman.lat, gpsman.lon, gpsman.speed, gpsman.fix)
                time.sleep(0.2)
        except (KeyboardInterrupt, SystemExit):
            for gps_manager in gps_managers:
                print("Stopping GPS manager thread")
                del(gps_manager)
            gpio_off()
            sys.exit(0)
        except Exception:
            raise


if __name__ == '__main__':
    run_test()
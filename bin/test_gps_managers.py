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
    # gps_checker_manager = GPSChecker(gps_managers)
    # gps_checker_manager.start()

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

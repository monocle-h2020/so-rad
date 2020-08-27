#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
A simple test to check TriOS Radiometer connectivity.
@author: stsi
"""
import sys
import os
import time
import inspect
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(inspect.getfile(inspect.currentframe())))))
import serial.tools.list_ports as list_ports
from initialisation import rad_init
from main_app import parse_args, read_config
from PyTrios import PyTrios as ps
import RPi.GPIO as GPIO
import datetime
try:
    import gnuplotlib as gp
    import numpy as np
    plot=True
except:
    print("To show plots install gnuplot (sudo apt-get install gnuplot) and gnuplotlib (pip3 install gnuplotlib)")
    plot=False


def run_test(conf):
    """Test connectivity to TriOS RAMSES radiometer sensors using the routines used in the main application"""
    ports = list_ports.comports()
    for p in ports:
        print(p)
    config = conf['RADIOMETERS']
    rad, Rad_manager = rad_init(config, ports)
    ports = [config['port1'], config['port2'], config['port3']]
    print("Starting radiometry manager")

    radiometry_manager = Rad_manager(rad)
    time.sleep(1)

    print(radiometry_manager)

    trig_id, specs, sids, itimes = radiometry_manager.sample_all(datetime.datetime.now())
    for i, s in zip(sids,specs):
        print("Received spectrum from {0}: {1}".format(i, s))
        if plot:
            gp.plot(np.array(s), terminal = 'dumb 80,40', unset = 'grid')

    time.sleep(0.5)

    print("Stopping radiometry manager threads")
    if radiometry_manager is not None:
        radiometry_manager.stop()

    # switch off gpio
    if rad['use_gpio_control']:
        print("Switch off GPIO control")
        pin = int(rad['gpio1'])
        GPIO.setmode(GPIO.BCM)
        GPIO.output(pin, GPIO.LOW)
        GPIO.cleanup()

    sys.exit(0)

if __name__ == '__main__':
    args = parse_args()
    conf = read_config(args.config_file)
    run_test(conf)



#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
A simple test to check connectivity of a single TriOS G2 Radiometer.
@author: stsi
"""

import sys
import os
import time
import inspect
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(inspect.getfile(inspect.currentframe())))))
import serial.tools.list_ports as list_ports
#from initialisation import rad_init
#from main_app import parse_args
#import functions.config_functions as cf
#from PyTrios import PyTrios as ps
#import RPi.GPIO as GPIO
import datetime
from thread_managers.radiometer_manager import TriosG2Ramses
import pytrios_g2.pytrios2 as pt2

try:
    import gnuplotlib as gp
    import numpy as np
    plot=True
except:
    print("To show plots install gnuplot (sudo apt-get install gnuplot) and gnuplotlib (pip3 install gnuplotlib)")
    plot=False


def make_sample_schedule(interval=15, repeat=10):
    tnext = datetime.datetime.now()
    tnext = tnext - datetime.timedelta(microseconds=tnext.microsecond)
    schedule = []

    for r in range(repeat):
        tnext = tnext + datetime.timedelta(seconds=interval)
        schedule.append(tnext)

    return schedule


def run_test(port):
    """Test connectivity to TriOS RAMSES radiometer sensors on a specific port"""

    instrument = TriosG2Ramses(port)
    instrument.start()
    instrument.connect()
    instrument.get_identity = True

    while instrument.busy:
        time.sleep(0.1)

    print(f"Sensor identity: {instrument.sam}")

    result = None

    for trigger_time in make_sample_schedule(15, 10):
        print(f"Next sample at {trigger_time}")
        instrument.sample_one(trigger_time)
        time.sleep(0.5)  # wait for thread to pick up command

        while instrument.busy:
            time.sleep(0.1)

        s = instrument.result
        print(f"Result: {s.spectrum_type['value']}, inclination: {s.pre_inclination['value']} - {s.post_inclination['value']} | {s.temp_inclination_sensor['value']} | {s.spectrum}")

    print("Stopping radiometry manager threads")

    instrument.stop()


if __name__ == '__main__':
    #args = parse_args()
    #conf = cf.read_config(args.config_file)
    #conf = cf.update_config(conf, args.local_config_file)
    log = pt2.init_logger()

    ports = list_ports.comports()
    for p in ports:
        print(p)
    port = '/dev/ttyUSB0'  # edit this
    run_test(port)


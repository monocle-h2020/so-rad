#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
A simple test to check TriOS Radiometer connectivity.
@author: stsi
"""
import sys
import os
import inspect
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(inspect.getfile(inspect.currentframe())))))
from initialisation import rad_init
from main_app import parse_args
import functions.config_functions as cf
import RPi.GPIO as GPIO
import datetime
import logging
import serial.tools.list_ports as list_ports
import time

def single_test(radiometry_manager, ed=True):
    log.info("Trigger measurement on all sensors")
    trig_id, specs, sids, itimes, preincs, postincs, inctemps  = radiometry_manager.sample_all(datetime.datetime.now())

    for sid, itime, preinc, postinc, inctemp, spec in zip(sids, itimes, preincs, postincs, inctemps, specs):
        log.info(f"Received spectrum from {sid}: {trig_id} {itime} {preinc}-{postinc}")
        log.debug(f"Spectrum:{spec}")

    if ed:
        log.info("Trigger an Ed measurement")
        trig_id, spec, sid, itime, inc_pre, inc_post, temp = radiometry_manager.sample_ed(datetime.datetime.now())
        log.info(f"Received Ed spectrum from {sid}: {trig_id} {itime} {temp} {inc_pre}-{inc_post}")
        log.debug(f"Spectrum:{spec}")


def run_test(conf, repeat=False):
    """Test connectivity to TriOS RAMSES radiometer sensors using the routines used in the main application"""

    ports = list_ports.comports()
    for port, desc, hwid in sorted(ports):
        log.info("port info: {0} {1} {2}".format(port, desc, hwid))
    config = conf['RADIOMETERS']
    rad, Rad_manager = rad_init(config, ports)

    # switch off gpio
    if rad['use_gpio_control']:
        log.info("Switch sensors on via GPIO control")
        rad['gpio_interface'].off(rad['gpio1'])
        log.info(f"gpio status: {rad['gpio_interface'].GPIO.input(rad['gpio1'])}")

        time.sleep(1) # Wait to allow sensors to boot

    log.info("Starting radiometry manager")
    radiometry_manager = Rad_manager(rad)

    if repeat:
       log.info("Starting repeat measurements, press CTRL-C to stop")
       while repeat:
           try:
               single_test(radiometry_manager, ed=False)
           except KeyboardInterrupt:
               repeat = False
    else:
        single_test(radiometry_manager, ed=False)

    log.info("Stopping radiometry manager threads")
    if radiometry_manager is not None:
        radiometry_manager.stop()

    # switch off gpio
    if rad['use_gpio_control']:
        log.info("Switch off sensors via GPIO control")
        rad['gpio_interface'].off(rad['gpio1'])
        rad['gpio_interface'].stop()


if __name__ == '__main__':
    args = parse_args()
    conf = cf.read_config(args.config_file)
    conf = cf.update_config(conf, args.local_config_file)

    log = logging.getLogger()
    handler = logging.StreamHandler(sys.stdout)
    log.setLevel(logging.INFO)
    handler.setLevel(logging.INFO)
    formatter = logging.Formatter('%(asctime)s| %(levelname)s | %(name)s | %(message)s')
    handler.setFormatter(formatter)
    log.addHandler(handler)

    run_test(conf, repeat=False)  # select repeat = True to repeat test until interrupted

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Shortcut to switch off all GPIO pins

"""
import sys
import os
import time
import inspect
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(inspect.getfile(inspect.currentframe())))))
from main_app import parse_args
from functions.config_functions import read_config, update_config
from thread_managers import gpio_manager
import logging


def run(conf):
    rad_config = conf['RADIOMETERS']
    rad = {}
    if rad_config.getboolean('use_gpio_control'):
        pin = rad_config.getint('gpio1')
        rad['gpio_protocol'] = rad_config.get('gpio_protocol')
        assert rad['gpio_protocol'] in  ['rpi', 'gpiozero']
        if rad['gpio_protocol'] == 'rpi':
            rad['gpio_interface'] = gpio_manager.RpiManager()       # select manager and initialise
        elif rad['gpio_protocol'] == 'gpiozero':
            rad['gpio_interface'] = gpio_manager.GpiozeroManager()  # select manager and initialise

        log.info(rad['gpio_interface'])
        log.info(f"Switching pin {pin}")

        rad['gpio_interface'].on(pin)
        rad['gpio_interface'].on(22)   # 2nd ssr - testing only

        log.info("Done")
    else:
        print("GPIO control is not set")


if __name__ == '__main__':
    args = parse_args()
    conf = read_config(args.config_file)
    # start logging to stdout
    log = logging.getLogger()
    handler = logging.StreamHandler(sys.stdout)
    log.setLevel(logging.INFO)
    handler.setLevel(logging.INFO)

    formatter = logging.Formatter('%(asctime)s| %(levelname)s | %(name)s | %(message)s')
    handler.setFormatter(formatter)
    log.addHandler(handler)

    # update config with local overrides
    conf = update_config(conf, args.local_config_file)

    run(conf)

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
    ind_config = conf['INDICATORS']
    if not ind_config.getboolean('use_rgb_led'):
        print("RGB indicators are not enabled in config")
        return

    ind = gpio_manager.RpiManager()       # select manager and initialise

    log.info("Cycle colours")
    colours = ['blue', 'green', 'red', 'cyan', 'white', 'yellow', 'pink']
    for c in colours:
        pins = get_colour(ind_config, c)
        log.info(pins)
        ind.on(pins)
        time.sleep(1)
        ind.off(pins)

    log.info("Done")

def get_colour(ind_config, colour):
    """
    Return pin states to get a given colour
    """
    R = ind_config.getint('red_pin')
    G = ind_config.getint('green_pin')
    B = ind_config.getint('blue_pin')

    if colour == 'red':
        return [R]
    elif colour == 'green':
        return [G]
    elif colour == 'blue':
        return [B]
    elif colour == 'white':
        return [R,G,B]
    elif colour == 'cyan':
        return [G,B]
    elif colour == 'yellow':
        return [R,G]
    elif colour == 'pink':
        return [R,B]
    else:
        log.error(f"colour {colour} not implemented")
        return []


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

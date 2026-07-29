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
from functions.rgb_indicator import set_colour
from thread_managers import gpio_manager
import logging


def run(conf):
    log.info("Cycle colours")
    colours = ['blue', 'green', 'red', 'cyan', 'white', 'yellow', 'pink']
    for c in colours:
        set_colour(conf, c)

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

    log.info("Done")


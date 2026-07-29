#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Control RGB LED
"""
import sys
import os
import time
import inspect
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(inspect.getfile(inspect.currentframe())))))
from thread_managers import gpio_manager
import logging

def set_colour(conf, colour):
    ind_config = conf['INDICATORS']
    if not ind_config.getboolean('use_rgb_led'):
        print("RGB indicators are not enabled in config")
        return

    ind = gpio_manager.RpiManager()       # select manager and initialise

    pins_on, pins_off = get_colour(ind_config, colour)
    ind.off(pins_off)
    ind.on(pins_on)


def get_colour(ind_config, colour):
    """
    Return pin states to get a given colour
    """
    R = ind_config.getint('red_pin')
    G = ind_config.getint('green_pin')
    B = ind_config.getint('blue_pin')

    if colour == 'red':
        return [R], [G,B]
    elif colour == 'green':
        return [G], [R,B]
    elif colour == 'blue':
        return [B], [R,G]
    elif colour == 'white':
        return [R,G,B], []
    elif colour == 'cyan':
        return [G,B], [R]
    elif colour == 'yellow':
        return [R,G], [B]
    elif colour == 'pink':
        return [R,B], [G]
    else:
        log.error(f"colour {colour} not implemented")
        return []

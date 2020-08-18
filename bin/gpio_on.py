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
from main_app import parse_args, read_config
import RPi.GPIO as GPIO


def run():
    args = parse_args()
    conf = read_config(args.config_file)

    # collect info on which GPIO pins are being used
    gpios = []
    if conf['GPS']['use_gpio_control']:
        gpios.append(conf['GPS']['gpio2'])

    if conf['RADIOMETERS']['use_gpio_control']:
        gpios.append(conf['RADIOMETERS']['gpio1'])
        gpios.append(conf['RADIOMETERS']['gpio2'])
        gpios.append(conf['RADIOMETERS']['gpio3'])

    gpios = [int(g) for g in gpios]

    GPIO.setmode(GPIO.BOARD)
    GPIO.setup(gpios, GPIO.OUT)
    GPIO.output(gpios, GPIO.HIGH)
    GPIO.cleanup()
    print("done")

if __name__ == '__main__':
    run()

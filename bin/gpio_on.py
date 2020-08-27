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

    if conf['RADIOMETERS'].getboolean('use_gpio_control'):
        pin = conf['RADIOMETERS'].getint('gpio1')
    else:
       print("GPIO control is not set")

    GPIO.setmode(GPIO.BCM)
    GPIO.setup(pin, GPIO.OUT)
    GPIO.output(pin, GPIO.HIGH)
    time.sleep(1)
    GPIO.cleanup()
    print("done")

if __name__ == '__main__':
    run()

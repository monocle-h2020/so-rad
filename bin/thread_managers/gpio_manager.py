#!/usr/bin/python3
# -*- coding: utf-8 -*-
"""
Handle GPIO control

Plymouth Marine Laboratory
License: under development

"""
import os
import sys
import time
import datetime
import logging

log = logging.getLogger('gpio')

class RpiManager(object):
    """
    Use the Rpi.GPIO library to control GPIO output pins
    """
    def __init__(self):
        try:
            import RPi.GPIO as GPIO
            self.GPIO = GPIO
            self.GPIO.setwarnings(False)
            self.GPIO.setmode(self.GPIO.BCM)
        except Exception as msg:
            log.warning("Could not import GPIO library. Functionality may be limited to system tests.\n{0}".format(msg))
    def on(self, pin):
        self.GPIO.setup(pin, self.GPIO.OUT)
        self.GPIO.output(pin, self.GPIO.HIGH)

    def off(self, pin):
        self.GPIO.setup(pin, self.GPIO.OUT)
        self.GPIO.output(pin, self.GPIO.LOW)


class GpiozeroManager(object):
    """
    Use the gpiozero library to control GPIO output pins
    NOTE: This cannot be used with the current version of gpiozero, because it does not keep the state of the pin beyond the scope of the function it was called in.
    """
    def __init__(self):
        try:
            import gpiozero as GPIO
            self.GPIO = GPIO
        except Exception as msg:
            log.warning("Could not import GPIO library. Functionality may be limited to system tests.\n{0}".format(msg))

    def on(self, pin):
        log.info(self.GPIO)
        log.info(self.GPIO.LED)
        log.info(pin)
        s = self.GPIO.LED(pin)
        s.on()

    def off(self, pin):
        s = self.GPIO.LED(pin)
        s.off()

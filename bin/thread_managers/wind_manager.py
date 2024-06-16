#!/usr/bin/python3
# -*- coding: utf-8 -*-
"""
This script provides classes to interface with anemometers.

Implement a class for each type of instrument  manager. 

Classes provided:
 - Gill windsonic (proprietary Gill prototcol)

Plymouth Marine Laboratory
"""
import time
import datetime
import logging
import serial
import threading
import codecs
import sys

log = logging.getLogger('wind')


class Gill(object):
    """
    Victron MPPT manager class, normally initalised from initialisation.py
    Connects to a Victron MPPT controller using a TTL (5V) level serial cable and using the victron.connect protocol.
    """
    def __init__(self, wind):
        """
        : wind is a dictionary obtained from the initialisation script
        """
        self.config = wind
        self.lastlineread = b''
        self.wind_speed     = None
        self.wind_direction = None
        self.status         = None
        self.units          = None
        self.serial         = wind['serial']
        self.stop_monitor   = False
        self.started        = False
        self.lock           = threading.Lock()

        self.last_update = datetime.datetime.now()
        self.sleep_interval = 0.1

    def __repr__(self):
        return f"Wind {self.latest_reading_time.isoformat()}: speed: {self.wind_speed} direction: {self.wind_direction}"

    def start(self):
        """
        Starts serial reading threads.
        """
        if not self.started:
            self.started = True
            self.thread = threading.Thread(target=self.run)
            self.thread.start()
            log.info(f"Started Wind manager on {self.serial.port}")
        else:
            log.warn("Could not start Wind manager")

    def stop(self):
        """
        Tells the serial threads to stop.
        """
        log.info("Stopping Wind manager")
        self.stop_monitor = True
        time.sleep(2*self.sleep_interval)
        log.info(self.thread)
        self.thread.join(2*self.sleep_interval)
        log.info(f"Wind manager running = {self.thread.is_alive()}")
        self.started = False
        self.serial.close()

    def parse_line(self, line):
        """
        Updates the fields held by this class, a lock is used to prevent corruption.
        :line: a line read on the serial port
        """
        self.lock.acquire(True)
        self.lastlineread = line
        #linesplit = line.split(',')
        #if len(linesplit) > 1 and linesplit[0] in self.vedirect.keys():
        #    val = linesplit[1]
        #    try:
        #        val = float(val)
        #    except: pass
        #    if val is not None:
        #        self.vedirect[linesplit[0]] = val
        self.last_update = datetime.datetime.now()
        self.lock.release()

    def run(self):
        """
        Main loop of the thread.
        """
        log.info(f"Starting Wind monitor thread on port {self.serial.port}")
        while not self.stop_monitor:
            if self.serial.inWaiting() > 1000:
                # if too much data in buffer, throw it away
                log.warning(f">1kb in Wind buffer on port {self.serial.port}. Clearing input buffer.")
                self.serial.reset_input_buffer()
                time.sleep(0.001)
                continue
            if self.serial.inWaiting() > 10:
                # if there is data, read it, parse it and continue immediately
                # this will always return a line with a line ending unless the serial port timeout is reached
                serial_string = self.serial.readline()
                try:
                    self.parse_line(serial_string.strip())
                except UnicodeDecodeError:
                    pass
                    time.sleep(0.001)  # Sleep for a millisecond so that it doesn't max CPU
                except Exception:
                    log.warning("Error parsing Wind string: {serial_string}")
                    time.sleep(0.001)  # Sleep for a millisecond so that it doesn't max CPU
            else:
                time.sleep(self.sleep_interval)
                continue

    def __del__(self):
        self.stop()

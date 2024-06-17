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
import re

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
        self.data = []
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

        The Gill protocol is:

        <STX>Q, 229, 002.74 ,M, 00, <ETX> 16 <CR> <LF>
         ^   ^    ^       ^  ^   ^     ^   ^
         |   |    |       |  |   |     |   |
         |<STX> = Start of string character (ASCII value 2)
             |    |       |  |   |     |   |
             |WindSonic node address = Unit identifier
                  |       |  |   |     |   |
                  |Wind direction = Wind Direction
                          |  |   |     |   |
                          |Wind speed = Wind Speed
                             |   |     |   |
                             |Units = Units of measure (knots, m/s etc.)
                                 |    |    |
                                 |Status = Anemometer status code (see Appendix J for further details)
                                      |    |
                                      |<ETX> = End of string character (ASCII value 3)
                                           |
                                           |Checksum = This is the EXCLUSIVE – OR of the bytes between (and not including) the <STX> and <ETX>characters.
           <CR> = ASCII character
           <LF> = ASCII character
        """

        self.lock.acquire(True)
        self.lastlineread = line

        STX = b'\x02'
        ETC = b'\x03'

        status_codes = {'00': 'OK',
                        '01': 'Axis 1 failed',
                        '02': 'Axis 2 failed',
                        '04': 'Axis 1 and 2 failed',
                        '08': 'NVM error',
                        '09': 'ROM error',
                        'A':  'NMEA data Acceptable',
                        'V':  'NMEA data Void',
                       }

        units = {'M': 'm/s',
                 'N': 'kn',
                 'P': 'mph',
                 'K': 'kph',
                 'F': 'ft/min'
                 }


        if not ((STX in line) and (ETC in line)):
            log.warning("Incomplete line received")
            self.data = []
            self.lock.release()
            return


        try:
            checksum_sent = line[-2:].decode('ascii')
            data_to_check = line[1:-3]
            checksum_received = 0
            for b in data_to_check:
                checksum_received ^= b
            checksum_valid = checksum_sent == hex(checksum_received)[-2:].upper()

            self.data = line[1:-3].decode('ascii').split(',')
            self.status         = status_codes[self.data[4]]
            if (not checksum_valid) or (self.status != 'OK'):
                 log.warning(f"Wind data error: {self.status}, checksum: {checksum_valid}")
                 self.data = []
                 self.wind_speed     = None
                 self.wind_direction = None
                 self.units          = None
                 self.last_update    = datetime.datetime.now()
                 self.lock.release()
                 return

            else:
                self.wind_speed     = float(self.data[2])
                self.wind_direction = int(self.data[1])
                self.units          = units[self.data[3]]
                self.last_update = datetime.datetime.now()
                self.lock.release()

        except Exception as err:
            log.warning(err)
            self.data = []
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
                try:
                    serial_string = self.serial.readline()
                    self.parse_line(serial_string.strip())
                except UnicodeDecodeError:
                    pass
                    time.sleep(0.001)  # Sleep for a millisecond so that it doesn't max CPU
                except Exception as err:
                    log.debug(f"Error parsing Wind string: {serial_string}")
                    log.info(err)
                    time.sleep(0.001)  # Sleep for a millisecond so that it doesn't max CPU
            else:
                time.sleep(self.sleep_interval)
                continue

    def __del__(self):
        self.stop()

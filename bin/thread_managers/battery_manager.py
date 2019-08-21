#!/usr/bin/python3
# -*- coding: utf-8 -*-
"""
This script provides classes to interface with a battery manager, likely a solar charge controller.

Implement a class for each type of battery manager. A Victron MPPT class is provided.

Plymouth Marine Laboratory
License: under development

"""
import time
import datetime
import logging
import serial
import threading
import codecs

log = logging.getLogger()   # report to root logger


class VictronManager(object):
    """
    Victron MPPT manager class, normally initalised from initialisation.py
    Connects to a Victron MPPT controller using a TTL (5V) level serial cable and using the victron.connect protocol.
    """
    def __init__(self, battery, ports):
        """
        : battery config is the [BATTERY] part of the config file
        : ports is a list of available COM ports
        """
        self.config = battery
        self.serial = self.connect(ports)
        self.voltage = None
        self.stop_monitor = False
        self.started = False        
        self.lock = threading.Lock()
        self.threads = []
        self.connect()
        self.lastlineread = ''
        self.last_update = datetime.datetime.now()
        self.sleep_interval = 0.1

    def start(self):
        """
        Starts serial reading threads.
        """
        if not self.started:
            self.started = True
            for port in self.serial:
                new_thread = threading.Thread(target=self.run, args=(port,))
                self.threads.append(new_thread)
            for thread in self.threads:
                thread.start()
            log.info("Started Battery manager")
        else:
            log.warn("Could not start Battery manager")

    def stop(self):
        """
        Tells the serial threads to stop.
        """
        log.info("Stopping Battery manager")
        self.stop_monitor = True
        time.sleep(2*self.sleep_interval)
        log.info(self.threads)
        for thread in self.threads:
            thread.join(1)
            log.info("Battery manager running = {0}".format(thread.is_alive()))
        self.threads = []
        self.started = False

    def parse_line(self, line):
        """
        Updates the fields held by this class, a lock is used to prevent corruption.
        :line: a line read on the serial port
        """
        self.lock.acquire(True)
        self.lastlineread = line
        self.last_update = datetime.datetime.now()
        self.gps_lock.release()

    def run(self, port):
        """
        Main loop of the thread.
        This will run and read from a serial port and pass it back
        """
        log.info("Starting battery monitor thread on port {0}".format(port))
        while not self.stop_monitor:
            if port.inWaiting() > 1000:
                # if too much data in buffer, throw it away
                log.warning(">1kb in gps buffer on port {0}. Clearing input buffer.".format(port))
                port.reset_input_buffer()
                time.sleep(0.001)
                continue
            if port.inWaiting() > 0:
                # if there is data, read it, parse it and continue immediately
                serial_string = port.readline()
                try:
                    self.last_result_dict = self.parse_line(codecs.decode(serial_string, 'utf-8'))
                except UnicodeDecodeError:
                    log.warning("UnicodeDecodeError on Battery string: {0}".format(serial_string))
                    time.sleep(0.001)  # Sleep for a millisecond so that it doesn't max CPU
            else:
                time.sleep(self.sleep_interval)
                # sleep for a standard period
                continue

    def connect(self, ports):
        # If port autodetect is selected, look for what port has the identifying string also provided
        if self.config['port_autodetect']:
            for port, desc, hwid in sorted(ports):
                if (desc == self.config['port_autodetect_string']):
                    self.config['port'] = port
                    log.info("Battery using port: {0}".format(port))
        else:
            assert self.config['port_default'] is not None
            self.config['port'] = self.config['port_default']
    
        # Create a serial object for the motor port
        self.serial = serial.Serial(port=self.config['port'],
                                          baudrate=self.config['baud'],
                                          timeout=1.0, bytesize=8, parity='E',
                                          stopbits=1, xonxoff=0)
        self.serial.reset_input_buffer()
        self.serial.reset_output_buffer()
        
    def __del__(self):
        self.serial.close()
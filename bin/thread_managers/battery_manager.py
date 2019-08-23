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
import sys

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
        self.connect(ports)
        self.vedirect = {'V': None, 'VPV': None, 'PPV': None, 'I': None, 'IL': None, 'ERR': None}
        self.batt_voltage = None
        self.batt_current = None
        self.load_current = None
        self.solar_voltage = None
        self.solar_power = None
        self.solar_current = None
        self.error = None
        self.stop_monitor = False
        self.started = False
        self.lock = threading.Lock()
        self.connect(ports)
        self.lastlineread = ''
        self.last_update = datetime.datetime.now()
        self.sleep_interval = 0.1

    def __repr__(self):
        return "Solar {0}V {1:1.3f}A {2}W | Battery {3}V {4}A | Load {5}A {6:1.2f}W".format(self.solar_voltage, self.solar_current, self.solar_power,
                                                                                     self.batt_voltage, self.batt_current,
                                                                                     self.load_current, self.load_current*12.0)

    def start(self):
        """
        Starts serial reading threads.
        """
        if not self.started:
            self.started = True
            self.thread = threading.Thread(target=self.run, args=(self.serial,))
            self.thread.start()
            log.info("Started Battery manager on {0}".format(self.serial.port))
            #thread.join(0.01)
        else:
            log.warn("Could not start Battery manager")

    def stop(self):
        """
        Tells the serial threads to stop.
        """
        log.info("Stopping Battery manager")
        self.stop_monitor = True
        time.sleep(2*self.sleep_interval)
        log.info(self.thread)
        self.thread.join(1)
        log.info("Battery manager running = {0}".format(self.thread.is_alive()))
        self.thread = []
        self.started = False

    def parse_line(self, line):
        """
        Updates the fields held by this class, a lock is used to prevent corruption.
        :line: a line read on the serial port
        """
        self.lock.acquire(True)
        self.lastlineread = line

        linesplit = line.split('\t')
        if len(linesplit) > 1 and linesplit[0] in self.vedirect.keys():
            val = linesplit[1]
            try:
                val = float(val)
            except: pass
            self.vedirect[linesplit[0]] = val
            self.last_update = datetime.datetime.now()
            self.update_vals()

        self.lock.release()

    def update_vals(self):
        try:
            self.batt_voltage =   self.vedirect['V']/1000.0 # Volt
            self.batt_current =   self.vedirect['I']/1000.0 # Ampere
            self.load_current =   self.vedirect['IL']/1000.0
            self.solar_voltage =  self.vedirect['VPV']/1000.0
            self.solar_power =    self.vedirect['PPV']  # W
            self.error =          self.vedirect['ERR']
            self.solar_current =  self.solar_power/self.solar_voltage # A
        except TypeError: pass

    def run(self, serial_port):
        """
        Main loop of the thread.
        This will run and read from a serial port and pass it back
        """
        log.info("Starting battery monitor thread on port {0}".format(serial_port.port))
        while not self.stop_monitor:
            if serial_port.inWaiting() > 1000:
                # if too much data in buffer, throw it away
                log.warning(">1kb in gps buffer on port {0}. Clearing input buffer.".format(serial_port.port))
                serial_port.reset_input_buffer()
                time.sleep(0.001)
                continue
            if serial_port.inWaiting() > 0:
                # if there is data, read it, parse it and continue immediately
                serial_string = serial_port.readline()
                try:
                    self.parse_line(codecs.decode(serial_string.strip(), 'utf-8'))
                except UnicodeDecodeError:
                    pass
                    #log.warning("UnicodeDecodeError on Battery string: {0}".format(serial_string))
                    time.sleep(0.001)  # Sleep for a millisecond so that it doesn't max CPU
                except Exception:
                    log.warning("Error parsing Battery string: {0}".format(serial_string))
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
                                          timeout=1.0, bytesize=8, parity='N',
                                          stopbits=1, xonxoff=0)
        self.serial.reset_input_buffer()
        self.serial.reset_output_buffer()

    def __del__(self):
        self.serial.close()

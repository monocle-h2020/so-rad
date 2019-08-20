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
        # import any dependencies to connect to this interface
        # configure connection
        self.serial = self.connect(ports)
        self.voltage = None
        
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




class SerialReader(threading.Thread):
    """
    Thread to read from a serial port
    """
    def __init__(self, serial_port, parent):
        threading.Thread.__init__(self)
        self.serial_port = serial_port
        self.parent = parent

        self.observers = []

        self.current_gps_dict = None
        log.info("Starting GPS reader thread")

    def run(self):
        """
        Main loop of the thread.

        This will run and read from a GPS string and when it is valid and decoded it'll be passed via the
        observer design pattern.
        """
        while not self.parent.stop_gps:
            old_gps_time = self.parent.datetime

            if self.serial_port.inWaiting() > 1000:
                # if too much data in buffer, throw it away
                log.warning(">1kb in gps buffer on port {0}. Clearing input buffer.".format(self.serial_port.port))
                self.serial_port.reset_input_buffer()
                time.sleep(0.001)
                continue

            if self.serial_port.inWaiting() > 0:
                # if there is data, read it
                gps_string = self.serial_port.readline()
            else:
                time.sleep(0.01)
                # sleep a bit longer than usual
                continue

            log.debug("NMEA: {0}".format(gps_string.strip()))

            try:
                self.current_gps_dict = GPSParser.parse(codecs.decode(gps_string, 'utf-8'))
                self.notify_observers()
            except UnicodeDecodeError:
                log.warning("UnicodeDecodeError on GPS string: {0}".format(gps_string))

            #if datetime.datetime.now().timestamp() - self.parent.last_update.timestamp() > 1.0:
            #    if old_gps_time.timestamp() == self.current_gps_dict['date']:
            #        self.parent.reset_comports()

            time.sleep(0.001)  # Sleep for a millisecond so that it doesn't max CPU

    def register_observer(self, observer):
        """
        Register an observer of the GPS thread.

        Observers must implement a method called "update"
        :param observer: An observer object.
        :type observer: object
        """
        if not observer in self.observers:
            self.observers.append(observer)

    def notify_observers(self):
        """
        This pushes the GPS dict to all observers.
        """
        if self.current_gps_dict is not None:
            for observer in self.observers:
                observer.update(self.current_gps_dict)


class GPSManager(object):
    """
    Main GPS class which oversees the management and reading of GPS ports.
    """
    def __init__(self):
        self.serial_ports = []
        self.stop_gps = False
        self.watchdog = None
        self.started = False
        self.threads = []
        self.heading = None
        self.lat = None
        self.lon = None
        self.alt = None
        self.speed = None
        self.fix = 0
        self.datetime = None
        self.old = False
        self.proper_compass = False
        self.satellite_number = 0
        self.update_rate = 0
        self.gps_lock = threading.Lock()
        self.gps_observers = []
        self.watchdog_callbacks = []
        self.last_update = datetime.datetime.now()

    def __del__(self):
        #self.disable_watchdog()
        self.stop()

    def add_serial_port(self, serial_port):
        """
        Add a serial port to the list of ports to read from.

        The serial port must be an instance of serial.Serial, and the open() method must have been called.

        :param serial_port: Serial object
        :type serial_port: serial.Serial
        """
        if not serial_port in self.serial_ports:
            self.serial_ports.append(serial_port)

    def remove_serial_port(self, serial_port):
        """
        Remove serial port from the list of ports to remove.

        This wont kill any threads reading serial ports. Run stop then remove then start again.
        :param serial_port: Serial object
        :type serial_port: serial.Serial
        """
        if serial_port in self.serial_ports:
            self.serial_ports.remove(serial_port)

    def start(self):
        """
        Starts serial reading threads.
        """
        if not self.started:
            self.started = True
            for port in self.serial_ports:
                new_thread = GPSSerialReader(port, self)
                new_thread.register_observer(self)
                self.threads.append(new_thread)

            for thread in self.threads:
                thread.start()

            log.info("Started GPS managers")
        else:
            log.warn("GPS manager already started")

    def stop(self):
        """
        Tells the serial threads to stop.
        """
        log.info("Stopping GPS manager")
        self.stop_gps = True
        time.sleep(2)
        log.info(self.threads)
        for thread in self.threads:
            thread.join(1)
            log.info("gps alive? = {0}".format(thread.is_alive()))
        self.threads = []
        self.started = False

    def update(self, gps_dict):
        """
        Updates the gps info held by this class, a lock is used to prevent corruption.

        :param gps_dict: GPS Dictionary passed.
        :type gps_dict: dict
        """
        self.gps_lock.acquire(True)
        if gps_dict is not None:
            self.old = False
            if self.watchdog is not None:
                self.watchdog.reset()
            if gps_dict['type'] == 'hchdg':
                self.proper_compass = True
                self.heading = gps_dict['heading']
            elif gps_dict['type'] == 'gpvtg':
                # Use track made good? for heading if no proper compass
                self.speed = gps_dict['speed']

                if not self.proper_compass:
                    self.heading = gps_dict['heading']
            elif gps_dict['type'] == 'gpgga':
                self.lat = gps_dict['lat']
                self.lon = gps_dict['lon']
                self.alt = gps_dict['alt']
                #self.fix = gps_dict['fix']
                self.satellite_number = gps_dict['satellite_number']
                #if self.datetime is not None: # Doesnt get day only time so update if we have proper day (GPRMC should set that eventually)
                #    self.datetime.replace(hour=gps_dict['hour'], minute=gps_dict['min'], second=gps_dict['seconds'])
                #else:
                #    self.datetime = gps_dict['date']
            elif gps_dict['type'] == 'gprmc':
                self.lat = gps_dict['lat']
                self.lon = gps_dict['lon']
                self.datetime = gps_dict['date']
                self.speed = gps_dict['speed']
                # Use track made good? for heading if no proper compass
                if not self.proper_compass:
                    self.heading = gps_dict['heading']
            elif gps_dict['type'] == 'pmtk500':
                self.update_rate = gps_dict['update_rate']
            elif gps_dict['type'] == 'gpgsa':
                self.fix = gps_dict['fix']
            #self.notify_observers()
            self.last_update = datetime.datetime.now()
        self.gps_lock.release()

    def flushbuffer(self):
        self.serial_ports[0].reset_input_buffer()

    def reset_comports(self):
        """Reset the comports so that the data is fresh and the GPS sensors are in sync"""
        self.gps_lock.acquire(True)
        self.serial_ports[0].close()
        time.sleep(0.05)
        self.serial_ports[0].open()
        log.info("Reset GPS ports: {0}".format(datetime.datetime.now()))
        self.gps_lock.release()



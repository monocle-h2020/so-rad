#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
GPS Manager

Creates GPS Manager objects which create serial reader threads for the GPS
sensor it is instantiated with. This takes in the serial data and parses it
using a library of GPS NMEA strings to extract the information.
"""
import datetime
import logging
import re
import threading
import time
import codecs

log = logging.getLogger()   # report to root logger

# GPGGA $GPGGA,113657.32,5021.9979,N,00407.9635,W,1,9,0.9,8.1,M,53.6,M,,*43
#  GPS Fix Data:
#    Time, Lat, Lon, Fix Quality, No. Satellites, HDOP, Altitude, HELIP, DGPS, DGPS Ref
# GPGSV
#  Satellites in view:
#    Total messages, Message number, No. Satellites, SV PRN, Elevation, Azimuth, SNR, 4-7, 4-7, 4-7
# GPRMC $GPRMC,113745.12,A,5021.9979,N,00407.9635,W,0.0,358.1,310315,2.2,W,A*3B
#  Minimum GPS Data:
#    Time, Valid, Lat, Lon, Speed, Course, Date, Variation
# GPVTG $GPVTG,232.7,T,234.9,M,1.3,N,2.4,K,A*2F
#  Track Made Good and Ground Speed
#    True Track, Magnetic Track, Ground Speed (knots), Ground Speed (Km/h)
# HCHDG $HCHDG,359.6,0.0,E,2.2,W*59
#  Compass Data:
#    Heading, deviation, variation
# PAMTR
# PAMTT
# WIMDA
# WIMWD
# WIMWV

class GPSParser(object):
    """
    Class which contains a parse and checksum method.

    Will parse GPGGA and HCHDG NMEA sentence.
    """
    @staticmethod
    def checksum(sentence):
        """
        Check the GPS NMEA sentence and validate its checksum.

        :param sentence: NMEA sentence
        :type sentence: str

        :return: True if the sentences checksum is valid, False otherwise
        :rtype: bool
        """
        sentence = sentence.strip()
        match = re.search(r'^\$(.*\*.*)$', sentence)
        if match:
            try:
                sentence = match.group(1)
                nmeadata, cksum = re.split(r'\*', sentence)
                calc_cksum = 0
                for char in nmeadata:
                    calc_cksum ^= ord(char)
                return '0x'+cksum.lower() == hex(calc_cksum)
            except ValueError:
                return False
        return False

    @staticmethod
    def parse(gps_string):
        """
        Parse a GPS NMEA sentence, returns the output of the function which matches the string.

        :param gps_string: NMEA Sentence.
        :type gps_string: str

        :return: Function output or None
        """
        if GPSParser.checksum(gps_string):
            try:
                if gps_string.startswith('$GPGGA') or gps_string.startswith('$GNGGA') or gps_string.startswith('$GLGGA'):
                    return GPSParser.parse_gpgga(gps_string)
                elif gps_string.startswith('$GPRMC') or gps_string.startswith('$GNRMC') or gps_string.startswith('$GLRMC'):
                    return GPSParser.parse_gprmc(gps_string)
                elif gps_string.startswith('$GPVTG'):
                    return GPSParser.parse_gpvtg(gps_string)
                elif gps_string.startswith('$HCHDG'):
                    return GPSParser.parse_hchdg(gps_string)
                elif gps_string.startswith('$PMTK500'):
                    return GPSParser.parse_pmtk500(gps_string)
                elif gps_string.startswith('$GPGSA') or gps_string.startswith('$GNGSA') or gps_string.startswith('$GLGSA'):
                    return GPSParser.parse_gpgsa(gps_string)
            except:
                log.debug("Could not parse gps string:\n\t{0}".format(gps_string))
                pass

        return None

    @staticmethod
    def parse_gpgga(gpgga_string):
        """
        Parses a GPGGA sentence.

        :param gpgga_string: NMEA Sentence
        :type gpgga_string: str

        :return: Returns a dictionary with data extracted from the string.
        :rtype: dict
        """
        gps_parts = gpgga_string.split(',')[1:-1]
        # $GPGGA,113657.32,5021.9979,N,00407.9635,W,1,9,0.9,8.1,M,53.6,M,,*43
        #        0         1         2 3          4 5 6 7   8   9 10   11
        #                                                                ^12
        lat = int(gps_parts[1][0:2]) + (float(gps_parts[1][2:])/60.0)
        lon = int(gps_parts[3][0:3]) + (float(gps_parts[3][3:])/60.0)
        if gps_parts[2] == 'S':
            lat *= -1
        if gps_parts[4] == 'W':
            lon *= -1

        hour = int(gps_parts[0][0:2])
        mins = int(gps_parts[0][2:4])
        seconds = int(round(float(gps_parts[0][4:]), ndigits=0))

        #date = datetime.datetime.now()
        #date.replace(hour=hour, minute=mins, second=seconds)

        result = {
            'type': 'gpgga',
            'hour': hour,
            'min': mins,
            'seconds': seconds,
            #'date': date,
            'lat': lat,
            'lon': lon,
            'alt': float(gps_parts[8]),
            #'fix': int(gps_parts[5]),
            'satellite_number': int(gps_parts[6])
        }

        return result

    @staticmethod
    def parse_gprmc(gprmc_string):
        """
        Parses a GPRMC sentence.

        :param gprmc_string: NMEA Sentnce
        :type gprmc_string: str

        :return: Returns a dictionary with data extracted from the string.
        :rtype: dict
        """
        gps_parts = gprmc_string.split(',')[1:-1]
        # $GPRMC,113623.12,A,5021.9979,N,00407.9635,W,0.0,358.1,310315,2.2,W,A*3A
        #        0         1 2         3 4          5 6   7     8      9   10
        hour = int(gps_parts[0][0:2])
        mins = int(gps_parts[0][2:4])
        seconds = int(gps_parts[0][4:6])
        microseconds = int(gps_parts[0][7:])*1000

        day = int(gps_parts[8][0:2])
        month = int(gps_parts[8][2:4])
        year = int(gps_parts[8][4:6])
        if year < 1900:
            year += 2000

        date = datetime.datetime(year, month, day, hour, mins, seconds, microseconds)

        lat = int(gps_parts[2][0:2]) + (float(gps_parts[2][2:])/60.0)
        lon = int(gps_parts[4][0:3]) + (float(gps_parts[4][3:])/60.0)
        if gps_parts[3] == 'S':
            lat *= -1
        if gps_parts[5] == 'W':
            lon *= -1

        result = {
            'type': 'gprmc',
            'hour': hour,
            'min': mins,
            'seconds': seconds,
            'microseconds': microseconds,
            'day': day,
            'month': month,
            'year': year,
            'date': date,
            'lat': lat,
            'lon': lon,
            'speed': float(gps_parts[6]),
            'heading': float(gps_parts[7])
        }

        return result

    @staticmethod
    def parse_gpvtg(gpvtg_string):
        """
        Parses a GPVTG sentance.

        :param gpvtg_string: NMEA Sentance
        :type gpvtg_string: str

        :return: Returns a dictionary with data extracted from the string.
        :rtype: dict
        """
        gps_parts = gpvtg_string.split(',')[1:-1]
        # $GPVTG,232.7,T,234.9,M,1.3,N,2.4,K,A*2F
        #        0     1 2     3 4   5 6   7

        result = {
            'type': 'gpvtg',
            'heading': float(gps_parts[0]),
            'speed': float(gps_parts[4])
        }

        return result

    @staticmethod
    def parse_hchdg(hchdg_string):
        """
        Parses a HCHDG sentance.

        :param hchdg_string: NMEA Sentance
        :type hchdg_string: str

        :return: Returns a dictionary with data extracted from the string.
        :rtype: dict
        """
        gps_parts = hchdg_string.split(',')[1:-1]
        # $HCHDG,359.6,0.0,E,2.2,W*59
        #        0     1   2 3

        result = {
            'type': 'hchdg',
            'heading': float(gps_parts[0])
        }

        return result

    @staticmethod
    def parse_pmtk500(pmtk500_string):
        """
        Parses a PMTK500 sentence.

        :param pmtk500_string: NMEA Sentance
        :type pmtk500_string: str

        :return: Returns a dictionary with data extracted from the string.
        :rtype: dict
        """
        gps_parts = pmtk500_string.split(',')[1:-1]
        # $PMTK500,1000,0,0,0.0,0.0*1A
        #          0    1 2 3   4

        result = {
            'type': 'pmtk500',
            'update_rate': int(gps_parts[0])
        }

        return result

    @staticmethod
    def parse_gpgsa(gpgsa_string):
        """
        Parses a GPGSA sentance.

        :param gpgsa_string: NMEA Sentance
        :type gpgsa_string: str

        :return: Returns a dictionary with data extracted from the string.
        :rtype: dict
        """
        gps_parts = gpgsa_string.split(',')[1:-1]
        # $GPGSA,A,3,04,05,,09,12,,,24,,,,,2.5,1.3,2.1*39
        #        0 1 2                      3   4   5  6

        result = {
            'type': 'gpgsa',
            'fix': float(gps_parts[1])
        }

        return result


class GPSSerialReader(threading.Thread):
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
            thread.join(0.1)
            # log.info("gps alive? = {0}".format(thread.is_alive()))
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

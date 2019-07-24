#!/usr/bin/env python
"""
HyperSAS Application.
"""
from __future__ import print_function, division
#import sys
#sys.path.append('/users/rsg/oco/Repos/MONOCLE/Rrs_azimuth/hypersas/app/hypersas_lib')
from . import gpslib_new as gpslib#, sasmanager
import configparser
import serial
import datetime
import ephem
import logging
import logging.handlers
import math
import os
import threading
import time
#-----
#from pysolar.solar import get_azimuth
#-----

logger = logging.getLogger("hypersas")
saslogger = logging.getLogger("saslogger")

def get_log_level(log_level_string):
    """
    Get the logging level from a given string

    :param log_level_string: String of the logging level
    :type log_level_string: str

    :return: Logging level
    :rtype: int
    """
    logs = {
        'CRITICAL': logging.CRITICAL,
        'CRIT': logging.CRITICAL,
        'ERROR': logging.ERROR,
        'WARNING': logging.WARNING,
        'WARN': logging.WARNING,
        'INFO': logging.INFO,
        'DEBUG': logging.DEBUG,
    }

    try:
        return logs[log_level_string.upper()]
    except KeyError:
        return logging.INFO


class AzimuthCalculation(threading.Thread):
    """
    Thread to calculate the azimuth and SAS angle
    """

    def __init__(self, parent):
        threading.Thread.__init__(self)
        self.stop = False
        self._parent = parent
        self._observer = ephem.Observer()
        self._sun = ephem.Sun()

#----------------------------------------------------
        #self.calc_lock = threading.Lock()
        #self.old = False
        self.solar_degrees = 0.0
        self.sas_pos = 0.0
        self.observers = []
#----------------------------------------------------

        logger.info("Starting SAS calculation thread")

    @staticmethod
    def _weird_mod(value):
        """
        This performs modulo operation with 180 and preserves the sign

        :param value: Value to modulo
        :type value: float

        :return: Value MOD 180
        :rtype: float
        """
        if value > 180.0:
            value -= 360
        elif value < -180.0:
            value += 360

        if value > 180.0 or value < -180.0:
            AzimuthCalculation._weird_mod(value)

        return value

    def run(self):
        #last_access_time = datetime.datetime.now()
        while not self.stop:
            
#----------------------------------------------------
            self.solar_degrees, self.sas_pos = self.run_calculations()
            self._parent.update(self.solar_degrees, self.sas_pos)
            #time.sleep(0.1)
#----------------------------------------------------

            if self.stop: # this prevents waiting a whole second ;)
                break

            last_access_time = datetime.datetime.now()
            while True:
                diff = datetime.datetime.now() - last_access_time
                #remaining_secs = 1 - (diff.microseconds * 0.000001) # 1 Second minus microseconds
                if diff.seconds >= 1:
                    break
                time.sleep(0.1)
                


    def run_calculations(self):
        """
        Do the calculations for the solar and SAS azimuth
        """

        #saslogger.info("lat: %s"%str(self._parent.latitude))
        #saslogger.info("lon: %s"%str(self._parent.longitude))
        # Update the observer to our current location
        self._observer.lat = str(self._parent.latitude)
        self._observer.lon = str(self._parent.longitude)
        self._observer.elevation = self._parent.altitude
        self._observer.date = self._parent.datetime

        self._sun.compute(self._observer)

        # Set the properties
        solar_degrees = math.degrees(self._sun.az)

        #saslogger.info("Sun azumith: {0}".format(solar_degrees))
        
        # Time to do the maths
        #
        # First find the two acceptable angles from the sun (+- 135 degrees)
        # Modulo the angles with 360 to prevent values > 360 or < 0
        # Find the angles +- 135 degrees from the sun relative to the heading (or 0 for the SAS)
        # Essentially modulo the values with 180 but do so in a way that we get a range -180 -> 180

        heading = self._parent.heading #!!!!!!! CHANGE !!!!!!!
        # speed = self._parent.speed
        # #speed_limit = self._parent.speed_limit

        # New positions (range 0 - 359)
        new_pos_1 = (solar_degrees + 135) % 360
        new_pos_2 = (solar_degrees - 135) % 360

        # New positions (range -180 - 180) relative to SAS
        sas_pos_1 = new_pos_1 - heading
        sas_pos_2 = new_pos_2 - heading
        sas_pos_1 = self._weird_mod(sas_pos_1)
        sas_pos_2 = self._weird_mod(sas_pos_2)

        # Check that the positions are -180 -> 180
        assert 180.0 >= sas_pos_1 >= -180.0
        assert 180.0 >= sas_pos_2 >= -180.0

        # Returns the number closest to 0
        final_sas_pos = min([sas_pos_1, sas_pos_2], key=abs)

#----------------------------------------------------
        return solar_degrees, final_sas_pos
#----------------------------------------------------


class AzimuthWindow():
    """
    Main application class
    """

    @staticmethod
    def padd_round(value, pad, ndigits):
        """
        0 Pad and round the decimal places of a number

        :param value: Number
        :type value: float

        :param pad: Digits to padd pre decimal place
        :type pad: int

        :param ndigits: Digits to round to
        :type ndigits: int

        :return: Formatted string
        :rtype: str
        """
        format_string = "{0:0>" + str(pad) + "}.{1}"
        return format_string.format(int(round(value, ndigits)), str(value - int(value))[2:2+ndigits])

    def __init__(self, gps_port_list):
        self.config_file = configparser.ConfigParser()
        self.config_file.read("config.ini")

        self.log_folder = "azimuth_calc/log_folder"

        self._console_log_level = get_log_level(self.config_file.get("LOGGING", "console_log_level"))
        self._gps_log_level = get_log_level(self.config_file.get("LOGGING", "gps_log_level"))
        self._sas_log_level = get_log_level(self.config_file.get("LOGGING", "sas_log_level"))
        self._app_log_level = get_log_level(self.config_file.get("LOGGING", "app_log_level"))
        
        #self.sasmanager = sasmanager.HyperSAS(sas_ip, sas_user, sas_password, neg_limit=left_lim, pos_limit=right_lim, start=0)

        self._solar_az_calc_thread = None

        self.gps_managers = []
        for gps_port in gps_port_list:
            gps_baud = self.config_file.getint("GPS", "baud1")
            gps_serial_port = serial.Serial(port=gps_port, baudrate=gps_baud, timeout=None, bytesize=serial.EIGHTBITS, parity=serial.PARITY_NONE, stopbits=serial.STOPBITS_ONE, xonxoff=False)

            gps_manager = gpslib.GPSManager()
            gps_manager.add_serial_port(gps_serial_port)
            gps_manager.register_observer(self)
            self.gps_managers.append(gps_manager)

        # This is check for the update method to stop the update changing gps light :(
        self._gps_stopped = False

#-----------------------------------------------

        self._lat = 0.0
        self._lon = 0.0
        self._alt = 0.0
        self._date = datetime.datetime.now()
        self._heading = 0.0
        self._sol_az = 0.0
        self._sas_az = 0.0
        self._speed = 0.0
        self._proper_compass = False
        self._sat_num = 0

#-----------------------------------------------
        self.old = False
        #self.solar_deg = 0.0
        self.calc_observers = []
        self.calc_lock = threading.Lock()
#-----------------------------------------------


        ## Logging setup
        logger.setLevel(self._app_log_level)
        saslogger.setLevel(self._sas_log_level)
        gpslib.logger.setLevel(self._gps_log_level)

        # Setup formatters
        console_formatter = logging.Formatter('[%(asctime)s %(name)s %(levelname)s] %(message)s')


        # Setup handlers
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(console_formatter)
        console_handler.setLevel(self._console_log_level)


        logger.addHandler(console_handler)
        saslogger.addHandler(console_handler)
        gpslib.logger.addHandler(console_handler)


    # def __del__(self):
    #     self.gps_manager.disable_watchdog()
    #     self.gps_manager2.disable_watchdog()
    #     self.gps_manager.stop()
    #     self.gps_serial_port.close()
    #     self._solar_az_calc_thread.stop = True

    @property
    def altitude(self):
        """
        Get altitude

        :return: GPS Altitude
        :rtype: float
        """
        return self._alt

    @altitude.setter
    def altitude(self, alt):
        """
        Set the altitude

        :param alt: Altitude
        :type alt: float
        """
        if isinstance(alt, float):
            self._alt = alt

    @property
    def latitude(self):
        """
        Get latitude

        :return: GPS Latitude
        :rtype: float
        """
        return self._lat

    @latitude.setter
    def latitude(self, lat):
        """
        Set the latitude

        :param lat: Latitude
        :type lat: float
        """
        if isinstance(lat, float):
            self._lat = lat

    @property
    def longitude(self):
        """
        Get longitude

        :return: GPS Longitude
        :rtype: float
        """
        return self._lon

    @longitude.setter
    def longitude(self, lon):
        """
        Set the longitude

        :param lon: Longitude
        :type lon: float
        """
        if isinstance(lon, float):
            self._lon = lon

    @property
    def heading(self):
        """
        Get compass heading

        :return: Compass heading
        :rtype: float
        """
        return self._heading

    @heading.setter
    def heading(self, hdg):
        """
        Set the heading

        :param hdg: Heading
        :type hdg: float
        """
        if isinstance(hdg, float):
            self._heading = hdg

    @property
    def speed(self):
        """
        Get the current speed

        :return: Speed in knots
        :rtype: float
        """
        return self._speed

    @speed.setter
    def speed(self, speed_in_knots):
        """
        Set the speed

        :param speed_in_knots: Speed
        :type speed_in_knots: float
        """
        if isinstance(speed_in_knots, (float, int)):
            self._speed = speed_in_knots

    @property
    def proper_compass(self):
        """
        Get the status of the compass

        :return: True if a magnetic compass is being used, False if GPS
        :rtype: bool
        """
        return self._proper_compass

    @proper_compass.setter
    def proper_compass(self, magnetic_compass):
        """
        Set type of compass used

        :param magnetic_compass: True if magnetic compass is used
        :type magnetic_compass: bool
        """
        if isinstance(magnetic_compass, bool):
            self._proper_compass = magnetic_compass

    @property
    def datetime(self):
        """
        Get GPS date

        :return: GPS Date
        :rtype: datetime.datetime
        """
        return self._date

    @datetime.setter
    def datetime(self, date):
        """
        Set the date

        :param date: Date
        :type date: datetime.datetime
        """
        if isinstance(date, datetime.datetime):
            self._date = date

    @property
    def solar_azimuth(self):
        """
        Get solar azimuth

        :return: Solar azimuth
        :rtype: float
        """
        return self._sol_az

    @solar_azimuth.setter
    def solar_azimuth(self, sol_az):
        """
        Set the solar azimuth variable and app label

        :param sol_az: Solar azimuth value
        :type sol_az: float
        """
        if isinstance(sol_az, float):
            self._sol_az = sol_az

    @property
    def sas_azimuth(self):
        """
        Get SAS Azimuth

        :return: SAS Azimuth
        :rtype: float
        """
        return self._sas_az

    @sas_azimuth.setter
    def sas_azimuth(self, sas_az):
        """
        Set the SAS variable and app label

        :param sas_az: SAS Azimuth value
        :type sas_az: float
        """
        if isinstance(sas_az, float):
            self._sas_az = sas_az
            #self.sasmanager.position = sas_az

    @property
    def satellite_number(self):
        """
        Get number of satellites

        :return: Satellite number
        :rtype: int
        """
        return self._sat_num

    @satellite_number.setter
    def satellite_number(self, sat_num):
        """
        Set the satellite number variable and app label

        :param sat_num: Satellite number value
        :type sat_num: int
        """
        if isinstance(sat_num, int):
            self._sat_num = sat_num

    def _do_update(self):
        self.latitude = self.gps_managers[0].lat
        self.longitude = self.gps_managers[0].lon
        self.altitude = self.gps_managers[0].alt
        self.heading = self.gps_managers[0].heading
        self.datetime = self.gps_managers[0].datetime
        self.speed = self.gps_managers[0].speed
        self.proper_compass = self.gps_managers[0].proper_compass
        self.satellite_number = self.gps_managers[0].satellite_number

    def set_solar_azimuth(self, value): # Here because of GLib.idle_add
        """
        Set the solar azimuth

        :param value: Position of the sun
        :type value: float
        """
        self.solar_azimuth = value

    def set_sas_azimuth(self, value): # Here because of GLib.idle_add
        """
        Set the SAS azimuth

        :param value: Position of the SAS
        :type value: float
        """
        self.sas_azimuth = value

#-----------------------------------------------
    def update(self, sol_degrees, sas_degrees):
        self.calc_lock.acquire(True)
        self.old = False
        self.solar_azimuth = sol_degrees
        self.sas_azimuth = sas_degrees
        #self._solar_az_calc_thread.update()
        self.calc_lock.release()
#-----------------------------------------------

    def log_activated(self, option):
        """
        LOG Switch event

        :param switch: Switch that was actioned
        :type switch: Gtk.Switch

        :param gparam: Gtk parameters
        """
        if option:
            logger.info("Starting logging")

            file_formatter = logging.Formatter('[%(asctime)s %(levelname)s] %(message)s')

            # Save in 50MB files
            hypersas_filehandler = logging.handlers.RotatingFileHandler(os.path.join(self.log_folder, "hyper_sas_app.log"), mode='a', maxBytes=52428800, backupCount=20)
            saslogger_filehandler = logging.handlers.RotatingFileHandler(os.path.join(self.log_folder, "sas_manager.log"), mode='a', maxBytes=52428800, backupCount=20)
            gpslib_filehandler = logging.handlers.RotatingFileHandler(os.path.join(self.log_folder, "gps.log"), mode='a', maxBytes=52428800, backupCount=20)

            hypersas_filehandler.setFormatter(file_formatter)
            saslogger_filehandler.setFormatter(file_formatter)
            gpslib_filehandler.setFormatter(file_formatter)

            logger.addHandler(hypersas_filehandler)
            saslogger.addHandler(saslogger_filehandler)
            gpslib.logger.addHandler(gpslib_filehandler)

            logger.info("Started logging")

        else:
            logger.info("Stopping logging")

            # Cheap hack to remove the rotating file handler
            for logger_object in (logger, gpslib.logger, saslogger):
                rot_handlers = [handler for handler in logger_object.handlers if isinstance(handler, logging.handlers.RotatingFileHandler)]
                for rot_handler in rot_handlers:
                    logger_object.removeHandler(rot_handler)


    def gps_activated(self, option):
        """
        GPS Switch event

        :param switch: Switch that was actioned
        :type switch: Gtk.Switch

        :param gparam: Gtk parameters
        """
        if option:
            logger.info("Starting GPS Manager")
            
            for gps_manager in self.gps_managers:
                gps_manager.enable_watchdog(inteval=5)
                gps_manager.start()

            self._gps_stopped = False

            logger.info("Started GPS Manager")

        else:
            logger.info("Stopping GPS Manager")
            
            for gps_manager in self.gps_managers:
                self._gps_stopped = True
                gps_manager.disable_watchdog()
                gps_manager.stop()

            logger.info("Stopped GPS Manager")

    def sas_activated(self, option):
        """
        SAS Switch event

        :param switch: Switch that was actioned
        :type switch: Gtk.Switch

        :param gparam: Gtk parameters
        """
        if option:
            logger.info("Starting SAS Manager")

            self._solar_az_calc_thread = AzimuthCalculation(self)
#-----------------------------------------------
            self.calc_observers.append(self._solar_az_calc_thread)
#-----------------------------------------------
            self._solar_az_calc_thread.start()

            logger.info("Started SAS Manager")
        else:
            logger.info("Stopping SAS Manager")

            self._solar_az_calc_thread.stop = True
            self._solar_az_calc_thread.join()
            print("sas thread alive? =", self._solar_az_calc_thread.is_alive())

            logger.info("Stopped SAS Manager")


def run():
    """
    Run APP
    """
    sas_app = AzimuthWindow()

if __name__ == '__main__':
    run()

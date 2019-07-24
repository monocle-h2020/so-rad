#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SOS Manager

Creates a SOS Manager object and thread to send the radiometry sensor data
from the database to the SOS proxy.
"""

import os
import sys
import re
import matplotlib.pyplot as plt
import numpy as np
import datetime as dt
import dateutil.parser as du
import json
import requests
import sqlite3
import threading
import logging
import time

log = logging.getLogger()


sos_pull_params = {
  "request": "GetDataAvailability",
  "service": "SOS",
  "version": "2.0.0",
  "procedure": "http://monocle-h2020.eu/PML_SORAD",
  "observedProperty": "http://monocle-h2020.eu/PML_SORAD_STRING"
}

server ='https://rsg.pml.ac.uk/sensorweb/service'


class SOS_thread(threading.Thread):
    """
    Thread to send data to SOS proxy
    """
    
    def __init__(self, parent):
        threading.Thread.__init__(self)
        self._parent = parent

        self.stop_sos_thread = False

        log.info("Starting SOS Manager thread")

    def run(self):

        log.info("Started SOS Manager thread")

        current_time = dt.datetime.now()

        if current_time - self._parent.prev_post_time > dt.timedelta(minutes=10):
            
            #log.info("..... Sending data to SOS .....")

            conn = sqlite3.connect('sorad_database.db')
            cur = conn.cursor()

            #cur.execute('select * from sorad_metadata where trigger_id > date({0});'.format(dt.datetime.strptime(prev_end_date, '%Y-%m-%dT%H:%M:%S.%fZ')))
            cur.execute('select * from sorad_metadata inner join sorad_radiometry on sorad_radiometry.sample_id = sorad_metadata.id_ where sorad_metadata.trigger_id > "{0}";'.format(self._parent.prev_post_time))

            for row in cur.fetchall():
                #print(row)
                id_ = row[0]
                trigger_id = row[1]
                gps1_datetime = row[2]
                gps2_datetime = row[3]
                gps1_fix = row[4]
                gps2_fix = row[5]
                gps1_lat = float(row[6])
                gps1_lon = float(row[7])
                gps2_lat = float(row[8])
                gps2_lon = float(row[9])
                poll_rate1 = row[10]
                poll_rate2 = row[11]
                speed1 = row[12]
                speed2 = row[13]
                bearing = row[14]
                sun_azi = row[15]
                sun_elev = row[16]
                motor_temp = row[17]
                driver_temp = row[18]
                n_obs = row[19]
                sample_id = row[20]
                sample_trigger_id = row[21]
                sensor_id = row[22]
                inttime = row[23]
                measurement = row[24]

                string = "320;950;3.3;"
                measurement = measurement[1:-1]
                measurement = measurement.replace(" ", "")
                string += measurement
                print(string)
                #break

                self._parent.update(self, current_time)
                log.info("..... Data sent to SOS: {0} .....".format(dt.datetime.now()))

        time.sleep(10)


class SOS_Manager(object):
    """Object to control the SOS proxy thread"""
    def __init__(self):
        self.started = False
        self.sos_observers = []
        self.sos_thread = None
        self.sos_lock = threading.Lock()

        self.prev_post_time = dt.datetime(1970,1,1)

    def __del__(self):
        self.stop()

    def start(self):
        """Starts the SOS proxy thread if it's not already running"""
        if not self.started:

            log.info("Starting SOS Manager")

            r = requests.post(server, json=sos_params)

            response_dict = r.json()

            self.prev_post_date = du.parse(response_dict['dataAvailability'][0]['phenomenonTime'][1])

            #print(prev_end_date)
            #prev_end_date = "2019-06-26T12:00:00.000Z"

            self.started = True
            self.sos_thread = SOS_thread(self)
            time.sleep(0.1)
            self.sos_observers.append(self.sos_thread)
        else:
            log.warning("SOS thread already started")
    
    def stop(self):
        """Stops the SOS proxy thread"""
        log.info("Stopping SOS thread")
        self.sos_thread.stop_sos_thread = True
        time.sleep(1)
        self.sos_thread.join()
        log.info("SOS thread alive? = {}".format(self.sos_thread.is_alive()))
        self.started = False
        
    def update(self, prev_post_time):
        """Updates the SOS manager variables from the arguments provided"""
        self.sos_lock.acquire(True)
        self.prev_post_time = prev_post_time
        self.sos_lock.release()

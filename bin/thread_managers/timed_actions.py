#!/usr/bin/python3
# -*- coding: utf-8 -*-
"""
A template for implementing further thread based managers for peripheral equipment

Plymouth Marine Laboratory
License: see README.md

"""
import logging
import threading
import sys
import time
import numpy as np
import datetime
from functions import timed_functions as tf

log = logging.getLogger('maintenance')


class MaintenanceManager(object):
    """
    docstring for XYZ Manager class
    """
    def __init__(self, config_dict):
        """
        Initialise this class from a dictionary reflecting a section of the config file.
        : config_dict is a specific section [MISC] of the config file from which settings can be read here:
              self. example_setting = config_dict.getint('example_setting')
        """
        self.updated = None  # typically a datetime to indicate last time the class instance values were updated
        self.thread = None
        self.started = False
        self.stop_monitor = False
        self.sleep_interval = 1.0

        # time sync (gps --> system clock)
        self.last_timesync_requested = datetime.datetime.now() - datetime.timedelta(minutes=1)  # primed, 1 min delay
        self.timesync_interval_mins = 60  # every 60 minutes

    def update_values(self):
        """
        update_values
        """
        self.updated = datetime.datetime.now()
        return

    def __repr__(self):
        return f"Maintenance Manager"

    def start(self):
        """
        Starts reading thread.
        """
        if not self.started:
            self.started = True
            self.thread = threading.Thread(target=self.run)  # use args = (arg1,arg2) if needed
            self.thread.start()
            log.info("Started Maintenance Manager")
        else:
            log.warn("Could not start Maintenance Manager")

    def stop(self):
        """
        Stop the sampling thread
        """
        log.info("Stopping Maintenance  manager")
        self.stop_monitor = True
        time.sleep(1*self.sleep_interval)
        log.info(self.thread)
        self.thread.join(2*self.sleep_interval)
        log.info("Maintenance manager running = {0}".format(self.thread.is_alive()))
        self.started = False

    def run(self):
        """
        Main loop of the thread.
        This will run and read new data and update the instance values
        """
        log.info("Starting Maintenance Manager thread")
        while not self.stop_monitor:

            if datetime.datetime.now() > (self.last_timesync_requested + datetime.timedelta(minutes=self.timesync_interval_mins)):
                tf.sync_clocks()
                self.last_timesync_requested = datetime.datetime.now()
                self.update_values()

            # sleep for a standard period, ideally close to the refresh frequency
            time.sleep(self.sleep_interval)
            continue

    def __del__(self):
        self.stop()

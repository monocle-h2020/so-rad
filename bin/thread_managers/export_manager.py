#!/usr/bin/python3
# -*- coding: utf-8 -*-
"""
Manager class to manage data uploads to parseserver

Plymouth Marine Laboratory
License: see README.md
"""
import logging
import threading
import sys
import time
import numpy as np
import datetime

log = logging.getLogger('export')


class ParseExportManager(object):
    """
    Parseserver export manager
    """
    def __init__(self, export_dict):
        """
        Initialise this class from a dictionary reflecting a section of the config file.
        : config_dict is a specific section [EXPORT] of the config file interpreted as a dictionary in initialisation.py
        """
        self.x = None
        self.y = None
        self.z = None

        self.updated = None  # typically a datetime to indicate last time the class instance values were updated
        self.thread = None
        self.started = False
        self.stop_monitor = False
        self.sleep_interval = 0.01

    def update_values(self):
        """
        docstring for update_values function
       Â"""
        # some logic to read new values and update x, y, z
        self.x += 1
        self.y += 2
        self.z += 3
        self.updated = datetime.datetime.now()
        return

    def __repr__(self):
        return f"XYZ Manager x: {x:0.2f} y: {y:0.2f} z: {z:0.2f}"

    def start(self):
        """
        Starts reading thread.
        """
        if not self.started:
            self.started = True
            self.thread = threading.Thread(target=self.run)  # use args = (arg1,arg2) if needed
            self.thread.start()
            log.info("Started XYZ Manager")
        else:
            log.warn("Could not start XYZ Manager")

    def stop(self):
        """
        Stop the sampling thread
        """
        log.info("Stopping XYZ manager")
        self.stop_monitor = True
        time.sleep(1*self.sleep_interval)
        log.info(self.thread)
        self.thread.join(2*self.sleep_interval)
        log.info("XYZ manager running = {0}".format(self.thread.is_alive()))
        self.started = False

    def run(self):
        """
        Main loop of the thread.
        This will run and read new data and update the instance values
        """
        log.info("Starting XYZ monitor thread")
        while not self.stop_monitor:
            self.update_values()

            # sleep for a standard period, ideally close to the refresh frequency
            time.sleep(self.sleep_interval)
            continue

    def __del__(self):
        self.stop()




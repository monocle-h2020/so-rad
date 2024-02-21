#!/usr/bin/python3
# -*- coding: utf-8 -*-
"""
This script provides classes to interface with cameras.

Implements a class for each type of camera supported. A class is currently provided for:
 - soradcam: A raspberry pi camera 3 (autofocus) running on a Pi Zero 2 w using the picamera2 library

stsi@Plymouth Marine Laboratory
License: see README.md

"""
import os
import logging
import threading
import sys
import time
import numpy as np
import datetime
import requests
import socket

TIMEOUT = 8.0

log = logging.getLogger('cam')

class Soradcam(object):
    """
    Connecting to a remote Pi Zero 2 W running a flask instance with the following routes
     -  /gethigh -  returning best available resolution jpg.
     -  /getmedium - returning medium resolution jpg.
     -  /getlow - returning low resolution jpg.
    """

    def __init__(self, cam=None):
        """
        Set up
        : cam is the [CAM] part of the config file interpreted as a dictionary in initialisation.py
        """
        # time of last request
        self.last_request_time = None
        # last image received
        self.last_valid_result = None
        # last request success
        self.last_request_success = False
        # last time a request was answered (good or bad)
        self.last_received_time = None

        # connectivity
        self.last_api_port_response = None
        self.camera_ip = cam['ip']
        self.camera_port = cam['port']

        # image settings
        self.res = cam['resolution']   # low / medium / full

        # storage_settings
        self.request_label = None
        self.storage_path = cam['storage_path']

        log.info(f"Camera request command = http://{self.camera_ip}:{self.camera_port}/get{self.res}")

        # thread things
        self.thread = None
        self.started = False
        self.sleep_interval = 0.01
        self.busy = False

        # thread monitoring events
        self.stop_monitor = False
        self.picture_requested = False

        self.connected = self.check_api_port()

    def get_picture(self, label=datetime.datetime.now().isoformat()):
        '''get a new picture, this function is only called from the active thread'''
        if self.busy:
            log.warning(f"Camera manager is busy handling request from {self.last_request_time.isoformat()}, request ignored.")
            return
        else:
            self.last_request_time = datetime.datetime.now()
            self.last_received_time = None
            self.last_request_success = False
            self.last_valid_result = None
            self.busy = True
            self.picture_requested = True
            self.request_label = label
            log.info(f"Image requested at {self.last_request_time}")
        return


    def check_api_port(self):
        '''Check whether the API port is responsive'''
        if self.busy:
            log.warning(f"Camera manager is busy handling request from {self.last_request_time.isoformat()}, request ignored.")
            return
        else:
            try:
                s = socket.socket()
                s.connect((self.camera_ip, self.camera_port))

                self.last_api_port_response = datetime.datetime.now()
                return True

            except ConnectionRefusedError:
                log.warning("No response on camera API port")
                return False

            except Exception as err:
                log.warning("Unhandled exception polling camera API port")
                log.exception(err)
                return False

    def __repr__(self):
        return f"Last image requested {self.last_request_time.isoformat()}"

    def start(self):
        """
        Starts reading thread.
        """
        if not self.started:
            self.started = True
            self.thread = threading.Thread(target=self.run)  # use args = (arg1,arg2) if needed
            self.thread.start()
            log.info("Started camera manager")
        else:
            log.warn("Could not start camera manager")

    def stop(self):
        """
        Stop the sampling thread
        """
        log.info("Stopping camera manager")
        self.stop_monitor = True
        time.sleep(1*self.sleep_interval)
        log.info(self.thread)
        self.thread.join(2*self.sleep_interval)
        log.info("Camera manager running = {0}".format(self.thread.is_alive()))
        self.started = False

    def run(self):
        """
        Main loop of the thread.
        This will run and read new data and pass it back
        """
        log.info("Starting camera monitor thread")
        while not self.stop_monitor:
            if not self.connected:
                self.connected = self.check_api_port()
                if not self.connected:
                    log.warning("Camera not responding")
                    time.sleep(1)

            elif self.picture_requested:
                # fetch new image from remote camera
                log.info("Picture request observed")
                camera_url = f"http://{self.camera_ip}/get{self.res}"
                log.info(camera_url)
                try:
                    response = requests.get(camera_url, timeout=TIMEOUT)
                    log.info(response)
                    log.info(f"response code: {response.status_code}")
                    self.last_received_time = datetime.datetime.now() # when request was answered, irrespective of result
                    if (response.status_code >= 200) and (response.status_code < 300):
                        self.last_request_success = True
                        self.last_valid_result = response
                        self.last_received_time = datetime.datetime.now()
                        with open(os.path.join(self.storage_path, f"{self.request_label}.jpg"), 'wb') as outfile:
                            outfile.write(response.content)
                    else:
                        self.last_request_success = False
                        self.last_valid_result = None

                except requests.exceptions.ReadTimeout:
                    log.warning("Timeout on camera request")
                    self.connected = self.check_api_port()

                except Exception as err:
                    log.warning("Unhandled exception during camera request")
                    log.exception(err)
                    self.connected = self.check_api_port()

                # return to normal state
                self.busy = False
                self.picture_requested = False

            # sleep for a short standard period
            time.sleep(self.sleep_interval)
            continue

    def __del__(self):
        self.stop()

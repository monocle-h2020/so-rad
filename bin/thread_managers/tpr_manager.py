#!/usr/bin/python3
# -*- coding: utf-8 -*-
"""
This script provides classes to interface with a tilt/pitch/roll (TPR) sensor manager. The sensor is likely based on an accelerometer.

Implements a class for each type of TPR manager. A class is provided for:
 - Adafruit ADXL345 (wrapper of their board and library for the Analytical Devices ADXL345)

Plymouth Marine Laboratory
License: see README.md

"""
import logging
import threading
import sys
import time
import board
import busio
import adafruit_adxl34x
import numpy as np
import argparse
import datetime
import math
from numpy import argwhere, array, mean, std, append, nanstd, nanmean
log = logging.getLogger()   # report to root logger


class Ada_adxl345(object):
    """
    Adafruit ADXL345 manager class, normally initalised from initialisation.py
    Connects to the board over default I2C ports on the Raspberry Pi, using default the addressing. Probably won't work away from the RPi. 
    """
    def __init__(self, tpr):
        """
        Set up
        : tpr is the [TPR] part of the config file interpreted as a dictionary in initialisation.py
        """
        self.i2c = busio.I2C(board.SCL, board.SDA)
        self.accelerometer = adafruit_adxl34x.ADXL345(self.i2c)
        self.tilt = None
        self.pitch = None
        self.roll = None
        self.tilt_avg = None
        self.tilt_std = None
        self.pitch_avg = None
        self.pitch_std = None
        self.roll_avg = None
        self.roll_std = None
        self.updated = None
        self.avg_updated = None
        self.thread = None
        self.started = False
        self.stop_monitor = False
        self.sleep_interval = 0.01
        # the orientation of our sensor is not as written on the board, so here we adjust
        # normally x = 0, y = 1, z = 2. Store this in the config file?
        self.yindex = tpr['yindex']  # 2
        self.zindex = tpr['zindex']  # 0
        self.xindex = tpr['xindex']  # 1
        self.sampling_time = tpr['sampling_time']  # sampling cycle in seconds, default 10 seconds
        self.update_pitch_roll_single()   # init with first reading
        self.buffer_time =  [self.updated]
        self.buffer_tilt =  [self.tilt]
        self.buffer_pitch = [self.pitch]
        self.buffer_roll =  [self.roll]

    def update_pitch_roll_single(self):
        '''Pitch and Roll from rotation around X and Y axes'''
        x = float(self.accelerometer.acceleration[self.xindex])
        y = float(self.accelerometer.acceleration[self.yindex])
        z = float(self.accelerometer.acceleration[self.zindex])

        x_axis_rotation = math.atan( y / math.sqrt(x**2 + z**2) )  # this is the roll rotation, around the x (forward) axis. positive is to the right
        y_axis_rotation = math.atan( x / math.sqrt(y**2 + z**2) )  # this is the pitch rotation, around the y (sideward) axis. positive is up.
        if z != 0.0:
            z_axis_rotation = math.atan( math.sqrt(x**2 + y**2) / z )  # Theta or Tilt rotation, between z (up) axis and gravity
        else:
            z_axis_rotation = 90.0

        self.pitch = math.degrees(x_axis_rotation)
        self.roll  = math.degrees(y_axis_rotation)
        self.tilt  = - math.degrees(z_axis_rotation)
        self.updated = datetime.datetime.now()
        return self.updated, self.tilt, self.pitch, self.roll

    def __repr__(self):
        return "Tilt {0:0.2f} \tPitch {1:0.2f} \tRoll {2:0.2f} degrees".format(self.tilt, self.pitch, self.roll)

    def start(self):
        """
        Starts reading thread.
        """
        if not self.started:
            self.started = True
            self.thread = threading.Thread(target=self.run)  # use args = (arg1,arg2) if needed
            self.thread.start()
            log.info("Started TPR manager")
        else:
            log.warn("Could not start TPR manager")

    def stop(self):
        """
        Stop the sampling thread
        """
        log.info("Stopping TPR manager")
        self.stop_monitor = True
        time.sleep(1*self.sleep_interval)
        log.info(self.thread)
        self.thread.join(2*self.sleep_interval)
        log.info("TPR manager running = {0}".format(self.thread.is_alive()))
        self.started = False

    def run(self):
        """
        Main loop of the thread.
        This will run and read new data and pass it back
        """
        log.info("Starting TPR monitor thread")
        while not self.stop_monitor:
            timestamp, tilt, pitch, roll = self.update_pitch_roll_single()
            if len(self.buffer_time)<10:
                self.buffer_time.append(timestamp)
                self.buffer_tilt.append(tilt)
                self.buffer_pitch.append(pitch)
                self.buffer_roll.append(roll)
                time.sleep(self.sleep_interval)
                continue
            else:
                # housekeeping, purge old entries from buffer
                time_cutoff = datetime.datetime.now() - datetime.timedelta(seconds=self.sampling_time)

                current_keep = argwhere(array(self.buffer_time) >= time_cutoff)
                current_keep = array([k[0] for k in current_keep]) # flatten, not sure why this is needed

                self.buffer_time  = list(array(self.buffer_time)[current_keep])
                self.buffer_tilt  = list(array(self.buffer_tilt)[current_keep])
                self.buffer_pitch = list(array(self.buffer_pitch)[current_keep])
                self.buffer_roll  = list(array(self.buffer_roll)[current_keep])
                self.buffer_time.append(timestamp)
                self.buffer_tilt.append(tilt)
                self.buffer_pitch.append(pitch)
                self.buffer_roll.append(roll)
                # buffer is now current

                buffer_age = (datetime.datetime.now() - self.buffer_time[0]).total_seconds()
                if buffer_age > self.sampling_time:
                    # average and stdev of buffered result
                    self.tilt_avg  = nanmean(self.buffer_tilt)
                    self.tilt_std  = nanstd(self.buffer_tilt)
                    self.pitch_avg = nanmean(self.buffer_pitch)
                    self.pitch_std = nanstd(self.buffer_pitch)
                    self.roll_avg  = nanmean(self.buffer_roll)
                    self.roll_std  = nanstd(self.buffer_roll)
                    self.avg_updated = datetime.datetime.now()

            time.sleep(self.sleep_interval) # sleep for a standard period, ideally close to the refresh frequency of the sensor (0.01s)
            continue

    def __del__(self):
        self.stop()

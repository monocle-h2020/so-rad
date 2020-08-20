#!/usr/bin/env python3

"""
Simple test for Tilt Pitch Roll (TPR) sensor (ADXL345)
"""

import time
import board
import busio
import adafruit_adxl34x
import numpy as np
import argparse
import datetime
import math


class ADXL345(object):
    '''
    ADXL345 via adafruit_adxl34x library giving Tilt/Pitch/Roll
    '''
    def __init__(self):
        """
        Set up
        """
        self.i2c = busio.I2C(board.SCL, board.SDA)
        self.accelerometer = adafruit_adxl34x.ADXL345(self.i2c)
        self.tilt = None
        self.pitch = None
        self.roll = None
        self.updated = None
        # the orientation of our sensor is not as written on the board, so here we adjust
        # normally x = 0, y = 1, z = 2. Store this in the config file?
        self.xindex = 1  # config
        self.yindex = 2  # config
        self.zindex = 0  # config

    def get_pitch_roll(self):
        '''Pitch and Roll from rotation around X and Y axes'''
        x = float(self.accelerometer.acceleration[self.xindex])
        y = float(self.accelerometer.acceleration[self.yindex])
        z = float(self.accelerometer.acceleration[self.zindex])

        #x_axis_rotation = math.atan2(y, math.sqrt((x**2) + (z**2)) )  # x and y planes are exchangeable
        #y_axis_rotation = -math.atan2(x, math.sqrt((y**2) + (z**2)) )

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


def main(config, duration, sleep):
    # get protocol from config
    protocol = "ADXL345"
    acc = ADXL345()

    t1 = time.time()

    while time.time() < t1 + duration:

        u, t, p, r = acc.get_pitch_roll()
        print("{0} | Tilt: {1:2.2f} \t Pitch: {2:2.2f} \t Roll: {3:2.2f}".format(u, t, p, r))

        time.sleep(sleep)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument("-d", "--duration", default=3, type=int, help="Test duration in seconds (default 10s)")
    parser.add_argument("-s", "--sleep", default = 0.1, type=float, help="Sleep time between samples (min ~0.01s, default 0.1s)")
    parser.add_argument("-c", "--config", required=True, help="Path to config file")
    args = parser.parse_args()

    # read TPR usage and protocol from config file
    # use the initialisation module to get the right TPR class

    main(args.config, args.duration, args.sleep)


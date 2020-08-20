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
        #self.tilt = 0.0
        self.pitch = None
        self.roll = None
        self.updated = None

    def get_pitch_roll(self):
        '''Pitch and Roll from rotation around X and Y axes'''
        x = self.accelerometer.acceleration[0]
        y = self.accelerometer.acceleration[1]
        z = self.accelerometer.acceleration[2]
        #distance = math.sqrt((x * x) + (y * y))
        x_axis_rotation = math.atan2(y, math.sqrt((x * x) + (z * z)) )
        y_axis_rotation = -math.atan2(x, math.sqrt((y * y) + (z * z)) )

        self.pitch = math.degrees(x_axis_rotation)
        self.roll  = math.degrees(y_axis_rotation)
        self.updated = datetime.datetime.now()
        return self.updated, self.pitch, self.roll


def main(config, duration):
    # get protocol from config
    protocol = "ADXL345"
    acc = ADXL345()

    t1 = time.time()

    while time.time() < t1 + duration:

        t, p, r = acc.get_pitch_roll()
        print("{0} | Pitch: {1:2.5f} \t Roll: {2:2.5f}".format(t, p, r))

        time.sleep(0.1)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument("-d", "--duration", default=3, type=int, help="Test duration in seconds (default 10s)")
    parser.add_argument("-c", "--config", required=True, help="Path to config file")
    args = parser.parse_args()

    # read TPR usage and protocol from config file

    main(args.config, args.duration)


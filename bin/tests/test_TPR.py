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

parser = argparse.ArgumentParser()
parser.add_argument("-t", "--time", default=10, type=int, help="Test duration in seconds (default 10s)")
args = parser.parse_args()

print("Connecting on I2C")
i2c = busio.I2C(board.SCL, board.SDA)
accelerometer = adafruit_adxl34x.ADXL345(i2c)


def main():
    no_s = args.time
    t_end = time.time() + no_s
    t1 = (time.time())

    a = []
    x = []
    y = []
    z = []

    while time.time()< t_end:

        acc = accelerometer.acceleration
        x, y, z = acc
        x, y, z = float(x), float(y), float(z)

        print("x: {0:2.5f}\ty: {1:2.5f}\t z: {2:2.5f}".format(x, y, z))

        time.sleep(0.1)


if __name__ == '__main__':
     main()


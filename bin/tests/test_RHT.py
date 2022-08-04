#!/usr/bin/env python3

"""
Short test to check RH&T sensor operates correctly
Test is specifically for DHT22 RH&T sensor
"""
import argparse
import Adafruit_DHT
import datetime
import os
import time


parser = argparse.ArgumentParser()
parser.add_argument("-p", "--pin", type=int, default=14, help="GPIO data pin number for RHT sensor (default 14)")
args = parser.parse_args()

DHT_SENSOR = Adafruit_DHT.DHT22
DHT_PIN = args.pin


def test_run():
    for i in range(10):
        humidity, temperature = Adafruit_DHT.read_retry(DHT_SENSOR, DHT_PIN)
        print("[{0}] RH: {1}% Temperature: {2} degrees C".format(i, humidity, temperature))
        time.sleep(0.1)


if __name__ == '__main__':
    test_run()

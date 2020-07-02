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
parser.add_argument("-o", "--output", action="store_true", help="create output file")
parser.add_argument("-p", "--pin", action="store", type=int, help="GPIO Data pin No. for RHT sensor")
args = parser.parse_args()

Pin_GPIO = 14
if args.pin:
    Pin_GPIO = 14
DHT_SENSOR = Adafruit_DHT.DHT22
DHT_PIN = Pin_GPIO
try:
    f = open('/home/pi/Pi-sensor/RHT_test_output.csv', 'a+') #sorad-code/bin/tests/RHT_test_output.csv', 'a+')
    if os.stat('/home/pi/Pi-sensors/RHT_test_output.csv').st_size ==0: #sorad-code/bin/tests/RHT_test_output.csv').st_size == 0:
        f.write('Date,Time,Temperature,Humidity\r\n')
except:
    pass

def test_run():
        humidity, temperature = Adafruit_DHT.read_retry(DHT_SENSOR, DHT_PIN)
        if humidity is not None and temperature is not None:
            print('RH: ', humidity,'T: ', temperature)
            if args.output:
                f.write('{0},{1},{2:0.1f}*C,{3:0.1f}%\r\n'.format(time.strftime('%y-%m-%d'), time.strftime('%H:%M:%S'), temperature, humidity))
        else:
            print("Failed to retrieve data from humidity sensor check GPIO pins")


if __name__ == '__main__':
    test_run()

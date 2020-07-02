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
parser.add_argument("-o", "--output", action="store_true", help="create output file")
parser.add_argument("-d", "--display", action="store_true", help="dsiplay output data")
parser.add_argument("-t", "--time", action="store", type=int, help="Seconds to record data for, type.int")
args = parser.parse_args()

i2c = busio.I2C(board.SCL, board.SDA)
accelerometer = adafruit_adxl34x.ADXL345(i2c)
print("I2C active.. ")

def main():
    # Define number of seconds to record data
    no_s = 1
    if args.time:
        no_s = args.time
    t_end = time.time() + no_s
    t1 = (time.time())
    # Create variable and record for specified time
    a = []
    x = []; y = []; z = []
    acc_x = []; acc_y = []; acc_z = []
    while time.time()< t_end:
        a = ('%f %f %f' %accelerometer.acceleration)
        x, y, z = a.split(' ',2)
        x, y, z = float(x), float(y), float(z)
        acc_x.append(x); acc_y.append(y); acc_z.append(z)
        if args.output:
            try:
                f = open('/home/pi/Pi-sensor/TPR_test_output.csv', 'a+') #sorad-code/so-rad/bin/tests/TPR_test_output.csv', 'a+')
                if os.stat('/home/pi/Pi-sensor/TPR_test_output.csv)st.size == 0 #sorad-code/bin/tests/TPR_test_output.csv').st_size == 0:
                    f.write('Date,Time,x,y,z\r\n')
            except:
                pass
        f.write('{0},{1},{2:0.5f},{3:0.5f},{4:0.5f} \r\n'.format(time.strftime('%y-%m-%d'), time.strftime('%H:%M:%S'), x, y, z))

    if args.display:
        # Calculate how long loop ran for
        t2 = (time.time())
        t_diff = t2-t1

        # Display data
        print('data recorded over ', no_s,'s','time taken (s)', t_diff)
        print('frequency: ', len(acc_x)/t_diff,'/s')
        print('x: ', acc_x,
              'y: ', acc_y,
              'z: ', acc_z)
        exit(0)
if __name__ == '__main__':
     main()


#!/usr/bin/env python3

"""
Simple test for Tilt Pitch Roll (TPR) sensor (ADXL345)
"""

import sys
import os
import time
import inspect
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(inspect.getfile(inspect.currentframe())))))
import serial.tools.list_ports as list_ports
from initialisation import tpr_init
from main_app import parse_args, read_config

test_duration_single_reads = 1  # seconds
test_duration_monitor_average = 1000  # seconds


def main(conf):
    print("Start test, initialising")
    tpr, tpr_manager = tpr_init(conf['TPR'])

    print("Show live data for {0} second (0.01s refresh rate)".format(test_duration_single_reads))
    # get protocol from config
    t1 = time.time()
    while time.time() < t1 + test_duration_single_reads:

        u, t, p, r, x, y, z = tpr_manager.update_pitch_roll_single()
        print("{0} | Tilt: {1:2.2f} \t Pitch: {2:2.2f} \t Roll: {3:2.2f} \t x/y/z accelleration: {4}/{5}/{6}".format(u, t, p, r, x, y, z))

        time.sleep(0.01)


    print("\n\nrun monitor for {0} seconds".format(test_duration_monitor_average))
    tpr_manager.start()
    t1 = time.time()
    while time.time() < t1 + test_duration_monitor_average:
        if None in [tpr_manager.avg_updated, tpr_manager.tilt_avg, tpr_manager.tilt_std,
                      tpr_manager.pitch_avg, tpr_manager.pitch_std,
                      tpr_manager.roll_avg, tpr_manager.roll_std]:
            print("Waiting for buffer to fill before calculating average. Buffer length: {0}, oldest record: {1}".format(len(tpr_manager.buffer_tilt), tpr_manager.buffer_time[0]))
        else:
            print("{0} | Tilt: {1:2.1f} (±{2:2.2f}) \t Pitch: {3:2.1f} (±{4:2.2f}) \t Roll: {5:2.1f} (±{6:2.2f})"\
                     .format(tpr_manager.avg_updated, tpr_manager.tilt_avg, tpr_manager.tilt_std,
                      tpr_manager.pitch_avg, tpr_manager.pitch_std,
                      tpr_manager.roll_avg, tpr_manager.roll_std))
        time.sleep(1)

    print("finished test, stopping monitor")
    tpr_manager.stop()

if __name__ == '__main__':
    args = parse_args()
    conf = read_config(args.config_file)
    # read TPR usage and protocol from config file
    # use the initialisation module to get the right TPR class

    main(conf)


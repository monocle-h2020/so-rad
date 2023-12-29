#!/usr/bin/env python3
"""
Simple test for camera connectivity
"""

import sys
import os
import time
import inspect
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(inspect.getfile(inspect.currentframe())))))
#from initialisation import tpr_init
#from main_app import parse_args
#import functions.config_functions as cf
import thread_managers.camera_manager as cameras

#def main(conf):
def main():
    print("Start test, initialising")
    #tpr = tpr_init(conf['TPR'])
    #tpr_manager = tpr['manager']
    #print("Show live data for {0} second (0.01s refresh rate)".format(test_duration_single_reads))
    # get protocol from config

    camera = cameras.Soradcam()
    camera.start()

    t0 = time.perf_counter()
    camera.get_picture()
    while camera.busy and time.perf_counter()-t0 < 5.0:
        time.sleep(0.1)

    if camera.last_request_success:
        time_elapsed = (camera.last_received_time - camera.last_request_time).total_seconds()
        print(f"Image taken at {camera.last_request_time.isoformat()}: {len(camera.last_valid_result.content)} bytes [{time_elapsed} s]")
    else:
        print(f"No image received, last response at {camera.last_received_time.isoformat()}")

    print("finished test, stopping monitor")
    camera.stop()


if __name__ == '__main__':
    #args = parse_args()
    #conf = cf.read_config(args.config_file)
    #conf = cf.update_config(conf, args.local_config_file)
    #main(conf)
    main()


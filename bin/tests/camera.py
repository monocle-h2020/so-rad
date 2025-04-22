#!/usr/bin/env python3
"""
Simple test for camera connectivity
"""

import sys
import os
import time
import datetime
import inspect
import logging
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(inspect.getfile(inspect.currentframe())))))
from initialisation import camera_init
from main_app import parse_args
import functions.config_functions as cf
import thread_managers.camera_manager as cameras

import functions.redis_functions as rf

# connect to redis
redis_client = rf.init()

# hardcoded timeout on API request
request_timeout = cameras.TIMEOUT


def main(conf):
    print("Start test, initialising")
    cam = camera_init(conf['CAMERA'])
    camera = cam['manager']

    camera.start()
    log.info(f"Connected to camera: {camera.connected}")

    t0 = time.perf_counter()

    label = f"test_{datetime.datetime.now().isoformat()}"
    camera.get_picture(label=label)

    while camera.busy and time.perf_counter()-t0 < (request_timeout + 1):
        log.debug("Camera busy..")
        time.sleep(0.1)

    if camera.last_request_success:
        time_elapsed = (camera.last_received_time - camera.last_request_time).total_seconds()
        print(f"Image taken at {camera.last_request_time.isoformat()}: {len(camera.last_valid_result.content)} bytes [{time_elapsed} s]")
    else:
        print(f"No image received, last response at {camera.last_received_time.isoformat()}")

    outpath = os.path.join(cam['storage_path'], label+'.jpg')
    if os.path.exists(outpath):
        print(f"Image stored at {outpath}")
        rf.store(redis_client, 'last_picam_image', outpath)
    else:
        print(f"Error: Image not found at {outpath}")

    print("finished test, stopping monitor")
    camera.stop()


if __name__ == '__main__':
    args = parse_args()
    conf = cf.read_config(args.config_file)
    conf = cf.update_config(conf, args.local_config_file)

    log = logging.getLogger()
    handler = logging.StreamHandler(sys.stdout)
    log.setLevel(logging.INFO)
    handler.setLevel(logging.INFO)
    formatter = logging.Formatter('%(asctime)s| %(levelname)s | %(name)s | %(message)s')
    handler.setFormatter(formatter)
    log.addHandler(handler)

    main(conf)


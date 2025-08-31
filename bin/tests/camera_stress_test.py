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
request_timeout = cameras.TIMEOUT*2.


def main(conf):
    print("Start test, initialising")
    cam = camera_init(conf['CAMERA'])
    camera = cam['manager']

    camera.start()
    log.info(f"Connected to camera: {camera.connected}")


    image_requests = []
    for i in range(20):
        log.info(f"{i+1}/20 Requesting an image every second (stress testing)")
        label = f"test_{datetime.datetime.now().isoformat()}"
        if not camera.busy:
            camera.get_picture(label=label)
            t0 = time.perf_counter()
            image_requests.append(label)
            camdict, u, s = rf.retrieve(redis_client, 'camera_dict', freshness=None)
            for key, val in camdict.items():
                log.info(f"{key}: {val}")

        time.sleep(1)

    for f in image_requests:
        outpath = os.path.join(cam['storage_path'], f+'.jpg')
        if os.path.exists(outpath):
            print(f"Image stored at {outpath}")
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


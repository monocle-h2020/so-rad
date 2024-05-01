#!/usr/bin/env python3
"""
Monitor objects stored in redis by main_app
"""

import sys
import os
import time
import datetime
import inspect
import logging
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(inspect.getfile(inspect.currentframe())))))
from main_app import parse_args
import functions.config_functions as cf
import functions.redis_functions as rf
import numpy as np

sleep_interval = 1

def main():
    c = rf.init()
    try:
        while True:
            for k in ['counter', 'disk_free_gb', 'system_status', 'sampling_status']:
                r, u, stale = rf.retrieve(c, k, freshness = None)
                if r is None:
                    r = 'None'  # this is just to allow formatting
                stale_str = {True:'STALE', False:'', None:'missing'}[stale]

                log.info(f"{k:<15} {r:>20}\t updated: {u}  {stale_str}")
            time.sleep(sleep_interval)
    except KeyboardInterrupt:
        pass

    except Exception as msg:
        log.exception(msg)


if __name__ == '__main__':
    #args = parse_args()
    #conf = cf.read_config(args.config_file)
    #conf = cf.update_config(conf, args.local_config_file)

    log = logging.getLogger()
    handler = logging.StreamHandler(sys.stdout)
    log.setLevel(logging.INFO)
    handler.setLevel(logging.INFO)
    formatter = logging.Formatter('%(asctime)s| %(levelname)s | %(name)s | %(message)s')
    handler.setFormatter(formatter)
    log.addHandler(handler)

    #main(conf)
    main()

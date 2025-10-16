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

sleep_interval = 0.5

def main():
    c = rf.init()
    try:
        while True:
            os.system('clear')
            # individual redis keys
            log.info(f"====================================================")
            for k in ['counter', 'disk_free_gb', 'system_status', 'sampling_status',
                      'gps_manager']:
                r, u, stale = rf.retrieve(c, k, freshness=None)
                if r is None:
                    r = 'None'  # this is just to allow formatting
                stale_str = {True:'STALE', False:'', None:'missing'}[stale]
                if isinstance(r, dict):
                    for kk, vv in r.items():
                        if isinstance(vv, datetime.datetime):
                            vv = datetime.datetime.strftime(vv, '%Y%m%d %H%M%S')
                        log.info(f"{kk:<20} {vv:>20}\t updated: {u}  {stale_str}")
                else:
                    log.info(f"{k:<20} {r:>20}\t updated: {u}  {stale_str}")

            log.info(f"- - - - - - - - - - - - - - - - - - - - - - - - - - -")
            # combined values dict (to be made obsolete at some point)
            r, u, stale = rf.retrieve(c, 'values', freshness=None)
            for k in ['lat0', 'lon0', 'alt0', 'headMot', 'relPosHeading', 'accHeading', 'fix',
                      'flags_headVehValid', 'flags_diffSolN', 'flags_gnssFixOK', 'speed', 'nsat0',
                      'pi_temp', 'tilt_avg', 'tilt_std', 'inside_temp', 'inside_rh',
                      'driver_temp', 'motor_temp']:
                try:
                    log.info(f"{k:<20} {r[k]:>20}\t updated: {u}  {stale_str}")
                except: pass
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

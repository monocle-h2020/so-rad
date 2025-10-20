#!/usr/bin/env python3
"""
Simple test to test redis functions
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

def main(conf):

    c = rf.init()

    for i in [999, 999.999, '999', datetime.datetime.now(), np.nan,
              np.int16(999), np.int32(999), np.float16(999.999), np.float32(999.999),
              [1,2,3,'a','b','c'], (1,2,3,'a','b','c'), {1:'a',2:'b',3:'c'}, 1]:
        rf.store(c, 'test', i, expires=2)
        r, u, s = rf.retrieve(c, 'test', freshness = 10)
        log.info(f"Stored {i} (dtype {type(i)}), retrieved {r} (dtype {type(r)}), updated: {u}")

    log.info("Test object expiration using short freshness (should return None and throw warning that result is ignored)")
    rf.store(c, 'test', i, expires=-1)  # should instantly expire
    r, u, s = rf.retrieve(c, 'test', freshness=0)
    log.info(f"Stored {i} (dtype {type(i)}), retrieved {r} (dtype {type(r)}), updated: {u}")

    log.info("Test object expiration with freshness=None (should only throw warning and return value as normal)")
    r, u, s = rf.retrieve(c, 'test', freshness=None)
    log.info(f"Stored {i} (dtype {type(i)}), retrieved {r} (dtype {type(r)}), updated: {u}")

    print("Finished tests")


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


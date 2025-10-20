#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test time synchronization
@author: stsi
"""

import os
import time
import sys
import inspect
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(inspect.getfile(inspect.currentframe())))))
from functions.timed_functions import sync_clocks
import logging


def run_test():
    """
    Do a single function call
    """
    sync_clocks()


if __name__ == '__main__':
    # start logging to stdout
    log = logging.getLogger()
    handler = logging.StreamHandler(sys.stdout)
    #log.setLevel(logging.INFO)
    #handler.setLevel(logging.INFO)
    log.setLevel(logging.DEBUG)
    handler.setLevel(logging.DEBUG)

    formatter = logging.Formatter('%(asctime)s| %(levelname)s | %(name)s | %(message)s')
    handler.setFormatter(formatter)
    log.addHandler(handler)

    log.info("Starting Test")
    run_test()
    log.info("Finished Test")

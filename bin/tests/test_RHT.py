#!/usr/bin/env python3

"""
Short test to check RH&T sensor operates correctly
"""

import sys
import os
import time
import inspect
import logging
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(inspect.getfile(inspect.currentframe())))))
import serial.tools.list_ports as list_ports
from initialisation import rht_init
from main_app import parse_args
import functions.config_functions as cf
test_duration_single_reads = 60  # seconds

def test_run(conf):
    log = logging.getLogger(__name__)
    log.info("Start test, initialising")

    rht = rht_init(conf['RHT'])
    rht_manager = rht['manager']
    log.info(rht_manager)

    print("Show live data for {0} second (2s refresh rate)".format(test_duration_single_reads))

    # get protocol from config
    t1 = time.time()
    while time.time() < t1 + test_duration_single_reads:

        t_last, humidity, temperature = rht_manager.update_rht_single()
        log.info(f"{t_last.isoformat()} \t RH: {humidity}% \t Temperature: {temperature}C")
        time.sleep(2)

    log.info("Finished test.")


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

    test_run(conf)


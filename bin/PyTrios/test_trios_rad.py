#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
A simple test to check TriOS Radiometer G1 connectivity using the PyTrios library.
@author: stsi
"""
import sys
import os
import inspect
import argparse
import datetime
import logging
import serial.tools.list_ports as list_ports
import radiometer_manager

def single_test(radiometry_manager):
    log.info(f"Trigger measurement on all sensors")
    trig_id, specs, sids, itimes, preincs, postincs, inctemps  = radiometry_manager.sample_all(datetime.datetime.now())

    for sid, itime, preinc, postinc, inctemp, spec in zip(sids, itimes, preincs, postincs, inctemps, specs):
        log.info(f"Received spectrum from {sid}: {trig_id} {itime}. Spectrum: {spec[0:3]}...{spec[-3::]}")
        log.debug(f"Full spectrum:{spec}")


def run_test(ports, repeat=False):
    """Test connectivity to TriOS RAMSES radiometer sensors"""

    log.info("Starting radiometry manager")
    rad_manager = radiometer_manager.TriosManager(ports)

    if repeat:
       log.info("Starting repeat measurements, press CTRL-C to stop")
       while repeat:
           try:
               single_test(rad_manager)
           except KeyboardInterrupt:
               repeat = False
    else:
        single_test(rad_manager)

    log.info("Stopping radiometry manager threads")
    if radiometry_manager is not None:
        radiometry_manager.stop()


def parse_args():
    """parse command line arguments"""
    parser = argparse.ArgumentParser()
    parser.add_argument('-c', '--comport', nargs='+', type=str, required=True, help="serial port(s) (space-separated) to which sensor(s) is/are connected")
    args = parser.parse_args()
    return args


if __name__ == '__main__':
    args = parse_args()

    log = logging.getLogger()
    handler = logging.StreamHandler(sys.stdout)
    log.setLevel(logging.INFO)
    handler.setLevel(logging.INFO)
    formatter = logging.Formatter('%(asctime)s| %(levelname)s | %(name)s | %(message)s')
    handler.setFormatter(formatter)
    log.addHandler(handler)

    run_test(args.comport, repeat=False) # select repeat = True to repeat test until interrupted

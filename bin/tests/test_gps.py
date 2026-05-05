#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
A simple test to check GPS connectivity
@author: stsi
"""

import os
import time
import sys
import inspect
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(inspect.getfile(inspect.currentframe())))))
import serial.tools.list_ports as list_ports
import initialisation
from main_app import parse_args
from functions.check_functions import check_gps, check_heading
from functions.config_functions import read_config, update_config
import logging


def run_test(conf, terse=False):
    """Show GPS output stream"""
    # collect messages to return to web service
    test_duration = 999  # seconds

    ports = list_ports.comports()
    for port, desc, hwid in sorted(ports):
        log.info("port info: {0} {1} {2}".format(port, desc, hwid))

    log.info("Connecting to gps ports")
    gps = initialisation.gps_init(conf['GPS'], ports)
    log.info(gps['serial1'])
    log.info(f"GPS protocol: {gps['protocol']}")

    if not terse:
        log.info("Showing a few blocks of gps data, if available")
        for i in range(5):
            log.info(f"{i}, {gps['serial1'].port}, {gps['serial1'].inWaiting()}")
            log.info(f"{i}, {gps['serial1'].port}, {gps['serial1'].read(100)}")

    log.info("starting gps managers")
    if gps['manager'] is not None:
        gps['manager'].add_serial_port(gps['serial1'])
        gps['manager'].start()
    else:
        log.info("No GPS manager identified")
    time.sleep(0.1)

    if terse:
        test_duration = 10

    if not terse:
        log.info("Showing gps manager data for {0}s, CTRL-C to stop".format(test_duration))
    log.info(f"Port used: {gps['manager'].serial_ports}")

    t0 = time.perf_counter()

    try:
        if gps['protocol'] in ['pyubx2']:
            while (time.perf_counter() - t0) < test_duration:
                header = """\nTime \t\t {0} \nLat \t\t {1} \t Lon \t {2} \nSpeed \t\t {3} \nFix \t\t {4} \t nSat {7} \t Checks: {8} \nheading \t {5} (Check: {6})""".\
                      format(gps['manager'].last_update, gps['manager'].lat, gps['manager'].lon,
                      gps['manager'].speed, gps['manager'].fix,
                      gps['manager'].heading, check_heading(gps), gps['manager'].satellite_number, check_gps(gps))
                vals = """headMot \t {0} \nrelPosHead \t {1} \nAcc \t\t {2} \nVehH valid \t {3} \nRelPosH valid\t {4} \nDiff Soln\t {5}\n GNSS fix\t {6}""".\
                      format(gps['manager'].headMot, gps['manager'].relPosHeading, gps['manager'].accHeading,
                      gps['manager'].flags_headVehValid, gps['manager'].flag_relPosHeadingValid, gps['manager'].flags_diffSolN, gps['manager'].flags_gnssFixOK)
                log.info(header)
                log.info(vals)
                time.sleep(2.0)

        elif gps['protocol'] in ['djim350', 'nmea0183']:
            while (time.perf_counter() - t0) < test_duration:
                msg = f"Updated\t\t {gps['manager'].last_update}\n"
                msg+= f"Gps time\t\t {gps['manager'].datetime}\n"
                msg+= f"Lat\t\t {gps['manager'].lat}\n"
                msg+= f"Lon\t\t {gps['manager'].lon}\n"
                msg+= f"Heading\t\t {gps['manager'].heading}\n"
                msg+= f"Speed\t\t {gps['manager'].speed}\n"
                msg+= f"Fix\t\t {gps['manager'].fix}\n"
                msg+= f"pos_mode\t\t {gps['manager'].pos_mode}\n"
                msg+= f"check: {check_gps(gps)}\n"
                log.info(msg)
                time.sleep(1.0)

        else:
            log.critical(f"Protocol {gps['protocol']} not implemented")

    except (KeyboardInterrupt, SystemExit):
        log.info("Stopping GPS manager thread")
        gps['manager'].stop()
        time.sleep(0.5)
        sys.exit(0)

    except Exception:
        raise



    if gps['manager'] is not None:
        log.info("Stopping GPS manager thread")
        gps['manager'].stop()
        time.sleep(0.5)

    return


if __name__ == '__main__':
    args = parse_args()
    conf = read_config(args.config_file)
    # update config with local overrides
    conf = update_config(conf, args.local_config_file, verbosity=not args.terse)

    # start logging to stdout
    log = logging.getLogger()
    handler = logging.StreamHandler(sys.stdout)
    log.setLevel(logging.INFO)
    handler.setLevel(logging.INFO)
    formatter = logging.Formatter('%(asctime)s| %(levelname)s | %(name)s | %(message)s')
    handler.setFormatter(formatter)
    log.addHandler(handler)

    run_test(conf, args.terse)

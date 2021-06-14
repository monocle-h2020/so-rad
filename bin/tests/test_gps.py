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
import functions.config_functions as cf

test_duration = 3600  # seconds


def run_test():
    args = parse_args()
    conf = cf.read_config(args.config_file)
    conf = cf.update_config(conf, args.local_config_file)

    ports = list_ports.comports()
    for port, desc, hwid in sorted(ports):
        print("port info: {0} {1} {2}".format(port, desc, hwid))

    print("Connecting to gps ports")
    gps = initialisation.gps_init(conf['GPS'], ports)

    print(gps['serial1'])

    print("Showing a few blocks of gps data, if available")
    for i in range(5):
        print(i, gps['serial1'].port, gps['serial1'].inWaiting())
        print(i, gps['serial1'].port, gps['serial1'].read(100))

    print("starting gps managers")
    if gps['manager'] is not None:
        gps['manager'].add_serial_port(gps['serial1'])
        gps['manager'].start()
    else:
        print("No GPS manager identified")
    time.sleep(0.1)

    print("Showing gps manager data for {0}s, CTRL-C to stop".format(test_duration))
    print("Ports used: {0}".format(gps['manager'].serial_ports))
    t0 = time.time()
    print("Last update \t\t\t Latitude \t Longitude \t Speed \t\t Fix \t Heading (check) \t N sat (check)")
    while time.time() - t0 < test_duration:
        try:
            print("""\nTime \t\t {0} \nLat \t\t {1} \t Lon \t {2} \nSpeed \t\t {3} \nFix \t\t {4} \t nSat {7} \t Checks: {8} \nheading \t {5} ({6})""".\
                  format(gps['manager'].last_update, gps['manager'].lat, gps['manager'].lon,
                  gps['manager'].speed, gps['manager'].fix,
                  gps['manager'].heading, check_heading(gps), gps['manager'].satellite_number, check_gps(gps)))
            print("""headMot \t {0} \nrelPosHead \t {1} \nAcc \t\t {2} \nVehH valid \t {3} \nRelPosH valid\t {4} \nDiff Soln\t {5}\n GNSS fix\t {6}""".\
                  format(gps['manager'].headMot, gps['manager'].relPosHeading, gps['manager'].accHeading,
                  gps['manager'].flags_headVehValid, gps['manager'].flag_relPosHeadingValid, gps['manager'].flags_diffSolN, gps['manager'].flags_gnssFixOK))

            time.sleep(0.9)
        except (KeyboardInterrupt, SystemExit):
            print("Stopping GPS manager thread")
            gps['manager'].stop()
            time.sleep(0.5)
            sys.exit(0)
        except Exception:
            raise

    if gps['manager'] is not None:
        print("Stopping GPS manager thread")
        gps['manager'].stop()
        time.sleep(0.5)


if __name__ == '__main__':
    run_test()

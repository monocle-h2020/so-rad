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
from initialisation import wind_init
from main_app import parse_args
import functions.config_functions as cf
import serial.tools.list_ports as list_ports

def main(conf):
    print("Start test, initialising")

    ports = list_ports.comports()
    for port, desc, hwid in sorted(ports):
        log.info("port info: {0} {1} {2}".format(port, desc, hwid))

    wind = wind_init(conf['WIND'], ports)
    windman = wind['manager']

    windman.start()

    log.info(wind['serial'])
    log.info("Press CTRL-C to stop test")

    while True:
        try:
            #print(windman.windspeed)
            # Read the response
            time.sleep(1)
            log.info(windman.lastlineread)

        except KeyboardInterrupt:
            log.info("finished test, stopping monitor")
            windman.stop()
            time.sleep(1)
            sys.exit()


def parse_gill_sentence(sentence):
    """
    <STX>Q, 229, 002.74 ,M, 00, <ETX> 16 <CR> <LF>
     ^   ^    ^       ^  ^   ^     ^   ^
     |   |    |       |  |   |     |   |
     |<STX> = Start of string character (ASCII value 2)
         |    |       |  |   |     |   |
         |WindSonic node address = Unit identifier
              |       |  |   |     |   |
              |Wind direction = Wind Direction
                      |  |   |     |   |
                      |Wind speed = Wind Speed
                         |   |     |   |
                         |Units = Units of measure (knots, m/s etc.)
                             |    |    |
                             |Status = Anemometer status code (see Appendix J for further details)
                                  |    |
                                  |<ETX> = End of string character (ASCII value 3)
                                       |
                                       |Checksum = This is the EXCLUSIVE – OR of the bytes between (and not including) the <STX> and <ETX>characters.
       <CR> = ASCII character
       <LF> = ASCII character
    """
    STX = '2'
    ETC = '3'
    #use regex

    return sentence



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


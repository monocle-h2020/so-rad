#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
A simple test to check TriOS Radiometer connectivity.
@author: stsi
"""
import sys
import os
import time
import inspect
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(inspect.getfile(inspect.currentframe())))))
import serial.tools.list_ports as list_ports
from initialisation import rad_init
from main_app import parse_args, read_config
from PyTrios import PyTrios as ps
if not sys.platform.startswith('win'):
    if os.uname()[1] == 'raspberrypi' and os.uname()[4].startswith('arm'):
        import RPi.GPIO as GPIO


def run_test(conf):
    """Test connectivity to TriOS RAMSES radiometer sensors using the routines used in the main application"""
    ports = list_ports.comports()
    for p in ports:
        print(p)
    config = conf['RADIOMETERS']
    rad, Rad_manager = rad_init(config, ports)
    ports = [config['port1'], config['port2'], config['port3']]
    #ports = [config['port1']]

    #ps.tchannels = {}
    #for port in ports:
    #    print("Checking port: {0}".format(port))
    #    try:
    #        c = None
    #        c = ps.TMonitor(port, baudrate=9600)
    #        c[0].verbosity = 3
    #        ps.TCommandSend(c[0], commandset=None, command='query')
    #        time.sleep(5)
    #        c[0].threadlive.clear()   # clear to stop thread
    #        c[0].threadactive.clear()  # clear to pause thread
    #        time.sleep(1)
    #        ps.TClose(c[0])
    #    except Exception as e:
    #        print("Could not connect to port {0}: \n{1}".format(port, e))
    #        pass

    # Start the radiometry manager
    print("Starting radiometry manager")

    radiometry_manager = Rad_manager(rad)
    rad['ed_sampling'] = radiometry_manager.ed_sampling  # if the Ed sensor is not identified, disable this feature

    time.sleep(10)

    print("Stopping radiometry manager threads")
    if radiometry_manager is not None:
        radiometry_manager.stop()

    # switch off gpio
    gpios = []
    if rad['use_gpio_control']:
        print("Switch off GPIO control")
        gpios.append(rad['gpio1'])
        gpios.append(rad['gpio2'])
        gpios.append(rad['gpio3'])
        # Turn all GPIO pins off
        GPIO.output(gpios, GPIO.LOW)
        GPIO.cleanup()

    sys.exit(0)

if __name__ == '__main__':
    args = parse_args()
    conf = read_config(args.config_file)
    run_test(conf)



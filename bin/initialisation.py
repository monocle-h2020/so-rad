#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""

Autonomous operation of hyperspectral radiometers with optional rotating measurement platform, solar power supply and remote connectivity

Routines to initialise GPS, MOTOR, RADIOMETERS and DATABASE

Plymouth Marine Laboratory
License: under development

"""
import time
import serial
import serial.tools.list_ports as list_ports
import sqlite3
import RPi.GPIO as GPIO
import logging
from functions import gps_functions as gps_func
from thread_managers import radiometer_manager
from thread_managers import battery_manager

log = logging.getLogger()   # report to root logger


def db_init(db_config):
    """set up and test sqlite database connection. Return dictionary with database items"""
    db = {}
    # Check db_config to see if db should be used
    db['used'] = db_config.getboolean('use_database')

    # If it is used, check the type of db
    if db['used']:
        try:
            assert db_config.get('database_type') == "sqlite3"
        except AssertionError:
            msg = "database_type {0} not recognized. Only sqlite3 is supported".format(db_config['database_type'])
            log.critical(msg)
            raise AssertionError(msg)

        # Get the db file, connect to it and create a cursor before returning the db dict
        db['file'] = db_config.get('database_file')
        try:
            conn = sqlite3.connect(db['file'])
            cur = conn.cursor()
            conn.close()
        except Exception as err:
            msg = "Error connecting to database: \n {0}".format(err)
            log.critical(msg)
            raise Exception(msg)
    return db


def motor_init(motor_config, ports):
    """read motor configuration. Any other motor initialisation (e.g. test connection, go to home position) should be called here"""
    motor = {}

    # Get all the motor variables from the config file
    motor['used'] = motor_config.getboolean('use_motor')
    #motor['port'] = motor_config.get('port')  # suggest to read from config first, then try to find automatically. If latter fails, we default to the config.
    motor['step_limit'] = motor_config.getint('step_limit')
    motor['step_thresh'] = motor_config.getint('step_thresh_angle')
    motor['cw_limit'] = motor_config.getint('cw_limit_deg')
    motor['ccw_limit'] = motor_config.getint('ccw_limit_deg')
    motor['home_pos'] = motor_config.getint('home_pos')
    motor['step_thresh_time'] = motor_config.getint('step_thresh_time')
    motor['baud'] = motor_config.getint('baud')
    motor['check_angle_every_sec'] = float(motor_config.get('check_angle_every_sec'))
    motor['steps_per_degree'] = float(motor_config.getint('steps_per_degree'))

    # If port autodetect is wanted, look for what port has the identifying string also provided
    if motor_config.getboolean('port_autodetect'):
        port_autodetect_string = motor_config.get('port_autodetect_string')
        for port, desc, hwid in sorted(ports):
            if (desc == port_autodetect_string):
                motor['port'] = port
                log.info("Motor using port: {0}".format(port))
    else:
        assert motor_config.get('port_default').lower() is not None
        motor['port'] = motor_config.get('port_default')

    # Create a serial object for the motor port
    if motor['port'] is not None:
        motor['serial'] = serial.Serial(port=motor['port'],
                                      baudrate=motor['baud'],
                                      timeout=1.0, bytesize=8, parity='E',
                                      stopbits=1, xonxoff=0)
        motor['serial'].reset_input_buffer()
        motor['serial'].reset_output_buffer()
    else:
        raise serial.SerialException('Could not open motor port')

    # Return the motor dict
    return motor


def battery_init(battery_config, ports):
    """
    Read battery monitoring configuration settings and initialise connection to battery.

    : battery_config is the [BATTERY] section in the config file
    : battery is a dictionary containing the configuration
    """
    battery = {}
    # Get all the motor variables from the config file
    battery['used'] = battery_config.getboolean('use_battery')
    battery['interface'] = battery_config.get('battery_protocol')
    battery['baud'] = battery_config.getint('baud')
    battery['battery_low_th_mV'] = battery_config.getint('battery_low_th_V')
    battery['battery_crit_th_mV'] = battery_config.getint('battery_crit_th_V')
    battery['port_autodetect'] = battery_config.getboolean('port_autodetect')
    battery['port_autodetect_string'] = battery_config.get('port_autodetect_string')
    battery['port_default'] = battery_config.get('port_default').lower()

    if not battery['used']:
        return battery, None

    assert battery['interface'] in ['victron',]

    # Return the battery configuration dict and relevant manager class
    if battery['interface'] == 'victron':
        bat_manager = battery_manager.VictronManager(battery, ports)

    return battery, bat_manager


def gps_init(gps_config, ports):
    """read gps configuration. Any other initialisation should also be called here"""
    gps = {}

    # Get all the GPS variables from the config file
    gps['n_gps'] = gps_config.getint('n_gps')
    gps['baud1'] = gps_config.getint('baud1')
    gps['baud2'] = gps_config.getint('baud2')
    gps['set_polling_rate'] = gps_config.getboolean('set_polling_rate')  # True if polling rate can be set?
    gps['polling_rate1'] = gps_config.getint('polling_rate1')
    gps['polling_rate2'] = gps_config.getint('polling_rate2')
    gps['location1'] = gps_config.get('location1').lower()
    gps['location2'] = gps_config.get('location2').lower()
    assert gps['location1'] in ['front', 'rear']
    assert gps['location2'] in ['front', 'rear']
    gps['id1'] = gps_config.get('id1').lower()
    gps['id2'] = gps_config.get('id2').lower()
    gps['heading_speed_limit'] = gps_config.getint('heading_speed_limit')
    gps['gpio2'] = gps_config.getint('gpio2')
    gps['gpio_control'] = gps_config.getboolean('use_gpio_control')

    # If port autodetect is wanted, look for what port has the identifying string also provided
    if gps_config.getboolean('port_autodetect') and gps['gpio_control'] and gps['n_gps'] == 2:
        # this is the recommended situation, one gps will be detected, the second after powering the relay switch
        port_autodetect_string = gps_config.get('port_autodetect_string')
        gps_counter = 0
        ports = list_ports.comports()
        for port, desc, hwid in sorted(ports):
            #print(port, desc, hwid)
            if (desc == port_autodetect_string):
                gps['port1'] = port
                log.info("GPS1 using port: {0}".format(port))
                gps_counter += 1
        if gps_counter != 1:
            err = "Error: {0} gps interfaces detected, expected 1 of {1} to be connected".format(gps_counter, gps['n_gps'])
            raise AssertionError(err)

        # switch gpio pin on for the second GPS
        GPIO.setmode(GPIO.BOARD)
        pin = gps['gpio2']
        GPIO.setup(pin, GPIO.OUT)
        GPIO.output(pin, GPIO.HIGH)

        # Wait for the second GPS to start up
        time.sleep(10)

        # find second GPS using the same identifying string as before
        ports = list_ports.comports()
        for port, desc, hwid in sorted(ports):
            #print(port, desc, hwid)
            if (desc == port_autodetect_string) and port != gps['port1']:
                gps['port2'] = port
                log.info("GPS2 using port: {0}".format(port))
            # else: 
            #     err = "Error: Second GPS not found"
            #     raise AssertionError(err)
    else:
        # Get the known GPS ports from the config file
        gps['port1'] = gps_config.get('port1_default')
        if gps['n_gps'] == 2:
            gps['port2'] = gps_config.get('port2_default')
        if gps['gpio_control']:
            # switch gpio pin on for second GPS sensor
            GPIO.setmode(GPIO.BOARD)
            pin = gps['gpio2']
            GPIO.setup(pin, GPIO.OUT)
            GPIO.output(pin, GPIO.HIGH)
            time.sleep(10)

    time.sleep(1)
    # Create serial objects for both the GPS sensor ports using variables from the config file
    gps['serial1'] = serial.Serial(port=gps['port1'], baudrate=gps['baud1'], timeout=None, bytesize=serial.EIGHTBITS, parity=serial.PARITY_NONE, stopbits=serial.STOPBITS_ONE, xonxoff=False)
    gps['serial2'] = serial.Serial(port=gps['port2'], baudrate=gps['baud2'], timeout=None, bytesize=serial.EIGHTBITS, parity=serial.PARITY_NONE, stopbits=serial.STOPBITS_ONE, xonxoff=False)

    time.sleep(1)
    # If the polling rate is to be changed, send update commands to the GPS sensors
    if gps['set_polling_rate']:
       gps_func.update_gps_rate(gps['serial1'], int(gps['polling_rate1'])) 
       gps_func.update_gps_rate(gps['serial2'], int(gps['polling_rate2']))

    # Return the GPS dict
    return gps


def rad_init(rad_config, ports):
    """read radiometer configuration. Any other initialisation should also be called here"""
    rad = {}
    # Get the radiometry variables from the config file
    rad['n_sensors'] = rad_config.getint('n_sensors')
    rad['rad_interface'] = rad_config.get('rad_interface').lower()
    rad['pytrios_path'] = rad_config.get('pytrios_path')
    rad['port1'] = rad_config.get('port1')
    rad['port2'] = rad_config.get('port2')
    rad['port3'] = rad_config.get('port3')
    rad['sampling_interval'] = rad_config.getint('sampling_interval')
    rad['ed_sampling'] = rad_config.get('ed_sampling')
    rad['ed_sampling_interval'] = rad_config.getint('ed_sampling_interval')
    rad['ed_sensor_id'] = rad_config.get('ed_sensor_id')
    rad['inttime'] = rad_config.getint('integration_time')
    rad['allow_consecutive_timeouts'] = rad_config.getint('allow_consecutive_timeouts')
    rad['minimum_reboot_interval_sec'] = rad_config.getint('minimum_reboot_interval_sec')

    assert rad['rad_interface'] in ['pytrios',]

    # If the sensors are pytrios sensors, get more variables from the config file
    if rad['rad_interface'] == 'pytrios':
        rad['verbosity_chn'] = rad_config.getint('verbosity_chn')
        rad['verbosity_com'] = rad_config.getint('verbosity_com')
        rad['integration_time'] = rad_config.getint('integration_time')

    # If port autodetect is wanted, look for what ports have the identifying string also provided
    if rad_config.getboolean('port_autodetect'):
        rad_ports = []
        port_autodetect_string = rad_config.get('port_autodetect_string')
        for port, desc, hwid in sorted(ports):
            if (desc == port_autodetect_string):
                rad_ports.append(port)
        assert len(rad_ports) == 3
        rad['port1'] = rad_ports[0]
        rad['port2'] = rad_ports[1]
        rad['port3'] = rad_ports[2]
        log.info("Sensors using ports: {0}".format(", ".join(rad_ports)))

    # If GPIO control is wanted, turn on the GPIO pins for the sensors
    # using the pins provided in the config file
    rad['use_gpio_control'] = rad_config.getboolean('use_gpio_control')
    if rad['use_gpio_control']:
        rad['gpio1'] = rad_config.getint('gpio1')
        rad['gpio2'] = rad_config.getint('gpio2')
        rad['gpio3'] = rad_config.getint('gpio3')

        GPIO.setmode(GPIO.BOARD)
        pins = [rad['gpio1'], rad['gpio2'], rad['gpio3']]
        GPIO.setup(pins, GPIO.OUT)
        GPIO.output(pins, GPIO.HIGH)
        time.sleep(1) # Wait to allow sensors to boot

    # Return the radiometry dict and relevant manager class
    if rad['rad_interface'] == 'pytrios':
        Rad_manager = radiometer_manager.TriosManager(rad)

    return rad, Rad_manager


def init_gpio(conf, state=0):
    """set all GPIO pins identified in config file to low (0) or high (1)"""
    set_state = {0: GPIO.LOW, 1: GPIO.HIGH}

    # If GPIO control is wanted, using the pins stated in the config file turn them on/off
    if conf['DEFAULT'].getboolean('use_gpio_control'):
        pins = []
        if conf['GPS'].getboolean('use_gpio_control'):
            pins.append(conf['GPS'].getint('gpio2'))
        if conf['RADIOMETERS'].getboolean('use_gpio_control'):
            pins.append(conf['RADIOMETERS'].getint('gpio1'))
            pins.append(conf['RADIOMETERS'].getint('gpio2'))
            pins.append(conf['RADIOMETERS'].getint('gpio3'))
        GPIO.setmode(GPIO.BOARD)
        GPIO.setup(pins, GPIO.OUT)
        GPIO.output(pins, set_state[state])
        GPIO.cleanup()


def sample_init(sample_conf):
    """Reads the sampling settings from the config file

    :param conf: the config file dictionary
    :type conf: dict
    """
    sample = {}

    # Get the sampling variables from the config file
    sample['sampling_speed_limit'] = float(sample_conf.get('sampling_speed_limit'))
    sample['solar_elevation_limit'] = float(sample_conf.get('solar_elevation_limit'))

    # Return the sample dict
    return sample

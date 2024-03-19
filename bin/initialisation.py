#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""

Autonomous operation of hyperspectral radiometers with optional rotating measurement platform, solar power supply and remote connectivity

Routines to initialise GPS, MOTOR, RADIOMETERS and DATABASE

Plymouth Marine Laboratory
License: under development

"""
import os
import sys
import time
import serial
import serial.tools.list_ports as list_ports
import logging
from functions import gps_functions as gps_func
from thread_managers import radiometer_manager
from thread_managers import battery_manager
from thread_managers import tpr_manager
from thread_managers import gps_manager
from thread_managers import rht_manager
from thread_managers import gpio_manager
from functions import db_functions
log = logging.getLogger('init')   # report to root logger


def db_init(db_config):
    """set up and test sqlite database connection. Return dictionary with database items"""
    db = {}
    # Check db_config to see if db should be used
    db['used'] = db_config.getboolean('use_database')

    # If it is used, check the type of db
    if not db['used']:
        return db
    else:
        try:
            assert db_config.get('database_type') == "sqlite3"
        except AssertionError:
            msg = "database_type {0} not recognized. Only sqlite3 is supported".format(db_config['database_type'])
            log.critical(msg)
            raise AssertionError(msg)

    # Create tables (only if necessary)
    db['file'] = db_config.get('database_path')
    try:
        db_functions.create_tables(db)  # won't harm existing tables

        conn, cur = db_functions.connect_db(db)
        header_meta = db_functions.column_names(conn, cur, table="sorad_metadata")
        header_rad = db_functions.column_names(conn, cur, table="sorad_radiometry")
        db['header_meta'] = header_meta
        db['header'] = header_rad + header_meta
        conn.close()
    except Exception as err:
        msg = "Error connecting to database: \n {0}".format(err)
        log.critical(msg)
        conn.close()
        raise Exception(msg)

    # cater for a few older database styles
    if 'sos_inserted' in header_meta:
        log.debug("Database format < June 2021")
        db['export_success_field']  = 'sos_inserted'
        db['export_attempts_field'] = 'sos_insertion_attempts'
    elif 'export_success' in header_meta:
        log.debug("Database format > June 2021")
        db['export_success_field']  = 'export_success'
        db['export_attempts_field'] = 'export_attempts'
    else:
        log.critical("database format not recognized")

    # location info may also have changed with different versions
    if 'gps_lat' in header_meta:
        db['gps_fields'] = 'gps_'
    elif 'gps1_lat' in header_meta:
        db['gps_fields'] = 'gps1_'
    else:
        log.critical("gps fields not recognised in database")

    # if the sample_uuid is not stored on data collection, set switch to add it on upload
    db['add_sample_uuid'] = 'sample_uuid' not in db['header']

    return db


def motor_init(motor_config, ports):
    """read motor configuration. Any other motor initialisation (e.g. test connection, go to home position) should be called here"""
    motor = {}

    # Get all the motor variables from the config file
    motor['used'] = motor_config.getboolean('use_motor')
    motor['step_thresh'] = motor_config.getint('step_thresh_angle')
    motor['cw_limit'] = motor_config.getint('cw_limit_deg')
    motor['ccw_limit'] = motor_config.getint('ccw_limit_deg')
    motor['home_pos'] = motor_config.getint('home_pos')
    motor['step_thresh_time'] = motor_config.getfloat('step_thresh_time')
    motor['baud'] = motor_config.getint('baud')
    motor['steps_per_degree'] = float(motor_config.get('steps_per_degree'))
    motor['adjust_mode'] = motor_config.get('adjust_mode').lower()
    assert motor['adjust_mode'] in ['sampling', 'always']

    if not motor['used']:
        return motor

    # If port autodetect is set look for what port has the matching identification string
    log.info("connecting to motor.. autodetect={0}".format(motor_config.getboolean('port_autodetect')))

    if motor_config.getboolean('port_autodetect'):
        port_autodetect_string = motor_config.get('port_autodetect_string')
        for port, desc, hwid in sorted(ports):
            log.info("port info: {0} {1} {2}".format(port, desc, hwid))
            if port_autodetect_string in port+desc+hwid:
                motor['port'] = port
                log.info("Motor auto-detected on port: {0}".format(port))
    else:
        assert motor_config.get('port_default') not in [None, 'none', 'None']
        motor['port'] = motor_config.get('port_default')
        log.info("Motor manually set to port: {0}".format(motor['port']))

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
    battery['battery_low_th_V'] = float(battery_config.get('battery_low_th_V'))
    battery['battery_crit_th_V'] = float(battery_config.get('battery_crit_th_V'))
    battery['port_autodetect'] = battery_config.getboolean('port_autodetect')
    battery['port_autodetect_string'] = battery_config.get('port_autodetect_string')
    battery['port_default'] = battery_config.get('port_default').lower()

    if not battery['used']:
        return battery, None

    assert battery['interface'] in ['victron',]

    # Return the battery configuration dict and relevant manager class
    if battery['interface'].lower() == 'victron':
        bat_manager = battery_manager.VictronManager(battery, ports)

    return battery, bat_manager


def power_schedule_init(power_schedule_config):
    """
    Read power scheduling configuration settings.

    : power_schedule_config is the [POWER_SCHEDULE] section in the config file
    : power_schedule is a dictionary containing the configuration
    """
    power_schedule = {}
    # Get all the motor variables from the config file
    power_schedule['used'] = power_schedule_config.getboolean('use_power_schedule')
    power_schedule['mode'] = power_schedule_config.get('schedule_mode')
    power_schedule['use_gpio_control'] = power_schedule_config.getboolean('use_gpio_control')

    if not power_schedule['used']:
        return power_schedule

    if power_schedule['use_gpio_control']:
        power_schedule['gpio_protocol'] = power_schedule_config.get('gpio_protocol')
        assert power_schedule['gpio_protocol'] in  ['rpi', 'gpiozero']
        if power_schedule['gpio_protocol'] == 'rpi':
            power_schedule['gpio_interface'] = gpio_manager.RpiManager()       # select manager and initialise
        elif power_schedule['gpio_protocol'] == 'gpiozero':
            power_schedule['gpio_interface'] = gpio_manager.GpiozeroManager()  # select manager and initialise

        power_schedule['power_schedule_gpio1'] = power_schedule_config.getint('power_schedule_gpio1')
        power_schedule['gpio_interface'].on(power_schedule['power_schedule_gpio1'])
        time.sleep(1)

    return power_schedule


def tpr_init(tpr_config):
    """
    Read Tilt/Pitch/Roll monitoring config settings and initialise TPR connection and monitor

    : tpr_config is the [TPR] section in the config file
    : tpr is a dictionary containing the configuration 
    """
    tpr = {}
    # Get all the TPR variables from the config file
    tpr['used'] = tpr_config.getboolean('use_tpr')
    tpr['interface'] = tpr_config.get('protocol').lower()
    tpr['sampling_time'] = tpr_config.getfloat('sampling_time')
    tpr['xindex'] = tpr_config.getint('xindex')
    tpr['yindex'] = tpr_config.getint('yindex')
    tpr['zindex'] = tpr_config.getint('zindex')
    tpr['manager'] = None

    if not tpr['used']:
        return tpr

    assert tpr['interface'].lower() in ['ada_adxl345', ]

    # Return the configuration dict and initialise relevant manager class
    if tpr['interface'] == 'ada_adxl345':
        tpr['manager'] = tpr_manager.Ada_adxl345(tpr)

    return tpr


def rht_init(rht_config):
    """
    Read Relative Humidity and Temperature monitoring config settings and initialise RHT connection and monitor
    : rht_config is the [RHT] section in the config file
    : rht is a dictionary containing the configuration and manager
    """
    rht = {}
    # Get all the TPR variables from the config file
    rht['used'] = rht_config.getboolean('use_rht')
    rht['interface'] = rht_config.get('protocol').lower()
    rht['pin'] = rht_config.getint('pin')
    rht['sampling_time'] = rht_config.getint('sampling_time')
    rht['manager'] = None

    if not rht['used']:
        log.info(f"RHT sensor disabled in config")
        return rht

    assert rht['interface'].lower() in ['ada_dht22', 'ada_cp_dht']

    # Return the configuration dict and initialise relevant manager class
    if rht['interface'] in ['ada_dht22', 'ada_cp_dht']:
        rht['manager'] = rht_manager.Ada_dht22(rht)

    return rht


def gps_init(gps_config, ports):
    """read gps configuration. Any other initialisation should also be called here"""
    gps = {}
    gps['protocol'] = gps_config.get('protocol').lower()
    # Get all the GPS variables from the config file
    gps['baud1'] = gps_config.getint('baud1')
    gps['id1'] = gps_config.get('id1').lower()
    gps['heading_speed_limit'] = gps_config.getfloat('gps_heading_speed_limit')
    gps['heading_accuracy_limit'] = gps_config.getfloat('gps_heading_accuracy_limit')
    gps['port1'] = None
    gps['gps_heading_correction'] = gps_config.getfloat('gps_heading_correction')

    if gps['protocol'] in ['rtk', 'pyubx2']:
        # heading will be determined from distance between receivers rather than movement, so we need to know which one is nearer the front of the ship
       gps['location1'] = gps_config.get('location1').lower()
       gps['location2'] = gps_config.get('location2').lower()
       assert gps['location1'] in ['front', 'rear']
       assert gps['location2'] in ['front', 'rear']

    # If port autodetect is selected look for what port has the identifying string also provided
    port_autodetect_string = gps_config.get('port_autodetect_string')
    ports = list_ports.comports()
    for port, desc, hwid in sorted(ports):
        if (port_autodetect_string in port+desc+hwid) and (gps_config.getboolean('port_autodetect')):
            gps['port1'] = port
            log.info("GPS1 using port: {0}".format(port))
    if gps['port1'] is None:
        # Set the port from the config file
        log.info("Defaulting to GPS port settings in config file")
        gps['port1'] = gps_config.get('port1_default')

    # Create serial objects for the GPS sensor port using variables from the config file
    gps['serial1'] = serial.Serial(port=gps['port1'], baudrate=gps['baud1'], timeout=0.5, bytesize=serial.EIGHTBITS, parity=serial.PARITY_NONE, stopbits=serial.STOPBITS_ONE, xonxoff=False)

    # assign the relevant gps manager class
    if gps['protocol'] == 'rtk':
       gps['manager'] = gps_manager.RTKUBX()
    elif gps['protocol'] == 'nmea0183':
       gps['manager'] = gps_manager.NMEA0183()
    elif gps['protocol'] == 'pyubx2':
       gps['manager'] = gps_manager.PYUBX2()
    else:
       log.exception("GPS protocol '{0}' is not implemented".format(gps['protocol']))

    return gps


def rad_init(rad_config, ports):
    """read radiometer configuration. Any other initialisation should also be called here"""
    rad = {}
    # Get the radiometry variables from the config file
    rad['n_sensors'] = rad_config.getint('n_sensors')
    rad['rad_interface'] = rad_config.get('rad_interface').lower()
    rad['pytrios_path'] = rad_config.get('pytrios_path')
    #rad['port1'] = rad_config.get('port1')
    #rad['port2'] = rad_config.get('port2')
    #rad['port3'] = rad_config.get('port3')
    rad['sampling_interval'] = rad_config.getint('sampling_interval')
    rad['ed_sampling'] = rad_config.getboolean('ed_sampling')
    rad['ed_sampling_interval'] = rad_config.getint('ed_sampling_interval')
    rad['ed_sensor_id'] = rad_config.get('ed_sensor_id')
    rad['ed_sampling_min_solar_elevation_deg'] = rad_config.getint('ed_sampling_min_solar_elevation_deg')
    rad['inttime'] = rad_config.getint('integration_time')
    rad['allow_consecutive_timeouts'] = rad_config.getint('allow_consecutive_timeouts')
    rad['minimum_reboot_interval_sec'] = rad_config.getint('minimum_reboot_interval_sec')

    if rad['n_sensors'] == 0:
        log.info("Radiometers not used. Update config file setting n_sensors to change this.")
        return rad, None

    assert rad['rad_interface'] in ['pytrios','pytrios_g2']

    # If the interface is pytrios set more variables from the config file
    if rad['rad_interface'] == 'pytrios':
        rad['verbosity_chn'] = rad_config.getint('verbosity_chn')
        rad['verbosity_com'] = rad_config.getint('verbosity_com')
        rad['integration_time'] = rad_config.getint('integration_time')

    # If port autodetect is selected look for ports with identifying strings
    # Note that no sensor communication takes place here yet, this is only looking for the serial to usb interfaces
    if rad_config.getboolean('port_autodetect'):
        rad['ports'] = []
        port_autodetect_strings = rad_config.get('port_autodetect_string').split(',')
        for autodetect_string in port_autodetect_strings:
            found = False
            for port, desc, hwid in sorted(ports):
                if autodetect_string in port+desc+hwid:
                    rad['ports'].append(port)
                    found = True
            if not found:
                log.warning(f"Radiometer identifier {autodetect_string} not found on any port")
        if len(rad['ports']) < rad['n_sensors']:
            log.critical(f"{len(rad['ports'])} identified out of {rad['n_sensors']} expected.")

        for i, p in enumerate(rad['ports']):
            rad[f'port{i+1}'] = p
        log.info("Radiometers configured on ports: {0}".format(", ".join(rad['ports'])))


    # If GPIO control is selected turn on the GPIO pin for the radiometers
    # using the pin info provided in the config file
    rad['use_gpio_control'] = rad_config.getboolean('use_gpio_control')
    if rad['use_gpio_control']:
        rad['gpio_protocol'] = rad_config.get('gpio_protocol')
        assert rad['gpio_protocol'] in  ['rpi', 'gpiozero']
        if rad['gpio_protocol'] == 'rpi':
            rad['gpio_interface'] = gpio_manager.RpiManager()       # select manager and initialise
        elif rad['gpio_protocol'] == 'gpiozero':
            rad['gpio_interface'] = gpio_manager.GpiozeroManager()  # select manager and initialise

        rad['gpio1'] = rad_config.getint('gpio1')
        rad['gpio_interface'].on(rad['gpio1'])
        time.sleep(5) # Wait to allow sensors to boot

    # Return the radiometry dict and relevant manager class
    if rad['rad_interface'] == 'pytrios':
        Rad_manager = radiometer_manager.TriosManager
    elif rad['rad_interface'] == 'pytrios_g2':
        Rad_manager = radiometer_manager.TriosG2Manager

    return rad, Rad_manager


def init_gpio(conf, rad, state=0):
    """set all GPIO pins identified in config file to low (0) or high (1)"""

    # If GPIO control is requested use the pins stated in the config file
    if conf['DEFAULT'].getboolean('use_gpio_control'):
        pins = []
        if rad['use_gpio_control']:
            pins.append(rad['gpio1'])
        if state == 0:
            for pin in pins:
                rad['gpio_interface'].off(pin)
        elif state == 1:
            for pin in pins:
                rad['gpio_interface'].on(pin)


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

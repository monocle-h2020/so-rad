#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""

Autonomous operation of hyperspectral radiometers with optional rotating measurement platform, solar power supply and remote connectivity

Plymouth Marine Laboratory

License: under development

"""
import time
import serial.tools.list_ports as list_ports
import threading
import os
import sys
import datetime
import RPi.GPIO as GPIO
import configparser
import argparse
import initialisation
import logging
import logging.handlers
import functions.motor_controller_functions as motor_func
import functions.db_functions as db_func
import functions.gps_functions as gps_func
import functions.azimuth_functions as azi_func
from functions.check_functions import check_gps, check_motor, check_sensors, check_sun, check_battery, check_speed
#from thread_managers.gps_manager import GPSManager
from thread_managers.gps_checker import GPSChecker

def parse_args():
    """parse command line arguments"""
    parser = argparse.ArgumentParser()
    parser.add_argument('-c', '--config_file', required=True,
                        help="config file providing programme settings",
                        default=u"config.ini")
    parser.add_argument("--verbose", "-v", type=int, choices=[0, 1, 2, 3, 4],
                         help="set verbosity on output", default=3)
    args = parser.parse_args()

    if not os.path.exists(args.config_file):
        raise IOError("Config file not found at {0}".format(args.config_file))

    return args


def read_config(config_file):
    """Opens and reads the config file

    :param config_file: the config.ini file
    :type config_file: file
    :return: dictionary of the config file's contents
    :rtype: dictionary
    """
    config = configparser.ConfigParser()
    config.read(config_file)
    return config


def init_logger(conf_log_dict):
    """Initialises the root logger for the program

    :param conf_log_dict: dictionary containing the logger config information
    :type conf_log_dict: dictionary
    :return: log
    :rtype: logger
    """
    myFormat = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    formatter = logging.Formatter(myFormat)
    log_filename = conf_log_dict['log_file_location']
    if not os.path.isdir(os.path.dirname(log_filename)):
        os.makedirs(os.path.dirname(log_filename))

    console_log_level = conf_log_dict['console_log_level'].upper()

    logging.basicConfig(level=console_log_level, format=myFormat, stream=sys.stdout)

    # create file handler
    maxBytes = 2 * 1024 ** 2 # 100MB
    filehandler = logging.handlers.RotatingFileHandler(log_filename, mode='a',
                                                       maxBytes=maxBytes,
                                                       backupCount=10)
    # set the logger verbosity
    filehandler.setFormatter(formatter)
    filehandler.setLevel(console_log_level)

    # add the handlers to the root logger
    log = logging.getLogger()
    log.addHandler(filehandler)
    #logging.getLogger().addHandler(filehandler)
    return log


def init_all(conf):
    """Initialise all components"""

    log = logging.getLogger()

    db = initialisation.db_init(conf['DATABASE'])
    initialisation.init_gpio(conf, state=0)  # set all used pins to LOW

    # Get all comports and collect the initialisation dicts
    ports = list_ports.comports()
    motor = initialisation.motor_init(conf['MOTOR'], ports)


    GPSData = conf['GPS']
    if(GPSData.get('protocol').lower() == "rtk"):
        from thread_managers.gps_manager import RTKUBX as GPSManager
        gps = initialisation.gps_rtk_init(conf['GPS'])
    else:
        from thread_managers.gps_manager import NMEA0183 as GPSManager
        gps = initialisation.gps_init(conf['GPS'], ports)


    rad, Rad_manager = initialisation.rad_init(conf['RADIOMETERS'], ports)
    sample = initialisation.sample_init(conf['SAMPLING'])
    battery, bat_manager = initialisation.battery_init(conf['BATTERY'], ports)

    # start the battery manager
    if battery['used']:
        bat_manager.start()
        time.sleep(0.1)

    # collect info on which GPIO pins are being used
    gpios = []
    if gps['gpio_control']:
        gpios.append(gps['gpio2'])
    if rad['use_gpio_control']:
        gpios.append(rad['gpio1'])
        gpios.append(rad['gpio2'])
        gpios.append(rad['gpio3'])

    # Get the GPS serial objects from the GPS dict
    gps_ports = [port for key, port in gps.items() if 'serial' in key]
    # Instantiate GPS monitoring threads
    if len(gps_ports) > 0:
        gps_managers = []

        # if(len(gps_ports) == 1):
        #     print("send to rtk")
        # else:

        for port in gps_ports:
            gps_manager = GPSManager()
            gps_manager.add_serial_port(port)
            gps_manager.start()
            gps_managers.append(gps_manager)
    else:
        log.info("Check GPS sensors and Motor connection settings")
    time.sleep(0.1)

    # # Start the GPS checker thread
    # gps_checker_manager = GPSChecker(gps_managers)
    # gps_checker_manager.start()

    # Get the current motor pos and if not at HOME move it to HOME
    motor_pos = motor_func.get_motor_pos(motor['serial'])
    if motor_pos != motor['home_pos']:
        t0 = time.clock()
        log.info("Homing motor.. {0} --> {1}".format(motor_pos, motor['home_pos']))
        motor_func.return_home(motor['serial'])  # FIXME replace with rotate function to home pos as set in config
        moving = True
        while moving and (time.clock()-t0<5):
            moving = motor_func.motor_moving(motor['serial'], motor['home_pos'], tolerance=300)[0]
            if moving is None:
                moving = True  # assume we are not done
            log.info("..homing motor..")
            time.sleep(1)
        log.info("..done")
    else:
        log.info("Motor in home position")
    time.sleep(0.1)

    # Start the radiometry manager
    log.info("Starting radiometry manager")
    radiometry_manager = Rad_manager(rad)
    time.sleep(0.1)

    # Return all the dicts and manager objects
    return db, rad, sample, gps_managers, radiometry_manager, motor, battery, bat_manager, gpios


def stop_all(db, radiometry_manager, gps_managers, battery, bat_manager, gpios, idle_time=0):
    """stop all processes in case of an exception"""
    log = logging.getLogger()

    # Stop the GPS checker manager
    log.info("Stopping dual-gps monitor thread")
    #gps_checker_manager.stop()

    # Stop the radiometry manager
    log.info("Stopping radiometry manager threads")
    radiometry_manager.stop()

    # Stop the GPS managers
    for gps_manager in gps_managers:
        log.info("Stopping GPS manager thread")
        gps_manager.stop()
        time.sleep(0.5)

    # Stop the battery manager
    if battery['used']:
        log.info("Stopping battery manager thread")
        bat_manager.stop()

    # Turn all GPIO pins off
    GPIO.output(gpios, GPIO.LOW)
    GPIO.cleanup()

    # Close any lingering threads
    while len(threading.enumerate()) > 1:
        for t in threading.enumerate()[1:]:
            log.info(t.ident)
            t.join()
        log.info("active threads = {}".format(threading.active_count()))
        time.sleep(0.5)

    # Exit the program
    log.info("Idling {0} s before shutdown".format(idle_time))
    time.sleep(idle_time)
    sys.exit(0)


def run():
    """ main program loop.
    Reads config file to set up environment then starts various threads to monitor inputs.
    Monitors for a keyboard interrupt to provide a clean exit where possible.
    """

    # Add protocol type for GPS section in config file to identify which one the user wants.


    # Parse the command line arguments for the config file
    args = parse_args()
    conf = read_config(args.config_file)

    # start logging here
    log = init_logger(conf['LOGGING'])
    #log = logging.getLogger()
    log.info('\n===Started logging===\n')

    try:
        # Initialise everything
        db_dict, rad, sample, gps_managers, radiometry_manager,\
            motor, battery, bat_manager, gpios = init_all(conf)
    except Exception:
        log.exception("Exception during initialisation")
        stop_all(db_dict, radiometry_manager, gps_managers,
                battery, bat_manager, gpios)
        raise
    log.info("===Initialisation complete===")

    last_commit_time = datetime.datetime.now()
    trigger_id = None
    spec_data = ""
    ship_bearing_mean = None
    solar_az = None
    solar_el = None

    # Check if the program is using a fixed bearing or calculated one
    if conf['DEFAULT']['use_fixed_bearing'].lower() == 'true':
        ship_bearing_mean = conf['DEFAULT'].getint('fixed_bearing_deg')
        bearing_fixed = True
    else:
        bearing_fixed = False

    checks = {True: "1", False: "0"}
    # Repeat indefinitely until program closed
    counter = 0
    while True:
        counter += 1
        message = "[{0}] ".format(counter)
        try:
            # Check battery charge
            if battery['used']:
                if check_battery(bat_manager, battery) == 1:  # 0 = OK, 1 = LOW, 2 = CRITICAL
                    message += "Battery low, idling. Battery info: {0}".format(bat_manager)
                    log.info(message)
                    time.sleep(conf['DEFAULT'].getint('main_check_cycle_sec'))
                    continue
                elif check_battery(bat_manager, battery) == 2:  # 0 = OK, 1 = LOW, 2 = CRITICAL
                    message += "Battery level CRITICAL, shutting down. Battery info: {0}".format(bat_manager)
                    log.info(message)
                    stop_all(db_dict, radiometry_manager, gps_managers, battery, bat_manager, gpios, idle_time=1800)
                else:
                    message += "Bat {0}, ".format(bat_manager.batt_voltage)

            # reset to default
            speed_ready = False
            motor_ready = False
            sun_suitable = False
            rad_ready = False

            # Check if the GPS sensors have met conditions
            gps_ready = check_gps(gps_managers)
            message += "GPS {0}, ".format(checks[gps_ready])

            # Check if the radiometers have met conditions
            rad_ready = check_sensors(rad, trigger_id, radiometry_manager)
            message += "Rad {0}, ".format(checks[rad_ready])

            if gps_ready:
                # read latest gps info and calculate angles for motor
                speed = gps_managers[0].speed
                nsat0 = gps_managers[0].satellite_number
                if(len(gps_managers) == 2):
                    nsat1 = gps_managers[1].satellite_number

                speed_ready = check_speed(sample, gps_managers)
                message += "Speed {0}, ".format(checks[speed_ready])

                # Get the current motor pos to check if it's ready
                motor_pos = motor_func.get_motor_pos(motor['serial'])
                if motor_pos is None:
                    message += "Motor position not read. NotReady: {0}".format(datetime.datetime.now())
                    log.info(message)
                    time.sleep(conf['DEFAULT'].getint('main_check_cycle_sec'))
                    continue

                # # If bearing not fixed, fetch the calculated mean bearing using data from two GPS sensors
                # if not bearing_fixed:
                #     ship_bearing_mean = gps_checker_manager.mean_bearing

                lat0 = gps_managers[0].lat
                lon0 = gps_managers[0].lon
                alt0 = gps_managers[0].alt
                dt = gps_managers[0].datetime
                #dt1 = gps_managers[1].datetime

                # Fetch sun variables
                solar_az, solar_el, motor_angles = azi_func.calculate_positions(lat0, lon0, alt0, dt,
                                                                                ship_bearing_mean, motor, motor_pos)
                log.info("[{8}] Sun Az {0:1.0f} | El {1:1.0f} | ViewAz [{2:1.1f}|{3:1.1f}] | MotPos [{4:1.1f}|{5:1.1f}] | MotTarget {6:1.1f} ({7:1.1f})"\
                         .format(solar_az, solar_el, motor_angles['view_comp_ccw'], motor_angles['view_comp_cw'],
                                 motor_angles['ach_mot_ccw'], motor_angles['ach_mot_cw'],
                                 motor_angles['target_motor_pos_deg'], motor_angles['target_motor_pos_rel_az_deg'], counter))

                message += "ShBe: {0:1.0f}, SuAz: {1:1.0f}, SuEl: {2:1.1f}. Speed {3:1.1f} nSat [{4}|{5}] "\
                           .format(ship_bearing_mean, solar_az, solar_el, speed, nsat0, nsat1)
                # Check if the sun is in a suitable position
                sun_suitable = check_sun(sample, solar_az, solar_el)

                # If the sun is in a suitable position and the motor is not at the required position, move the motor, unless speed criterion is not met
                if (sun_suitable and (abs(motor_angles['target_motor_pos_step'] - motor_pos) > motor['step_thresh'])) and speed_ready:
                    log.info("Adjust motor angle ({0} --> {1})".format(motor_pos, motor_angles['target_motor_pos_step']))
                    # Rotate the motor to the new position
                    target_pos = motor_angles['target_motor_pos_step']
                    motor_func.rotate_motor(motor_func.commands, target_pos, motor['serial'])
                    moving = True
                    t0 = time.clock()  # timeout reference
                    while moving and time.clock()-t0 < 5:
                        moving, motor_pos = motor_func.motor_moving(motor['serial'], target_pos, tolerance=300)
                        if moving is None:
                            moving = True
                        log.info("..moving motor.. {0} --> {1}".format(motor_pos, target_pos))
                        time.sleep(2)

            else:
                message += "ShBe: None, SuAz: None, SuEl: None, Speed: None. "
                sun_suitable = False


            # If all checks are good, take radiometry measurements
            if all([gps_ready, rad_ready, sun_suitable, speed_ready]):
                # Get the current time of the computer and data from the GPS sensor managers
                trigger_id = datetime.datetime.now()
                gps1_manager_dict = gps_func.create_gps_dict(gps_managers[0])
                gps2_manager_dict = gps_func.create_gps_dict(gps_managers[1])

                # Collect radiometry data and splice together
                trig_id, specs, sids, itimes = radiometry_manager.sample_all(trigger_id)
                spec_data = []
                for n in range(len(sids)):
                    spec_data.append([str(sids[n]),str(itimes[n]),str(specs[n])])

                # If db is used, commit the data to it
                if db_dict['used']:
                    db_id = db_func.commit_db(db_dict, args.verbose, gps1_manager_dict, gps2_manager_dict,
                                              trigger_id, ship_bearing_mean, solar_az, solar_el, spec_data)
                    last_commit_time = datetime.datetime.now()
                    message += "Trig: {0} [{1}]".format(trigger_id, db_id)

            # If not enough time has passed since the last measurement, wait
            elif abs(datetime.datetime.now().timestamp() - last_commit_time.timestamp()) < 60:
                # do not execute measurement, do not record metadata
                message += "Not Ready"

            else:
                # record metadata and GPS data if some checks aren't passed
                gps1_manager_dict = gps_func.create_gps_dict(gps_managers[0])
                gps2_manager_dict = gps_func.create_gps_dict(gps_managers[1])

                no_trigger_id = datetime.datetime.now()
                spec_data = None

                if db_dict['used']:
                    db_id = db_func.commit_db(db_dict, args.verbose, gps1_manager_dict, gps2_manager_dict,
                                              no_trigger_id, ship_bearing_mean, solar_az, solar_el, spec_data)
                    last_commit_time = datetime.datetime.now()
                    message += "NotReady | GPS Recorded: {0} [{1}]".format(last_commit_time, db_id)

            log.info(message)
            time.sleep(conf['DEFAULT'].getint('main_check_cycle_sec'))

        except KeyboardInterrupt:
            log.info("Program interrupted, attempt to close all threads")
            stop_all(db_dict, radiometry_manager, gps_managers, battery, bat_manager, gpios)
        except Exception:
            log.exception("Unhandled Exception")
            stop_all(db_dict, radiometry_manager, gps_managers, battery, bat_manager, gpios)
            raise

if __name__ == '__main__':
    run()

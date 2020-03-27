#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""

Autonomous operation of hyperspectral radiometers with optional rotating measurement platform, solar power supply and remote connectivity

Plymouth Marine Laboratory

License: under development, please contact stsi at pml*ac*uk

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
from functions.check_functions import check_gps, check_motor, check_sensors, check_sun, check_battery, check_speed, check_heading, check_pi_cpu_temperature
#from thread_managers.gps_manager import GPSManager
from thread_managers.gps_checker import GPSChecker
from numpy import nan, nanmax


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

    if Rad_manager is not None and rad['use_gpio_control']:
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
    if Rad_manager is not None:
        radiometry_manager = Rad_manager(rad)
        time.sleep(0.1)
    else:
        radiometry_manager = None

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
    if radiometry_manager is not None:
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

def update_gps_values(gps_managers):
    """update the gps values to the latest available in the gps managers""" 
    values['lat0'] = gps_managers[0].lat
    values['lon0'] = gps_managers[0].lon
    values['alt0'] = gps_managers[0].alt
    values['dt'] = gps_managers[0].datetime
    values['headMot'] = gps_managers[0].headMot
    values['relPosHeading'] = gps_managers[0].relPosHeading
    values['accHeading'] = gps_managers[0].accHeading
    values['fix'] = gps_managers[0].fix
    values['flags_headVehValid'] = gps_managers[0].flags_headVehValid
    values['flags_diffSoln'] = gps_managers[0].flags_diffSoln
    values['flags_gnssFixOK'] = gps_managers[0].flags_gnssFixOK
    if len(gps_managers) == 2:
        values['dt1'] = gps_managers[1].datetime

    return values


def format_log_message(counter, ready, values):
    """construct a log message based on several system checks"""
    checks = {True: "1", False: "0"}    # values to show for True/False (e.g. 1/0 or T/F)
    message = "[{0}] ".format(counter)
    message += "Checks:  Bat {0} Pos {1} Head {2} Rad {3} Speed {4} ({5}) Sun {6} ({7})"\
               .format(values['batt_voltage'], checks[ready['gps']],
                       checks[ready['heading']], checks[ready['rad']],
                       checks[ready['speed']], values['speed'],
                       checks[ready['sun']], values['solar_el'])
    message += "\n"
    message += "[{10}] Heading: Sun {0} Mot {1} Veh {2} Acc: {3}) | fix: {4}, HeadOk: {5}, diffSolnOk: {6}, FixOk {7} | nSat [{8}|{9}] "\
                .format(valus['solar_az'], values['headMot'], values['relPosHeading'],
                        values['accHeading'], values['fix'], values['flags_headVehValid'],
                        values['flags_diffSoln'], values['flags_gnssFixOK'], values['nsat0'], values['nsat1'], counter)

    return message


def run_one_cycle(counter, conf, db_dict, rad, sample, gps_managers, radiometry_manager,
                  motor, battery, bat_manager, gpios, trigger_id, verbose):
    """run one measurement cycle
    
    : counter               - measurement cycle number, included for logging
    : conf                  - main configuration (parsed from file)
    : sample                - main sampling settings configuration
    : bat_manager           - battery manager instance
    : gps_managers          - list of gps manager instances
    : radiometry_manager    - radiometry manager instance
    : rad                   - radiometry configuration
    : battery               - battery management configuration
    : motor                 - motor configuration
    : pgios                 - gpio pins in use
    
    returns:
    : trigger_id            - identifier of the last measurement (a datetime object)
    """

    # init dicts for all environment checks and latest sensor values
    ready = {'speed': False, 'motor': False, 'sun': False, 'rad': False, 'heading': False, 'gps': False}
    values = {'speed': None, 'nsat0': None, 'nsat1': None, 'motor_pos': None, 'ship_bearing_mean': None,
              'solar_az': None, 'solar_el': None, 'motor_angles': None,
              'lat0': None, 'lon0': None, 'alt0': None, 'dt': None, 'dt1': None, 'nsat0': None, 'nsat1': None,
              'headMot': None, 'relPosHeading': None, 'accHeading': None, 'fix': None,
              'flags_headVehValid': None, 'flags_diffSoln': None, 'flags_gnssFixOK': None}

    use_rad = rad['n_sensors'] > 0

    # Check whether platform bearing is fixed (set in config) or calculated from GPS
    if conf['DEFAULT']['use_fixed_bearing'].lower() == 'true':
        ship_bearing_mean = conf['DEFAULT'].getint('fixed_bearing_deg')
        bearing_fixed = True
    else:
        bearing_fixed = False

    # Check battery charge - log special messages if required.
    if battery['used']:
        if check_battery(bat_manager, battery) == 1:  # 0 = OK, 1 = LOW, 2 = CRITICAL
            message = format_log_message(counter, ready, values)
            message += "Battery low, idling. Battery info: {1}".format(counter, bat_manager)
            log.warning(message)
            return trigger_id  # always return last trigger id
        elif check_battery(bat_manager, battery) == 2:  # 0 = OK, 1 = LOW, 2 = CRITICAL
            message = format_log_message(counter, ready, values)
            message += "Battery level critical, shutting down. Battery info: {0}".format(counter, bat_manager)
            log.warning(message)
            stop_all(db_dict, radiometry_manager, gps_managers, battery, bat_manager, gpios, idle_time=1800)  # calls sys.exit after pausing for idle_time to prevent immediate restart
            sys.exit(1)                                                                                       # just in case it didn't do that.

    # Check GPS environment
    gps_heading_accuracy_limit = conf['GPS'].getfloat('gps_heading_accuracy_limit')
    gps_protocol = conf['GPS'].get('protocol').lower()
    ready['gps']  = check_gps(gps_managers, gps_protocol)
    ready['heading'] = check_heading(gps_managers, gps_heading_accuracy_limit, gps_protocol)
    # Check radiometry environment
    ready['rad'] = check_sensors(rad, trigger_id, radiometry_manager)

    if ready['gps']:
        # read latest gps info and calculate angles for motor
        values['speed'] = gps_managers[0].speed
        values['nsat0'] = gps_managers[0].satellite_number
        if len(gps_managers) == 2:
            values['nsat1'] = gps_managers[1].satellite_number
        # time.sleep(2)  # not needed?
        ready['speed'] = check_speed(sample, gps_managers)

        # read motor position to see if it is ready
        values['motor_pos'] = motor_func.get_motor_pos(motor['serial'])
        if motor_pos is None:
            ready['motor'] = False
            message = format_log_message(counter, ready, values)
            message += "Motor position not read.")
            log.warning(message)
            return trigger_id

        # If bearing not fixed, fetch the calculated mean bearing using data from two GPS sensors
        if not bearing_fixed:
            heading_ok = True
            if len(gps_managers) == 2:
                values['ship_bearing_mean'] = gps_checker_manager.mean_bearing
            else:
                values['ship_bearing_mean'] = gps_managers[0].heading

        # collect latest GPS data
        values = update_gps_values(gps_managers)

        # Fetch sun variables
        values['solar_az'], values['solar_el'],\
            values['motor_angles'] = azi_func.calculate_positions(values['lat0'], values['lon0'],
                                                                  values['alt0'], values['dt'],
                                                                  values['ship_bearing_mean'], motor,
                                                                  values['motor_pos'])  # TODO: just pass the values and motor dicts into this function

        log.debug("[{8}] Sun Az {0:1.0f} | El {1:1.0f} | ViewAz [{2:1.1f}|{3:1.1f}] | MotPos [{4:1.1f}|{5:1.1f}] | MotTarget {6:1.1f} ({7:1.1f})"\
                 .format(values['solar_az'], values['solar_el'],
                         motor_angles['view_comp_ccw'], motor_angles['view_comp_cw'],
                         values['motor_angles']['ach_mot_ccw'], values['motor_angles']['ach_mot_cw'],
                         values['motor_angles']['target_motor_pos_deg'],
                         values['motor_angles']['target_motor_pos_rel_az_deg'], counter))

        # Check if the sun is in a suitable position
        ready['sun'] = check_sun(sample, values['solar_az'], ['solar_el'])

        # If the sun is in a suitable position and the motor is not at the required position, move the motor, unless speed criterion is not met
        if (ready['sun'] and (abs(values['motor_angles']['target_motor_pos_step'] - values['motor_pos']) > motor['step_thresh']))\
                                                                                                                  and (ready['speed'])\
                                                                                                                  and (ready['heading']):
            log.info("Adjust motor angle ({0} --> {1})".format(values'motor_pos'], values['motor_angles']['target_motor_pos_step']))
            # Rotate the motor to the new position
            target_pos = values['motor_angles']['target_motor_pos_step']
            motor_func.rotate_motor(motor_func.commands, target_pos, motor['serial'])
            moving = True
            t0 = time.clock()  # timeout reference
            while moving and time.clock()-t0 < 5:
                moving, motor_pos = motor_func.motor_moving(motor['serial'], target_pos, tolerance=300)
                if moving is None:
                    moving = True
                log.info("..moving motor.. {0} --> {1} (check again in 2s)".format(motor_pos, target_pos))
                if time.clock()-t0 > 5:
                    log.warning("Motor movement timed out (this is allowed)")
                time.sleep(2)

    # If all checks are good, take radiometry measurements
    if all([use_rad, ready['gps'], ready['rad'], ready['sun'], ready['speed'], ready['heading']]):
        # Get the current time of the computer as a unique trigger id
        trigger_id['all_sensors'] = datetime.datetime.now()
        # collect latest GPS data now that a measurement will be triggered
        values = update_gps_values(gps_managers)
        
        # TODO: the gps dicts are really not needed since we can pass the values dict into the database.
        gps1_manager_dict = gps_func.create_gps_dict(gps_managers[0])
        if len(gps_managers) == 2:
            gps2_manager_dict = gps_func.create_gps_dict(gps_managers[1])
            gps2_manager_dict['used'] = True
        else:
            gps2_manager_dict = {}
            for key in gps1_manager_dict.keys():
                gps2_manager_dict[key] = None
            gps2_manager_dict['used'] = False

        # Collect radiometry data and splice together
        spec_data = []
        trig_id, specs, sids, itimes = radiometry_manager.sample_all(trigger_id)
        for n in range(len(sids)):
            spec_data.append([str(sids[n]),str(itimes[n]),str(specs[n])])

        # If db is used, commit the data to it
        if db_dict['used']:
            db_id = db_func.commit_db(db_dict, verbose, gps1_manager_dict, gps2_manager_dict,
                                      trigger_id['all_sensors'], values['ship_bearing_mean'],
                                      values['solar_az'], values['solar_el'], spec_data)
            message += "\nNew record (all sensors): {0} [{1}]".format(trigger_id['all_sensors'], db_id)

    # If not enough time has passed since the last measurement (rad not ready) and minimum interval to record GPS has not passed, skip to next cycle
    elif (abs(trigger_id['ed_sensor'].timestamp() - datetime.datetime.now().timestamp()) > Ed Interval)\
            and (all([use_rad, rad['ed_sampling'], ready['gps'], values['solar_el']>0])):
        trigger_id['ed_sensor'] = datetime.datetime.now()
        # trigger Ed
        rad['ed_sampling_interval']
        rad['ed_sensor_id']

        spec_data = []
        trig_id, specs, sids, itimes = radiometry_manager.sample_ed(trigger_id)
        for n in range(len(sids)):
            spec_data.append([str(sids[n]),str(itimes[n]),str(specs[n])])

        # If db is used, commit the data to it
        if db_dict['used']:
            db_id = db_func.commit_db(db_dict, verbose, gps1_manager_dict, gps2_manager_dict,
                                      trigger_id['all_sensors'], values['ship_bearing_mean'],
                                      values['solar_az'], values['solar_el'], spec_data)
        
        message += "\nNew record (Ed sensor): {0} [{1}]".format(trigger_id['ed_sensor'], db_id)

    last_any_commit = nanmax([trigger_id['all_sensors'], trigger_id['ed_sensor'], trigger_id['gps_location']])
    elif abs(datetime.datetime.now().timestamp() - last_any_commit.timestamp()) < 60:
        trigger_id['gps_location'] = datetime.datetime.now()

        # record metadata and GPS data at least every minute
        values = update_gps_values(gps_managers) # collect latest GPS data
        # TODO remove use of these dicts, pass value dict to db instead
        gps1_manager_dict = gps_func.create_gps_dict(gps_managers[0])
        if len(gps_managers) == 2:
            gps2_manager_dict = gps_func.create_gps_dict(gps_managers[1])
            gps2_manager_dict['used'] = True
        else:
            gps2_manager_dict = {}
            for key in gps1_manager_dict.keys():
                gps2_manager_dict[key] = None
            gps2_manager_dict['used'] = False

        if db_dict['used']:
            db_id = db_func.commit_db(db_dict, args.verbose, gps1_manager_dict, gps2_manager_dict,
                                      trigger_id['gps_location'], values['ship_bearing_mean'],
                                      values['solar_az'], values['solar_el'], spec_data=None)
            message += "\nNew record (gps location): {0} [{1}]".format(trigger_id['gps_location'], db_id)
            
    else:
        # nothing to do

    log.info(message)
    return trigger_id


def run():
    """ main program loop.
    Reads config file to set up environment then starts various threads to monitor inputs.
    Monitors for a keyboard interrupt to provide a clean exit where possible.
    """

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

    main_check_cycle_sec = conf['DEFAULT'].getint('main_check_cycle_sec')

    log.info("===Initialisation complete===")

    last_commit_time = datetime.datetime.now()
    trigger_id = {'all_sensors': nan, 'ed_sensor': nan, 'gps_location': nan}  # stores when data were last recorded

    # Repeat indefinitely until program closed
    counter = 0
    # TODO: replace with some sort of scheduler for better clock synchronization
    # TODO: periodically update config (timings/limits only)
    while True:
        counter += 1
        try:
            run_one_cycle(counter, conf, db_dict, rad, sample, gps_managers, radiometry_manager,
                          motor, battery, bat_manager, gpios, trigger_id, args.verbose)
            time.sleep(main_check_cycle_sec)

        except KeyboardInterrupt:
            log.info("Program interrupted, attempt to close all threads")
            stop_all(db_dict, radiometry_manager, gps_managers, battery, bat_manager, gpios)
        except Exception:
            log.exception("Unhandled Exception")
            stop_all(db_dict, radiometry_manager, gps_managers, battery, bat_manager, gpios)
            raise

if __name__ == '__main__':
    run()

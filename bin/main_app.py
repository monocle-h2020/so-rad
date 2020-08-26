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
from thread_managers.gps_checker import GPSChecker
from numpy import nan, max

# only import RPi libraries if running on a Pi (other environments can be used for unit testing)
try:
    import RPi.GPIO as GPIO
except Exception as msg:
    print("Could not import GPIO. Functionality may be limited to system tests.\n{0}".format(msg))  #  note no log available yet


__version__ = 20200826.0


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
    gps   = initialisation.gps_init(conf['GPS'], ports)

    rad, Rad_manager = initialisation.rad_init(conf['RADIOMETERS'], ports)
    sample = initialisation.sample_init(conf['SAMPLING'])
    battery, bat_manager = initialisation.battery_init(conf['BATTERY'], ports)
    tpr = initialisation.tpr_init(conf['TPR'])

    # collect info on which GPIO pins are being used to control peripherals
    gpios = []
    if Rad_manager is not None and rad['use_gpio_control']:
        gpios.append(rad['gpio1'])

    # start individual monitoring threads
    if battery['used']:
        bat_manager.start()
        time.sleep(0.1)

    if gps['manager'] is not None:
        gps['manager'].add_serial_port(gps['serial1'])
        gps['manager'].start()

    if tpr['manager'] is not None:
        log.info("Starting Tilt/Pitch/Roll manager")
        tpr['manager'].start()

    if motor['used']:
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
    if Rad_manager is not None:
        log.info("Starting radiometry manager")
        try:
            radiometry_manager = Rad_manager(rad)
            time.sleep(0.1)
            rad['ed_sampling'] = radiometry_manager.ed_sampling  # if the Ed sensor is not identified, disable this feature
        except Exception as msg:
            log.exception(msg)
            stop_all(db, None, gps, battery, bat_manager, gpios, tpr, idle_time=0)  # calls sys.exit after pausing for idle_time to prevent immediate restart
    else:
        radiometry_manager = None

    # Return all the dicts and manager objects
    return db, rad, sample, gps, radiometry_manager, motor, battery, bat_manager, gpios, tpr


def stop_all(db, radiometry_manager, gps, battery, bat_manager, gpios, tpr, idle_time=0):
    """stop all processes in case of an exception"""
    log = logging.getLogger()

    # Stop the radiometry manager
    log.info("Stopping radiometry manager threads")
    if radiometry_manager is not None:
        radiometry_manager.stop()

    # Stop the GPS manager
    if gps['manager'] is not None:
        log.info("Stopping GPS manager thread")
        gps['manager'].stop()
        time.sleep(0.5)

    # Stop the battery manager
    if (battery['used']) and (bat_manager is not None):
        log.info("Stopping battery manager thread")
        bat_manager.stop()

    # Stop the TPR manager
    if (tpr['used']) and (tpr['manager'] is not None):
        log.info("Stopping TPR manager thread")
        tpr['manager'].stop()

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


def update_gps_values(gps, values):
    """update the gps values to the latest available in the gps managers"""
    values['lat0'] = gps['manager'].lat
    values['lon0'] = gps['manager'].lon
    values['alt0'] = gps['manager'].alt
    values['dt'] = gps['manager'].datetime
    values['headMot'] = gps['manager'].headMot
    values['relPosHeading'] = gps['manager'].relPosHeading
    values['accHeading'] = gps['manager'].accHeading
    values['fix'] = gps['manager'].fix
    values['flags_headVehValid'] = gps['manager'].flags_headVehValid
    values['flags_diffSoln'] = gps['manager'].flags_diffSoln
    values['flags_gnssFixOK'] = gps['manager'].flags_gnssFixOK
    values['speed'] = gps['manager'].speed
    values['nsat0'] = gps['manager'].satellite_number
    return values


def format_log_message(counter, ready, values):
    """construct a log message based on several system checks"""
    checks = {True: "1", False: "0"}    # values to show for True/False (e.g. 1/0 or T/F)
    message = "[{0}] ".format(counter)
    # handle string formatting where value may be None
    strdict = {}
    for valkey in ['speed', 'solar_el', 'solar_az', 'headMot', 'relPosHeading', 'accHeading']:
        if values[valkey] is not None:
            strdict[valkey] = "{0:.2f}".format(values[valkey])
        else:
            strdict[valkey] = "n/a"

    message += "Checks:  Bat {0} GPS {1} Head {2} Rad {3} Spd {4} ({5}) Sun {6} ({7})"\
               .format(values['batt_voltage'], checks[ready['gps']],
                       checks[ready['heading']], checks[ready['rad']],
                       checks[ready['speed']], strdict['speed'],
                       checks[ready['sun']], strdict['solar_el'])
    message += "\n"
    message += "[{9}] Heading: SunAz {0} Mot {1} Veh {2} Acc: {3}) | Fix: {4}, Head: {5}, diffSoln: {6}, FixFl {7} | nSat {8} "\
                .format(strdict['solar_az'], strdict['headMot'], strdict['relPosHeading'],
                        strdict['accHeading'], values['fix'], values['flags_headVehValid'],
                        values['flags_diffSoln'], values['flags_gnssFixOK'], values['nsat0'], counter)

    return message


def run_one_cycle(counter, conf, db_dict, rad, sample, gps, radiometry_manager,
                  motor, battery, bat_manager, tpr, gpios, trigger_id, verbose):
    """run one measurement cycle

    : counter               - measurement cycle number, included for logging
    : conf                  - main configuration (parsed from file)
    : sample                - main sampling settings configuration
    : bat_manager           - battery manager instance
    : gps                   - gps settings dictionary including thread manager instance
    : radiometry_manager    - radiometry manager instance
    : rad                   - radiometry configuration
    : battery               - battery management configuration
    : motor                 - motor configuration
    : pgios                 - gpio pins in use

    returns:
    : trigger_id            - identifier of the last measurement (a datetime object)
    """

    log = logging.getLogger()

    # init dicts for all environment checks and latest sensor values
    ready = {'speed': False, 'motor': False, 'sun': False, 'rad': False, 'heading': False, 'gps': False}
    values = {'speed': None, 'nsat0': None, 'motor_pos': None, 'ship_bearing_mean': None,
              'solar_az': None, 'solar_el': None, 'motor_angles': None, 'batt_voltage': None,
              'lat0': None, 'lon0': None, 'alt0': None, 'dt': None, 'nsat0': None,
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
        if values['batt_voltage'] is None:
            log.warning("Failed to check Battery Voltage")
        elif check_battery(bat_manager, battery) == 1:  # 0 = OK, 1 = LOW, 2 = CRITICAL
            message = format_log_message(counter, ready, values)
            message += "Battery low, idling. Battery info: {1}".format(bat_manager)
            log.warning(message)
            return trigger_id  # always return last trigger id
        elif check_battery(bat_manager, battery) == 2:  # 0 = OK, 1 = LOW, 2 = CRITICAL
            message = format_log_message(counter, ready, values)
            message += "Battery level critical, shutting down. Battery info: {0}".format(bat_manager)
            log.warning(message)
            stop_all(db_dict, radiometry_manager, gps_managers, battery, bat_manager, gpios, idle_time=1800)  # calls sys.exit after pausing for idle_time to prevent immediate restart
            sys.exit(1)
        values['batt_voltage'] = bat_manager.batt_voltage                                                                                     # just in case it didn't do that.

    # Check positioning
    ready['gps']  = check_gps(gps)
    ready['heading'] = check_heading(gps)
    # Check radiometry / sampling conditions
    ready['rad'] = check_sensors(rad, trigger_id['all_sensors'], radiometry_manager)

    if ready['gps']:
        # read latest gps info and calculate angles for motor
        # valid positioning data is required to do anything else
        values = update_gps_values(gps, values)
        ready['speed'] = check_speed(sample, gps)

        # read motor position to see if it is ready
        if motor['used']:
            values['motor_pos'] = motor_func.get_motor_pos(motor['serial'])
            if values['motor_pos'] is None:
                ready['motor'] = False
                message = format_log_message(counter, ready, values)
                message += "Motor position not read."
                log.warning(message)
                return trigger_id
        else:
            # if no motor is used we'll assume the sensors are pointing in the motor home position. 
            values['motor_pos'] = motor['home_pos']

        # If bearing is not fixed, fetch the calculated mean bearing using data from two GPS sensors
        if not bearing_fixed:
            if ready['heading']:
                values['ship_bearing_mean'] = gps['manager'].heading
            else:
                values['ship_bearing_mean'] = None

        # collect latest GPS data
        values = update_gps_values(gps, values)

        # Fetch sun variables and determine optimal motor pointing angles
        values['solar_az'], values['solar_el'],\
            values['motor_angles'] = azi_func.calculate_positions(values['lat0'], values['lon0'],
                                                                  values['alt0'], values['dt'],
                                                                  values['ship_bearing_mean'], motor,
                                                                  values['motor_pos'])

        log.debug("[{8}] Sun Az {0:1.0f} | El {1:1.0f} | ViewAz [{2:1.1f}|{3:1.1f}] | MotPos [{4:1.1f}|{5:1.1f}] | MotTarget {6:1.1f} ({7:1.1f})"\
                 .format(values['solar_az'], values['solar_el'],
                         values['motor_angles']['view_comp_ccw'], values['motor_angles']['view_comp_cw'],
                         values['motor_angles']['ach_mot_ccw'], values['motor_angles']['ach_mot_cw'],
                         values['motor_angles']['target_motor_pos_deg'],
                         values['motor_angles']['target_motor_pos_rel_az_deg'], counter))

        # Check if the sun is in a suitable position
        ready['sun'] = check_sun(sample, values['solar_az'], values['solar_el'])

        # If the sun is in a suitable position and the motor is not at the required position, move the motor, unless speed criterion is not met
        # the motor will be moved even if the radiometers are not yet ready to keep them pointed away from the sun
        if (ready['sun'] and (abs(values['motor_angles']['target_motor_pos_step'] - values['motor_pos']) > motor['step_thresh']))\
                                                                                                                  and (ready['speed'])\
                                                                                                                  and (ready['heading'])\
                                                                                                                  and (motor['used']):
            log.info("Adjust motor angle ({0} --> {1})".format(values['motor_pos'], values['motor_angles']['target_motor_pos_step']))
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
        values = update_gps_values(gps_managers, values)

        # Collect and combine radiometry data
        spec_data = []
        trig_id, specs, sids, itimes = radiometry_manager.sample_all(trigger_id)
        for n in range(len(sids)):
            spec_data.append([str(sids[n]),str(itimes[n]),str(specs[n])])

        # If local database is used, commit the data
        if db_dict['used']:
            db_id = db_func.commit_db(db_dict, verbose, gps, trigger_id['all_sensors'], values, spectra_data=spec_data, software_version=__version__)
            log.info("New record (all sensors): {0} [{1}]".format(trigger_id['all_sensors'], db_id))

    # If not enough time has passed since the last measurement (rad not ready) and minimum interval to record GPS has not passed, skip to next cycle
    elif (abs(trigger_id['ed_sensor'].timestamp() - datetime.datetime.now().timestamp()) > rad['ed_sampling_interval'])\
        and (all([use_rad, rad['ed_sampling'], ready['gps'], values['solar_el']>-90])):
        trigger_id['ed_sensor'] = datetime.datetime.now()

        values = update_gps_values(gps, values) # collect latest GPS data

        # trigger Ed
        spec_data = []
        trig_id, specs, sids, itimes = radiometry_manager.sample_ed(trigger_id)
        for n in range(len(sids)):
            spec_data.append([str(sids[n]),str(itimes[n]),str(specs[n])])

        # If db is used, commit the data to it
        if db_dict['used']:
            db_id = db_func.commit_db(db_dict, verbose, gps, trigger_id['all_sensors'], values, spectra_data=spec_data, software_version=__version__)
            log.info("New record (Ed sensor): {0} [{1}]".format(trigger_id['ed_sensor'], db_id))

    else:
        trigger = False
        last_any_commit = max([trigger_id['all_sensors'], trigger_id['ed_sensor'], trigger_id['gps_location']])
        log.debug("last commit of any kind: {0}".format(last_any_commit))
        seconds_elapsed_since_last_any_commit = abs(datetime.datetime.now().timestamp() - last_any_commit.timestamp())
        log.debug("seconds since last commit: {0}".format(seconds_elapsed_since_last_any_commit))
        if seconds_elapsed_since_last_any_commit > 60:
            trigger_id['gps_location'] = datetime.datetime.now()
            # record metadata and GPS data at least every minute
            values = update_gps_values(gps, values) # collect latest GPS data

            if db_dict['used']:
                db_id = db_func.commit_db(db_dict, verbose, trigger_id['gps_location'], values, spectra_data=None, software_version=__version__)
                log.info("New record (gps location): {0} [{1}]".format(trigger_id['gps_location'], db_id))

    message = format_log_message(counter, ready, values)
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
        db_dict, rad, sample, gps, radiometry_manager, motor, battery, bat_manager, gpios, tpr = init_all(conf)
    except Exception:
        log.exception("Exception during initialisation")
        stop_all(db_dict, radiometry_manager, gps, battery, bat_manager, gpios, tpr)
        raise

    main_check_cycle_sec = conf['DEFAULT'].getint('main_check_cycle_sec')

    log.info("===Initialisation complete===")

    trigger_id = {'all_sensors': datetime.datetime.now(),
                  'ed_sensor': datetime.datetime.now(),
                  'gps_location': datetime.datetime.now()}  # stores when data were last recorded

    # Repeat indefinitely until program is closed
    counter = 0
    # TODO: replace with some sort of scheduler for better clock synchronization
    # TODO: periodically update config (timings/limits only) from remotely fetched config_local file
    while True:
        counter += 1
        try:
            run_one_cycle(counter, conf, db_dict, rad, sample, gps, radiometry_manager,
                          motor, battery, bat_manager, gpios, tpr, trigger_id, args.verbose)
            time.sleep(main_check_cycle_sec)

        except KeyboardInterrupt:
            log.info("Program interrupted, attempt to close all threads")
            stop_all(db_dict, radiometry_manager, gps, battery, bat_manager, gpios, tpr)
        except Exception:
            log.exception("Unhandled Exception")
            stop_all(db_dict, radiometry_manager, gps, battery, bat_manager, gpios, tpr)
            raise

if __name__ == '__main__':
    run()

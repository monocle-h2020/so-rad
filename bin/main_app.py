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
import argparse
import initialisation
import logging
import logging.handlers
import functions.motor_controller_functions as motor_func
import functions.db_functions as db_func
import functions.gps_functions as gps_func
import functions.azimuth_functions as azi_func
from functions.check_functions import check_gps, check_motor, check_sensors, check_sun, check_battery, check_speed, check_heading, check_pi_cpu_temperature, check_ed_sampling, check_internet, check_remote_data_store
from functions.export_functions import run_export, update_status_parse_server, identify_new_local_records
import functions.config_functions as cf_func
from numpy import nan, max


__version__ = 20230401.1


def parse_args():
    """parse command line arguments"""
    parser = argparse.ArgumentParser()
    parser.add_argument('-c', '--config_file', required=True,
                        help="config file providing program settings",
                        default=u"config.ini")
    parser.add_argument('-l', '--local_config_file', required=True,
                        help="system-specific config overrides providing program settings",
                        default=u"config-local.ini")
    parser.add_argument("--verbose", "-v", action='store_true', help="verbose output")
    parser.add_argument("--terse", "-t", action='store_true', help="terse output")

    args = parser.parse_args()

    if not os.path.exists(args.config_file):
        raise IOError("Config file not found at {0}".format(args.config_file))

    return args


def init_logger(conf_log_dict):
    """Initialises the root logger for the program

    :param conf_log_dict: dictionary containing the logger config information
    :type conf_log_dict: dictionary
    :return: log
    :rtype: logger
    """
    myFormat = '%(asctime)s | %(name)s | %(levelname)s | %(message)s'
    formatter = logging.Formatter(myFormat)
    log_filename = conf_log_dict['log_file_location']
    print(f"Logging to {log_filename}")
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

    log = logging.getLogger('init')
    db = initialisation.db_init(conf['DATABASE'])

    # Get all comports and collect the initialisation dicts
    ports = list_ports.comports()
    motor = initialisation.motor_init(conf['MOTOR'], ports)
    gps   = initialisation.gps_init(conf['GPS'], ports)

    rad, Rad_manager = initialisation.rad_init(conf['RADIOMETERS'], ports)
    sample = initialisation.sample_init(conf['SAMPLING'])
    battery, bat_manager = initialisation.battery_init(conf['BATTERY'], ports)
    tpr = initialisation.tpr_init(conf['TPR'])  # tilt sensor
    rht = initialisation.rht_init(conf['RHT'])  # internal temp/rh sensor

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

    if rht['manager'] is not None:
        # take a few readings to stabilize
        for i in range(5):
            rht_time, rht_rh, rht_temp = rht['manager'].update_rht_single()
        try:
            log.info("Internal Temperature and Humidity: {0:2.1f}C {1:2.1f}% ".format(rht_temp, rht_rh))
        except:
            log.error("Could not read RHT sensor")
        #rht['manager'].start()  # there is no need to run an averaging thread, but it's there if we want it

    if motor['used']:
        # Get the current motor pos and if not at HOME move it to HOME
        motor_pos = motor_func.get_motor_pos(motor['serial'])
        motor_ready, motor_alarm = check_motor(motor)  # check for motor alarms
        try:
            if motor_pos is None:
                log.warning(f"Motor position not read. Alarm status = {motor_alarm}")
                motor_deg = None
            motor_deg = motor_pos / motor['steps_per_degree']
        except:
            pass

        if (motor_ready) and (motor_deg is not None) and (motor_deg + motor['home_pos'] != 0):
            target_pos = int(-1.0 * motor['home_pos'] * motor['steps_per_degree'])
            t0 = time.time()
            log.info(f"Homing motor.. {motor_pos} --> {target_pos}. Alarm status = {motor_alarm}")
            motor_func.rotate_motor(motor_func.commands, target_pos, motor['serial'])
            moving = True
            while moving and (time.time()-t0 < 5):
                moving = motor_func.motor_moving(motor['serial'], motor['home_pos'], tolerance=300)[0]
                if moving is None:
                    moving = True  # assume we are not done
                log.info("..homing motor..")
                time.sleep(1)
            log.info("..done")
        elif not motor_ready:
            log.info(f"Motor not ready. Alarm status = {motor_alarm}")
        else:
            log.info("Motor in home position (corrected for offset)")
        time.sleep(0.1)

    # Start the radiometry manager
    if Rad_manager is not None:
        log.info("Starting radiometry manager")
        try:
            radiometry_manager = Rad_manager(rad)
            time.sleep(1.0)
            rad['ed_sampling'] = radiometry_manager.ed_sampling  # if the Ed sensor is not identified, disable this feature
            if len(radiometry_manager.sams) < rad['n_sensors']:
                raise Exception("One or more radiometers required were not found")
        except Exception as msg:
            log.exception(msg)
            try:
                stop_all(db, radiometry_manager, gps, battery, bat_manager, rad, tpr, rht, conf, idle_time=600)  # calls sys.exit after pausing for idle_time to prevent immediate restart
            except UnboundLocalError:
                # special case for G1 sensors getting an incomplete rad manager
                stop_all(db, None, gps, battery, bat_manager, rad, tpr, rht, conf, idle_time=600)  # calls sys.exit after pausing for idle_time to prevent immediate restart

    else:
        radiometry_manager = None

    # Return all the dicts and manager objects
    return db, rad, sample, gps, radiometry_manager, motor, battery, bat_manager, gpios, tpr, rht


def stop_all(db, radiometry_manager, gps, battery, bat_manager, rad, tpr, rht, conf, idle_time=0):
    """stop all processes in case of an exception"""
    log = logging.getLogger('stop')

    # Stop the radiometry manager
    if radiometry_manager is not None:
        log.info("Stopping radiometry manager threads")
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

    # Stop the RHT manager
    if (rht['used']) and (rht['manager'] is not None) and (rht['manager'].started):
        log.info("Stopping RHT manager thread")
        rht['manager'].stop()

    # Turn all GPIO pins off
    initialisation.init_gpio(conf, rad, state=0)  # set all used pins to LOW
    rad['gpio_interface'].stop()  # release gpio control
    time.sleep(0.5)

    # Wait for any lingering threads.
    log.info(f"Waiting on {threading.active_count()} active threads..")
    for t in threading.enumerate()[1:]:
        log.info(t.ident)
    t0 = time.perf_counter()
    while (threading.active_count() > 1) and ((time.perf_counter()-t0) < 10):
        log.info(f"Waiting on {threading.active_count()} active threads..")
        time.sleep(1.0)

    # Join any lingering threads.
    t0 = time.perf_counter()
    if threading.active_count() > 1:
        for t in threading.enumerate()[1:]:
            log.info(t.ident)
            t.join()

    log.info(f"There are {threading.active_count()} active threads left.")

    # Exit the program
    log.info("Idling {0} s before shutdown".format(idle_time))
    time.sleep(idle_time)
    log.info("Exiting")
    sys.exit(0)


def update_system_values(gps, values, tpr=None, rht=None, motor=None):
    """update system value dict to the latest available in the sensor managers"""
    log = logging.getLogger('main')
    values['lat0'] = gps['manager'].lat
    values['lon0'] = gps['manager'].lon
    values['alt0'] = gps['manager'].alt
    values['dt'] = gps['manager'].datetime
    values['headMot'] = gps['manager'].headMot
    values['relPosHeading'] = gps['manager'].relPosHeading
    values['accHeading'] = gps['manager'].accHeading
    values['fix'] = gps['manager'].fix
    values['flags_headVehValid'] = gps['manager'].flags_headVehValid
    values['flags_diffSolN'] = gps['manager'].flags_diffSolN
    values['flags_gnssFixOK'] = gps['manager'].flags_gnssFixOK
    values['speed'] = gps['manager'].speed
    values['nsat0'] = gps['manager'].satellite_number
    values['pi_temp'] = check_pi_cpu_temperature()
    if (tpr is not None) and (tpr['manager'] is not None):
        log.debug("Tilt: {0} ({1})".format(tpr['manager'].tilt_avg, tpr['manager'].tilt_std))
        values['tilt_avg'] = tpr['manager'].tilt_avg
        values['tilt_std'] = tpr['manager'].tilt_std
    if (rht is not None) and (rht['manager'] is not None):
        rh_time, rh, temp = rht['manager'].update_rht_single()
        log.debug("Temp: {0}C RH: {1}%".format(temp, rh))
        values['inside_temp'] = temp
        values['inside_rh'] =   rh
    if (motor is not None) and (motor['used']):
        values['driver_temp'], values['motor_temp'] =  motor_func.motor_temp_read(motor)
    return values


def format_log_message(counter, ready, values):
    """Format log messages"""
    checks = {True: "1", False: "0"}    # values to show for True/False (e.g. 1/0 or T/F)
    message = "{0} | ".format(counter)
    # handle string formatting where value may be None
    strdict = {}
    for valkey in ['speed', 'solar_el', 'solar_az', 'headMot', 'relPosHeading', 'accHeading', 'ship_bearing_mean', 'motor_deg', 'tilt_avg', 'lat0', 'lon0', 'rel_view_az']:
        if values[valkey] is not None:
            if valkey in ['lat0', 'lon0']:
                strdict[valkey] = "{0:.5f}".format(values[valkey])
            else:
                strdict[valkey] = "{0:.2f}".format(values[valkey])
        else:
            strdict[valkey] = "n/a"

    if (not ready['heading']) or (values['motor_angles']['target_motor_pos_rel_az_deg'] is None):
        strdict['tar_view_az'] = "n/a"
    else:
        strdict['tar_view_az'] = "{0:.2f}".format(values['motor_angles']['target_motor_pos_rel_az_deg'])

    try:
        message += f"Bat {values['batt_voltage']} GPS {checks[ready['gps']]} Head {checks[ready['heading']]} Rad {checks[ready['rad']]} Spd {checks[ready['speed']]} ({strdict['speed']}) Sun {checks[ready['sun']]} ({strdict['solar_el']}) Tilt {strdict['tilt_avg']} Motor {checks[ready['motor']]} ({values['motor_alarm']})"
        message += f" | SunAz {strdict['solar_az']} Ship {strdict['ship_bearing_mean']} Motor {strdict['motor_deg']}| Fix: {values['fix']} ({values['nsat0']} sats) | RelViewAz: {strdict['rel_view_az']} (-> {strdict['tar_view_az']}) | loc: {strdict['lat0']} {strdict['lon0']}"
    except: pass

    return message


def run_one_cycle(counter, conf, db_dict, rad, sample, gps, radiometry_manager,
                  motor, battery, bat_manager, gpios, tpr, rht, trigger_id, verbose):
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
    : gpios                 - gpio pins in use

    returns:
    : trigger_id            - identifier of the last measurement (a datetime object)
    """

    log = logging.getLogger('main')

    # init dicts for all environment checks and latest sensor values
    ready = {'speed': False, 'motor': False, 'sun': False, 'rad': False, 'heading': False, 'gps': False}
    values = {'counter': counter, 'speed': None, 'nsat0': None, 'motor_pos': None, 'motor_deg': None, 'ship_bearing_mean': None,
              'solar_az': None, 'solar_el': None, 'motor_angles': {}, 'rel_view_az': None, 'batt_voltage': None,
              'lat0': None, 'lon0': None, 'alt0': None, 'dt': None, 'nsat0': None,
              'headMot': None, 'relPosHeading': None, 'accHeading': None, 'fix': None,
              'flags_headVehValid': None, 'flags_diffSolN': None, 'flags_gnssFixOK': None,
              'tilt_avg': None, 'tilt_std': None, 'inside_temp': None, 'inside_rh': None,
              'motor_alarm': None, 'driver_temp': None, 'motor_temp': None, 'pi_temp': None}

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
            stop_all(db_dict, radiometry_manager, gps_managers, battery, bat_manager, rad, conf, idle_time=1800)  # calls sys.exit after pausing for idle_time to prevent immediate restart
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
        values = update_system_values(gps, values, tpr, rht, motor)
        ready['speed'] = check_speed(sample, gps)

        # read motor position to see if it is ready
        if motor['used']:
            ready['motor'], values['motor_alarm'] = check_motor(motor)  # check for motor alarms
            values['motor_pos'] = motor_func.get_motor_pos(motor['serial'])
            try:
                values['motor_deg'] = values['motor_pos'] / motor['steps_per_degree']
            except:
                pass
            if values['motor_pos'] is None:
                ready['motor'] = False
                message = format_log_message(counter, ready, values)
                message += "Motor position not read."
                log.warning(message)
                return trigger_id
        else:
            # if no motor is used we'll assume the sensors are pointing in the motor home position.
            values['motor_pos'] = motor['home_pos']
            try:
                values['motor_deg'] = values['motor_pos'] / motor['steps_per_degree']
                ready['motor'] = True
            except:
                ready['motor'] = False
                pass

        # If bearing is not fixed, fetch the calculated mean bearing using data from GPS+heading sensors
        if not bearing_fixed:
            if ready['heading']:
                values['ship_bearing_mean'] = (gps['manager'].heading - gps['gps_heading_correction']) % 360.0
            else:
                values['ship_bearing_mean'] = None

        # collect latest GPS data
        values = update_system_values(gps, values)

        # Fetch sun variables and determine optimal motor pointing angles
        try:
            values['solar_az'], values['solar_el'],\
                values['motor_angles'] = azi_func.calculate_positions2(values['lat0'], values['lon0'],
                                                                      0.0, values['dt'],
                                                                      values['ship_bearing_mean'], motor,
                                                                      values['motor_pos'])
        except:
            log.warning(f"No pointing solution found. Is GPS info available?")
            ready['motor'] = False
            values['motor_angles']['target_motor_pos_rel_az_deg'] = None
            values['motor_angles']['target_motor_pos_step'] = None
            log.info(f"lat {values['lat0']} lon {values['lon0']} alt {values['alt0']} {values['dt']} heading {values['ship_bearing_mean']} motor {values['motor_pos']}")

        # Check if the sun is in a suitable position
        ready['sun'] = check_sun(sample, values['solar_az'], values['solar_el'])

        # Move motor?
        # full set of criteria
        if (ready['sun']) and (ready['speed']) and (ready['heading']) and (motor['used']) and (ready['motor'])\
            and ( abs(values['motor_angles']['target_motor_pos_step'] - values['motor_pos'] ) > motor['step_thresh']):
                move_motor = True
        # relaxed criteria - move the motor more often as long as the heading etc are valid (set 'adjust_mode' in config file)
        elif (ready['heading']) and (motor['used']) and (motor['adjust_mode']=='always') and (ready['motor'])\
            and ( abs(values['motor_angles']['target_motor_pos_step'] - values['motor_pos'] ) > motor['step_thresh']):
                move_motor = True
        else:
            move_motor = False

        if move_motor:
            target_pos = values['motor_angles']['target_motor_pos_step']
            log.info(f"{counter} | Adjust motor angle ({values['motor_pos']} --> {target_pos})")
            # Rotate the motor to the new position
            target_pos_deg_in_motor_plane = target_pos / motor['steps_per_degree']
            tolerance = 5.0
            if (target_pos_deg_in_motor_plane > motor['cw_limit'] + tolerance) or (target_pos_deg_in_motor_plane < motor['ccw_limit'] - tolerance):
                log.warning(f"Illegal motor position requested: {target_pos_deg_in_motor_plane} vs {motor['ccw_limit']} - {motor['cw_limit']}")
                ready['motor'] = False
            else:
                motor_func.rotate_motor(motor_func.commands, target_pos, motor['serial'])
                moving = True
                t0 = time.time()  # timeout reference
                while moving and time.time()-t0 < 5:
                    moving, values['motor_pos'] = motor_func.motor_moving(motor['serial'], target_pos,
                                                                          tolerance=motor['steps_per_degree']*3)
                    if moving is None:
                        moving = True
                    log.info(f"{counter} | ..moving motor.. {values['motor_pos']} --> {target_pos} (check again in 2s)")
                    if time.time()-t0 > 5:
                        log.warning("Motor movement timed out (this is allowed)")
                    time.sleep(0.1)

    # check whether the interval for separate Ed sampling has passed
    ready['ed_sampling'] = check_ed_sampling(use_rad, rad, ready, values)

    # collect latest GPS and TPR data now that a measurement may be triggered
    values = update_system_values(gps, values, tpr, rht, motor)

    try:
        values['motor_deg'] = values['motor_pos'] / motor['steps_per_degree']
    except:
        pass
    # update viewing azimuth details
    values['rel_view_az'], values['solar_az'] = azi_func.sun_relative_azimuth(values['lat0'], values['lon0'], 0.0, values['dt'],
                                                                              values['ship_bearing_mean'], values['motor_deg'], motor)

    # If all checks are good, take radiometry measurements
    if all([use_rad, ready['gps'], ready['rad'], ready['sun'], ready['speed'], ready['heading'], ready['motor']]):
        # Get the current time of the computer as a unique trigger id
        trigger_id['all_sensors'] = datetime.datetime.now()

        # Collect and combine radiometry data
        spec_data = []
        trig_id, specs, sids, itimes, pre_incs, post_incs, temp_incs = radiometry_manager.sample_all(trigger_id['all_sensors'])

        for n in range(len(sids)):
            spec_data.append([str(sids[n]),str(itimes[n]),str(specs[n])])

        # If local database is used, commit the data
        if db_dict['used']:
            db_id = db_func.commit_db(db_dict, verbose, values, trigger_id['all_sensors'], spectra_data=spec_data, software_version=__version__)
            log.info("{2} | New record (all sensors): {0} [{1}]".format(trigger_id['all_sensors'], db_id, counter))

        try:
            for sid, spec in zip(sids, spec_data):
                if None in spec:
                    log.warning(f"{counter} | None value encountered in spectrum from {sid}")
        except Exception as err:
            log.exception(err)

    # alternatively trigger just the Ed sampling, if corresponding conditions are met
    elif (abs(trigger_id['ed_sensor'].timestamp() - datetime.datetime.now().timestamp()) > rad['ed_sampling_interval'])\
        and (ready['ed_sampling']):
        trigger_id['ed_sensor'] = datetime.datetime.now()

        # trigger Ed
        spec_data = []
        trig_id, specs, sids, itimes, pre_incs, post_incs, temp_incs = radiometry_manager.sample_ed(trigger_id['ed_sensor'])
        for n in range(len(sids)):
            spec_data.append([str(sids[n]),str(itimes[n]),str(specs[n])])

        # If db is used, commit the data to it
        if db_dict['used']:
            db_id = db_func.commit_db(db_dict, verbose, values, trigger_id['all_sensors'], spectra_data=spec_data, software_version=__version__)
            log.info("{2} | New record (Ed sensor): {0} [{1}]".format(trigger_id['ed_sensor'], db_id, counter))

    # Alternatively check to see if just the gps location / metadata should be written
    else:
        trigger = False
        last_any_commit = max([trigger_id['all_sensors'], trigger_id['ed_sensor'], trigger_id['gps_location']])
        log.debug("last commit of any kind: {0}".format(last_any_commit))
        seconds_elapsed_since_last_any_commit = abs(datetime.datetime.now().timestamp() - last_any_commit.timestamp())
        log.debug("seconds since last commit: {0}".format(seconds_elapsed_since_last_any_commit))
        if seconds_elapsed_since_last_any_commit > 60:
            trigger_id['gps_location'] = datetime.datetime.now()

            if db_dict['used']:
                db_id = db_func.commit_db(db_dict, verbose, values, trigger_id['gps_location'], spectra_data=None, software_version=__version__)
                log.info("{2} | New record (gps location): {0} [{1}]".format(trigger_id['gps_location'], db_id, counter))

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
    conf = cf_func.read_config(args.config_file)
    conf = cf_func.update_config(conf, args.local_config_file)
    # start logging here
    log = init_logger(conf['LOGGING'])

    log = logging.getLogger('main')
    log.info('\n===Started logging===\n')


    try:
        # Initialise everything
        db_dict, rad, sample, gps, radiometry_manager, motor, battery, bat_manager, gpios, tpr, rht = init_all(conf)
    except Exception:
        log.exception("Exception during initialisation")
        stop_all(db_dict, radiometry_manager, gps, battery, bat_manager, rad, tpr, rht, conf, idle_time=120)
        raise

    main_check_cycle_sec = conf['DEFAULT'].getint('main_check_cycle_sec')

    log.info("===Initialisation complete===")

    trigger_id = {'all_sensors': datetime.datetime.now(),
                  'ed_sensor': datetime.datetime.now(),
                  'gps_location': datetime.datetime.now()}  # stores when data were last recorded, initialise here

    # Repeat indefinitely until program is closed
    counter = 0
    remote_update_timer = time.perf_counter() - 290.0  # set timer to 10 seconds before next trigger
    export_result = True  # tracks whether exporting has been succesful

    # TODO: replace with some sort of scheduler for better clock synchronization
    # TODO: periodically update config (timings/limits only) from remotely fetched config_local file
    while True:
        counter += 1
        last_check_cycle_start = time.perf_counter()
        try:
            run_one_cycle(counter, conf, db_dict, rad, sample, gps, radiometry_manager,
                          motor, battery, bat_manager, gpios, tpr, rht, trigger_id, args.verbose)
            log.info(f"Check cycle completed in {time.perf_counter() - last_check_cycle_start} s")

            use_export = conf['EXPORT'].getboolean('use_export')
            if not use_export:
                log.debug("f{counter} | No data export configured")
                time_to_sleep = main_check_cycle_sec - (time.perf_counter() - last_check_cycle_start)
                if time_to_sleep > 0:
                    time.sleep(time_to_sleep)
                continue

            # remote data store(s) operations go here, ideally within the time window where the system is idling
            t0 = time.perf_counter() # start of data upload operations this cycle.

            # while system idles, check how many samples need uploading, upload a batch and check again
            n_total, n_not_inserted, all_not_inserted = identify_new_local_records(db_dict, limit=0)  # just checking local db
            log.info(f"{counter} | {n_not_inserted} samples pending upload. Waited {time.perf_counter() - remote_update_timer:4.1f} s since last connection attempt")
            if not check_internet():
                log.debug(f"{counter} | Internet connection timed out.")

            if (n_not_inserted == 0) and (time.perf_counter() - remote_update_timer > 60):
                # update remote status at most once per minute if there are no data to upload
                if check_remote_data_store(conf)[0]:
                    export_result, resultcode = update_status_parse_server(conf, db_dict)
                    sucorfail = {True: 'succeeded', False:'failed'}[export_result]
                    log.info(f"{counter} | Instrument status update on remote server {sucorfail}")
                else:
                    log.debug(f"{counter} | No connection to remote server to update instrument status")

                remote_update_timer = time.perf_counter()  # reset timer regardless of result (don't spam the server)

            elif (n_not_inserted > 0) and ((export_result) or (time.perf_counter() - remote_update_timer > 300)):
                # if data are pending upload and connection was already good or 5 minutes have passed, try uploading data
                export_result = True
                if check_remote_data_store(conf)[0]:
                    while ((time.perf_counter() - t0 < main_check_cycle_sec) and n_not_inserted > 0) and (export_result):
                        # upload data until this check cycle is over, or no more samples remain, or an upload fails.
                        log.debug(f"{counter} | Uploading latest 10 samples ({n_not_inserted} pending)")
                        export_result, resultcode, successes = run_export(conf, db_dict, limit=10, test_run=False)
                        log.info(f"{counter} | {successes} sensor records uploaded. Request completed: {export_result}")
                        n_total, n_not_inserted, all_not_inserted = identify_new_local_records(db_dict, limit=0)  # just checking local db
                        time.sleep(0.05)
                    remote_update_timer = time.perf_counter()  # reset timer
                else:
                    log.debug(f"{counter} | No connection to remote server")
                    export_result = False
                    remote_update_timer = time.perf_counter()  # reset timer to try again in 5 minutes

            else:
                log.debug(f"{counter} | No data upload action taken for {time.perf_counter()-remote_update_timer:4.1f} s")

            time_to_sleep = main_check_cycle_sec - (time.perf_counter() - last_check_cycle_start)

            if time_to_sleep > 0:
                time.sleep(time_to_sleep)

        except KeyboardInterrupt:
            log.info("Program interrupted, attempt to close all threads")
            stop_all(db_dict, radiometry_manager, gps, battery, bat_manager, rad, tpr, rht, conf)
        except Exception:
            log.exception("Unhandled Exception")
            stop_all(db_dict, radiometry_manager, gps, battery, bat_manager, rad, tpr, rht, conf, idle_time=120)
            raise

if __name__ == '__main__':
    run()

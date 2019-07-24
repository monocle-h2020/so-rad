#!/usr/bin/python3
# -*- coding: utf-8 -*-
"""
Autonomous operation of hyperspectral radiometers with optional rotating measurement platform, solar power supply and remote connectivity

This script provides a class to interface with radiometers.

There should be a class for each family of sensors. Currently we just have TriosManager to control 3 TriOS spectroradiometers

Plymouth Marine Laboratory
License: under development

"""
import sys
import time
import datetime
import logging
import RPi.GPIO as GPIO
import traceback
from PyTrios import PyTrios as ps

log = logging.getLogger()   # report to root logger


class TriosManager(object):
    """
    Trios manager class
    """
    def __init__(self, rad):
        # import pytrios only if used
        #sys.path.append(rad['pytrios_path'])
        #global ps
        #from pytrios import PyTrios as ps
        self.config = rad  # dictionary with radiometry settings
        self.ports = [self.config['port1'], self.config['port2'], self.config['port3']]  # list of strings
        self.coms = ps.TMonitor(self.ports, baudrate=9600)
        self.sams = []
        self.connect_sensors()
        # track reboot cycles to prevent infinite rebooting of sensors if something unexpected happens (e.g a permanent sensor failure)
        self.reboot_counter = 0
        self.last_cold_start = datetime.datetime.now()
        self.last_connectivity_check = datetime.datetime.now()
        self.lasttrigger = None  # don't use this to get a timestamp on measurements, just used as a delay timer
        self.busy = False  # check this value to see if sensors are ready to sample


    def __del__(self):
        ps.tchannels = {}
        ps.TClose(self.coms)

    def connect_sensors(self):
        """(re)connect all serial ports and query all sensors"""
        self.busy = True

        log.info("(re)connecting to radiometers: closing com ports (wait 5 sec)")
        ps.TClose(self.coms)
        ps.tchannels = {}
        time.sleep(5)

        log.info("(re)connecting to radiometers: restarting listening threads (wait 5 sec)")
        self.coms = ps.TMonitor(self.ports, baudrate=9600)
        time.sleep(2)

        for com in self.coms:
            # set verbosity for com channel (com messages / errors)
            # 0/1/2 = none, errors, all
            com.verbosity = self.config['verbosity_com']
            # query connected instruments
            ps.TCommandSend(com, commandset=None, command='query')
        time.sleep(3)  # pause to receive query results

        self._identify_sensors()

        if len(self.sams) == 0:
            ps.TClose(self.coms)
            self.ready = False
            log.critical("no SAM modules found")
            raise Exception("no SAM modules found")

        for s in self.sams:
            # 0/1/2/3/4 = none, errors, queries(default), measurements, all
            self.tc[s].verbosity = self.config['verbosity_chn']  # set verbosity level for each sensor
            self.tc[s].failures = 0  # TODO: this adds a variable to the class, should really be added in the tchannel Class

        self.busy = False

    def _identify_sensors(self):
        """identify SAM instruments from identified channels"""
        self.tk = list(ps.tchannels.keys())
        self.tc = ps.tchannels
        self.sams = [k for k in self.tk if ps.tchannels[k].TInfo.ModuleType in ['SAM', 'SAMIP']]  # keys
        self.chns = [self.tc[k].TInfo.TID for k in self.sams]  # channel addressing
        self.sns = [self.tc[k].TInfo.serialn for k in self.sams]  # sensor ids
        try:
            self.tc_ed = self.sns.index(self.config['ed_sensor_id'])  # index (in sams list) of the ed sensor
        except:
            log.warning("Ed sensor not found")
            self.tc_ed = None

        if self.config['verbosity_com'] > 1:
            log.info("found SAM modules: {0}".format(list(zip(self.chns, self.sns))))

    def power_cycle_sensors(self):
        """reboot sensors by cycling power through GPIO/relay control
        All sensors must then be reconnected/identified"""
        self.busy = True
        GPIO.setmode(GPIO.BOARD)
        pins = [self.config['gpio1'], self.config['gpio2'], self.config['gpio3']]
        GPIO.setup(pins, GPIO.OUT)
        GPIO.output(pins, GPIO.LOW)
        time.sleep(30)
        GPIO.output(pins, GPIO.HIGH)
        time.sleep(10)
        self.reboot_counter += 1
        self.last_cold_start = datetime.datetime.now()
        self.connect_sensors()
        self.busy = False

    def check_and_restore_sensor_number(self):
        """check (called periodically from main app) whether the expected number of sensors are connected. 
        This will help recover from an incomplete reboot and 'tired sensor syndrome' in trios acc sensors."""
        reboot_int = self.config['minimum_reboot_interval_sec']
        time_elapsed_since_last_check = datetime.datetime.now()-self.last_connectivity_check
        log.debug("reboot_int: {0}, time_elapsed: {1}, n_sensors_now: {2}".format(reboot_int,
                                                                                  time_elapsed_since_last_check.total_seconds(),
                                                                                  len(self.sams)))
        if len(self.sams) == self.config['n_sensors']:
            # all is fine
            return True

        if time_elapsed_since_last_check.total_seconds() < reboot_int:
            # wait a bit longer before taking action
            return False

        # take action
        self.busy = True
        self.last_connectivity_check = datetime.datetime.now()
        if self.config['use_gpio_control']:
            if self.config['verbosity_chn'] > 0:
                log.warning("Number of sensors < {0}. Rebooting".format(self.config['n_sensors']))
            self.power_cycle_sensors()
        else:
            if self.config['verbosity_chn'] > 0:
                log.warning("Number of sensors < {0}. Reconnecting (no relay control set)".format(self.config['n_sensors']))
            self.connect_sensors()
        self.busy = False
        if len(self.sams) == self.config['n_sensors']:
            # all is fine
            return True
        else:
            return False


    def sample_ed(self, trigger_id):
        """this will trigger sampling only the sensor identified as the Ed sensor"""
        edsam = self.sams[self.tc_ed]
        return self.sample_all(trigger_id, sams_included=edsam)

    def sample_all(self, trigger_id, sams_included=None):
        """Send a command to take a spectral sample from every sensor currently detected by the program"""
        self.lasttrigger = datetime.datetime.now()  # this is not used to timestamp measurements, only to track progress
        self.busy = True
        try:
            if sams_included is None:
                sams_included = self.sams

            for s in sams_included:
                if self.config['inttime'] > 0:
                    # trigger single measurement at fixed integration time
                    self.tc[s].startIntSet(self.tc[s].serial, self.config['inttime'], trigger=self.lasttrigger)
                else:
                    # trigger single measurement at auto integration time
                    self.tc[s].startIntAuto(self.tc[s].serial, trigger=self.lasttrigger)

            # follow progress
            npending = len(sams_included)
            while npending > 0:
                # pytrios has a 12-sec timeout period for sam instruments so this will not loop forever
                # triggered measurements may not be pending but also not finished (i.e. incomplete or missing data)
                finished = [k for k in sams_included if self.tc[k].is_finished()]
                pending = [k for k in sams_included if self.tc[k].is_pending()]
                nfinished = len(finished)
                npending = len(pending)
                time.sleep(0.05)

            # account failed and successful measurement attempts
            missing = list(set(sams_included) - set(finished))

            for k in finished:
                self.tc[k].failures = 0
            for k in missing:
                self.tc[k].failures +=1

            # how long did the measurements take to arrive?
            if nfinished > 0 and self.config['verbosity_chn'] > 2:
                if type(self.tc[k].TSAM.lastRawSAMTime) == type(self.lasttrigger) and self.tc[k].TSAM.lastRawSAMTime is not None:
                    delays = [self.tc[k].TSAM.lastRawSAMTime - self.lasttrigger for k in sams_included]
                    delaysec = max([d.total_seconds() for d in delays])
                    log.info("\t{0} spectra received, triggered at {1} ({2} s)"
                        .format(nfinished, self.lasttrigger, delaysec))

            if len(missing) > 0 and self.config['verbosity_chn'] > 0:
                log.warning("Incomplete or missing result from {0}".format(",".join(missing)))

            # gather succesful results
            specs = [self.tc[s].TSAM.lastRawSAM
                    for s in sams_included if self.tc[s].is_finished()]
            sids = [self.tc[s].TInfo.serialn
                    for s in sams_included if self.tc[s].is_finished()]
            itimes = [self.tc[s].TSAM.lastIntTime
                    for s in sams_included if self.tc[s].is_finished()]

            # call reboot function for sensors that keep failing, followed by new query on respective COM port?
            rebooting = False
            for s in sams_included:
                if self.tc[s].failures > self.config['allow_consecutive_timeouts']:
                    rebooting = True

            if rebooting:
                time_since_last_reboot = datetime.datetime.now()-self.last_cold_start
                reboot_int = self.config['minimum_reboot_interval_sec']
                if self.config['use_gpio_control'] and time_since_last_reboot.total_seconds() > reboot_int:
                    if self.config['verbosity_chn'] > 0:
                        log.warning("Rebooting sensors")
                    self.power_cycle_sensors()
                else:
                    if self.config['verbosity_chn'] > 0:
                        log.warning("Reconnecting sensors (no relay control set)")
                    self.connect_sensors()

            self.busy = False
            return trigger_id, specs, sids, itimes  # specs, sids, itimes may be empty lists

        except Exception as m:
            ps.TClose(self.coms)
            log.exception("Exception in TriosManager: {}".format(m))
            raise

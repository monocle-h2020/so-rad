#!/usr/bin/python3
# -*- coding: utf-8 -*-
"""
Autonomous operation of hyperspectral radiometers.
This script provides a class to interface with TriOS radiometers.

The G1 manager runs a thread for each communication port, always listening for measurement triggers and for sensor output.

Plymouth Marine Laboratory
License: CC-BY-NC
Author: stsi
"""

import os
import sys
import time
import datetime
import logging
import threading
import PyTrios as ps

log = logging.getLogger('rad')
log.setLevel('INFO')


class TriosManager(object):
    """
    Trios G1 manager class
    """
    def __init__(self, list_of_ports):
        self.ports = list_of_ports
        self.coms = ps.TMonitor(self.ports, baudrate=9600)
        self.sams = []
        self.connect_sensors()
        self.lasttrigger = None  # don't use this to get a timestamp on measurements, just used as a delay timer
        self.busy = False  # check this value to see if sensors are ready to sample

    def __del__(self):
        ps.tchannels = {}
        ps.TClose(self.coms)

    def stop(self):
        ps.tchannels = {}
        ps.TClose(self.coms)

    def connect_sensors(self):
        """(re)connect all serial ports and query all sensors"""
        self.busy = True

        ps.TClose(self.coms)
        ps.tchannels = {}
        time.sleep(1)

        log.info("Connecting to radiometers: starting listening threads (wait 2 sec to initialise)")
        self.coms = ps.TMonitor(self.ports, baudrate=9600)
        time.sleep(2)

        for com in self.coms:
            # set verbosity for com channel (com messages / errors)
            # 0/1/2 = none, errors, all
            com.verbosity = 1
            # query connected instruments
            ps.TCommandSend(com, commandset=None, command='query')
        time.sleep(2)  # pause to receive query results

        self._identify_sensors()

        if len(self.sams) == 0:
            ps.TClose(self.coms)
            self.ready = False
            log.critical("no SAM modules found")
            raise Exception("no SAM modules found")

        for s in self.sams:
            # set verbosity: 0/1/2/3/4 = none, errors, queries(default), measurements, all
            self.tc[s].verbosity = 2  # set verbosity level for each sensor

        self.busy = False

    def _identify_sensors(self):
        """identify SAM instruments from identified channels"""
        self.tk = list(ps.tchannels.keys())
        self.tc = ps.tchannels
        self.sams = [k for k in self.tk if ps.tchannels[k].TInfo.ModuleType in ['SAM', 'SAMIP']]  # keys
        self.chns = [self.tc[k].TInfo.TID for k in self.sams]  # channel addressing
        self.sns = [self.tc[k].TInfo.serialn for k in self.sams]  # sensor ids

        log.info("found SAM modules: {0}".format(list(zip(self.chns, self.sns))))
        log.info("found channels: {0}".format(list(self.tk)))

    def sample_all(self, trigger_id, sams_included=None):
        """Send a command to take a spectral sample from every sensor currently detected by the program"""
        self.lasttrigger = datetime.datetime.now()  # this is not used to timestamp measurements, only to track progress
        self.busy = True
        try:
            if sams_included is None:
                sams_included = self.sams

            for s in sams_included:
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
            if nfinished > 0:
                if type(self.tc[k].TSAM.lastRawSAMTime) == type(self.lasttrigger) and self.tc[k].TSAM.lastRawSAMTime is not None:
                    delays = [self.tc[k].TSAM.lastRawSAMTime - self.lasttrigger for k in sams_included]
                    delaysec = max([d.total_seconds() for d in delays])
                    log.info("\t{0} spectra received, triggered at {1} ({2} s)"
                        .format(nfinished, self.lasttrigger, delaysec))

            if len(missing) > 0:
                log.warning("Incomplete or missing result from {0}".format(",".join(missing)))

            # gather succesful results
            specs = [self.tc[s].TSAM.lastRawSAM for s in sams_included if self.tc[s].is_finished()]
            sids = [self.tc[s].TInfo.serialn for s in sams_included if self.tc[s].is_finished()]
            itimes = [self.tc[s].TSAM.lastIntTime for s in sams_included if self.tc[s].is_finished()]

            self.busy = False
            pre_incs = [None]
            post_incs = [None]
            temp_incs = [None]
            # specs, sids, itimes may be empty lists, Last three fields for forward compatibility with G2 sensors
            return trigger_id, specs, sids, itimes, pre_incs, post_incs, temp_incs

        except Exception as m:
            ps.TClose(self.coms)
            log.exception("Exception in TriosManager: {}".format(m))
            raise

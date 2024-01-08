#!/usr/bin/python3
# -*- coding: utf-8 -*-
"""
Autonomous operation of hyperspectral radiometers with optional rotating measurement platform, solar power supply and remote connectivity

This script provides a class to interface with radiometers.

There should be a class for each family of sensors. Currently we have TriosManager to control 3 TriOS G1 (original) spectroradiometers and TriosG2Manager for the G2 update.
The G1 manager runs a thread for each communication port, always listening for measurement triggers and for sensor output. The G2 version monitors the sensor timer to determine when a measurement has finished and then idles while waiting for a new trigger. 

Plymouth Marine Laboratory
License: under development

"""
import os
import sys
import time
import datetime
import logging
import threading

log = logging.getLogger('rad')
log.setLevel('INFO')

try:
    import RPi.GPIO as GPIO
except Exception as msg:
    log.warning("Not running on a Raspberry Pi. Functionality may be limited to system tests: \n{0}".format(msg))


class TriosG2Manager(object):
    """
    A collection of Ramses G2 control threads.

    Trios G2 manager class setting up a sensor thread for each connected sensor and storing their properties.
    G2 uses modbus interface and includes sensor activity timers. This means continuous polling for data on serial ports is no longer required.
    A thread is started per port with a sensor attached - we don't support daisy chaining in this manager although it is inherently possible within the RS485 protocol to set specific slave addresses.
    """
    def __init__(self, rad):
        # import specific library for this sensor type
        global pt2
        import pytrios_g2.pytrios2 as pt2
        self.sams = []
        self.config = rad  # dictionary with radiometry settings
        self.ed_sampling = rad['ed_sampling']
        #self.ports = [self.config['port1'], self.config['port2'], self.config['port3']]  # list of strings
        self.ports = rad['ports']
        self.instruments = []  # store TriosG2Ramses instances which were succesfully started
        self.instruments_defined = [] # store all instances on which connections may be live
        self.connect_sensors()

        # track reboot cycles to prevent infinite rebooting of sensors if something unexpected happens (e.g a permanent sensor failure)
        self.reboot_counter = 0
        self.last_cold_start = datetime.datetime.now()
        self.last_connectivity_check = datetime.datetime.now()
        self.lasttrigger = None  # don't use this to get a timestamp on measurements, just used as a timer
        self.failures = 0

        self.busy = False  # check this value to see if sensors are being set up or triggered
        self.ready = False  # true when manager finishes initialisation.

        # thread properties
        self.started = False

    def connect_sensors(self, timeout=2):
        """connect to each port, start threads and collect sensor information"""
        if len(self.instruments) > 0:
             log.warning(f"There are already {len(self.instruments)} Ramses G2 instruments connected. Operation aborted.")
             return

        self.instruments_defined = []
        for port in self.ports:
            self.instruments_defined.append(TriosG2Ramses(port))

        for instrument in self.instruments_defined:
            instrument.start()
            time.sleep(0.5)
            instrument.connect()
            instrument.get_identity()

        t0 = time.perf_counter()
        while ((time.perf_counter() - t0) < timeout) and (len(self.instruments_defined) > 0):
            for instrument in self.instruments_defined:
                if (not instrument.busy) and (instrument not in self.instruments):
                    log.info(f"{instrument.mod['port']}: sensor {instrument.sam} connected.")
                    self.instruments.append(instrument)
                    self.sams.append(instrument.sam)
                    #instruments_defined.remove(instrument)
            time.sleep(0.1)

        for instrument in self.instruments_defined:
            if instrument not in self.instruments:
                log.warning(f"{instrument.mod['port']}: sensor connection timed out.")

        self.ready = True
        self.busy = False

    def stop(self):
        for instrument in self.instruments_defined:
            instrument.stop()

    def power_cycle_sensors(self):
        """reboot sensors by cycling power through GPIO/relay control
        All sensors must then be reconnected/identified"""
        self.busy = True
        self.ready = False
        self.stop()
        self.instruments = []
        self.sams = []
        rad = self.config
        pin = self.config['gpio1']
        rad['gpio_interface'].off(pin)
        time.sleep(30)
        rad['gpio_interface'].on(pin)
        time.sleep(2)
        self.reboot_counter += 1
        self.last_cold_start = datetime.datetime.now()
        self.connect_sensors()

    def check_and_restore_sensor_number(self):
        """check (called periodically from main app) whether the expected number of sensors are connected.
        This will help recover from an incomplete reboot and 'tired sensor syndrome' in trios acc sensors."""
        reboot_int = self.config['minimum_reboot_interval_sec']
        time_elapsed_since_last_check = datetime.datetime.now()-self.last_connectivity_check
        log.debug("reboot_int: {0}, time_elapsed: {1}, n_sensors_now: {2}".format(reboot_int,
                                                                                  time_elapsed_since_last_check.total_seconds(),
                                                                                  len(self.instruments)))
        if len(self.instruments) == self.config['n_sensors']:
            # all is fine
            return True

        elif time_elapsed_since_last_check.total_seconds() < reboot_int:
            # wait a bit longer before taking action
            return False

        else:
            # take action
            self.busy = True
            self.last_connectivity_check = datetime.datetime.now()
            if self.config['use_gpio_control']:
                log.warning("Number of sensors < {0}. Rebooting".format(self.config['n_sensors']))
                self.power_cycle_sensors()
            else:
                log.warning("Number of sensors < {0}. Reconnecting (no relay control set)".format(self.config['n_sensors']))
                self.connect_sensors()

            self.busy = False

            if len(self.instruments) == self.config['n_sensors']:
                # all is fine
                return True
            else:
                return False


    def sample_ed(self, trigger_time):
        """this will trigger sampling only the sensor identified as the Ed sensor"""
        edsam = self.config['ed_sensor_id']
        instrument = [inst for inst in self.instruments if inst.sam == edsam]
        if len(instrument) == 0:
            log.error(f"Ed sensor {edsam} not found")
            return trigger_time, [], instrument.sam, None, None, None, None
        else:
            instrument =  instrument[0]

        self.busy = True
        t0 = time.perf_counter()
        instrument.sample_one(trigger_time)
        while (instrument.busy) and (time.perf_counter() - t0 < 30):
            time.sleep(0.1)

        self.busy = False
        result = instrument.result
        if result is None:
            log.error(f"No result received from {instrument}")
            return trigger_time, [], instrument.sam, None, None, None, None

        return trigger_time, result.spectrum, instrument.sam, result.integration_time['value'],\
               result.pre_inclination['value'], result.post_inclination['value'], result.temp_inclination_sensor['value']


    def sample_all(self, trigger_time, sams_included=None):
        """Send a command to take a spectral sample from every sensor currently detected by the program"""
        self.lasttrigger = datetime.datetime.now()  # this is not used to timestamp measurements, only to track progress
        self.busy = True
        try:
            if sams_included is None:
                instruments_included = self.instruments
            else:
                instruments_included = [inst for inst in self.instruments if inst.sam in sams_included]

            failure = False

            # setting non-auto integration time is not implemented yet for pytrios_g2
            for instrument in instruments_included:
                #if self.config['inttime'] > 0:
                #    # trigger single measurement at fixed integration time
                #    self.tc[s].startIntSet(self.tc[s].serial, self.config['inttime'], trigger=self.lasttrigger)
                #else:
                #    # trigger single measurement at auto integration time
                instrument.sample_one(trigger_time)

            # follow progress
            t0 = time.perf_counter()
            npending = sum([i.busy for i in instruments_included])
            while (npending > 0) and (time.perf_counter() - t0 < 30):
                npending = sum([i.busy for i in instruments_included])
                time.sleep(0.05)

            if npending > 0:
                # one or more instruments did not return a result
                pending = [i.sam for i in instruments_included if i.busy]
                log.warning(f"Timeout: missing result from {','.join([p for p in pending])}")
                failure = True

            instruments_valid = []
            for i in instruments_included:
                if (i.result is None) or (i.result.spectrum is None) or (instrument.last_received < instrument.last_sampled):
                    log.warning(f"No new measurement from {i.sam}")
                    failure = True
                else:
                    instruments_valid.append(i)

            nfinished = len(instruments_valid)

            # how long did the measurements take to arrive?
            if nfinished > 0:
                delays = [i.last_received - i.last_sampled for i in instruments_valid]
                delaysec = [d.total_seconds() for d in delays]
                log.info(f"{nfinished} spectra received, triggered at {trigger_time} ({','.join([str(d) for d in delaysec])} s)")

            # increase the failure counter if anything was missing or reset it if all was good
            if failure:
                self.failures += 1
                log.info(f"Number of consecutive failures: {self.failures}")
            else:
                self.failures = 0

            # gather succesful results
            results = [instrument.result for instrument in instruments_valid]
            sids =  [instrument.sam for instrument in instruments_valid]
            specs = [result.spectrum for result in results]
            itimes = [result.integration_time['value'] for result in results]
            pre_incs = [result.pre_inclination['value'] for result in results]
            post_incs = [result.post_inclination['value'] for result in results]
            temp_incs = [result.temp_inclination_sensor['value'] for result in results]

            # call reboot function for sensors that keep failing, followed by new query on respective COM ports
            if self.failures > self.config['allow_consecutive_timeouts']:
                time_since_last_reboot = datetime.datetime.now()-self.last_cold_start  # timedelta
                reboot_int = self.config['minimum_reboot_interval_sec']
                if self.config['use_gpio_control'] and time_since_last_reboot.total_seconds() > reboot_int:
                    log.warning("Rebooting sensors")
                    self.power_cycle_sensors()
                else:
                    log.info(f"Not (yet) rebooting sensors. GPIO control: {self.config['use_gpio_control']}. Earliest reboot after {reboot_int - time_since_last_reboot.total_seconds()} s")

            self.busy = False
            return trigger_time, specs, sids, itimes, pre_incs, post_incs, temp_incs  # specs, sids, itimes etc may be empty lists

        except Exception as m:
            log.exception("Exception in TriosManager: {}".format(m))


class TriosG2Ramses(object):
    """
    A single Ramses G2 sensor control thread.
    """
    def __init__(self, port):
        self.mod = {'port': port, 'serial': None}  # modbus serial communications object
        self.sam = None   # sensor serial number
        # sampling properties
        self.busy = False    # True if the sensor is used for something (a very soft lock)
        self.ready = False   # True if a sensor is connected
        # thread properties
        self.started = False
        self.stop_monitor = False
        self.sleep_interval = 0.05  # time between thread cycles
        # command requests
        self.identify = False  # if set True, sensor info will be requested. Use get_identity() to set.
        self.trigger_sample = False  # store instruction for next sampling event. use sample_one() to set.
        # results
        self.result = None  # store latest sample result
        self.last_sampled = None
        self.last_received = None

    def __del__(self):
        self.stop()

    def __repr__(self):
        return (f"TriosG2Ramses {self.sam}")

    def start(self):
        """
        Starts the sampling thread
        """
        if not self.started:
            self.started = True
            self.thread = threading.Thread(target=self.run)  # use args = (arg1,arg2) if needed
            self.thread.start()
            log.info(f"Started RAMSES G2 communication thread on port {self.mod['port']}")
        else:
            log.warning(f"Could not start RAMSES G2 thread on port {self.mod['port']}")

    def connect(self):
        """(re)connect all serial ports and query all sensors."""
        self.busy = True

        if (self.mod['serial'] is not None) and (self.mod['serial'].isOpen()):
            log.info(f"Closing port {self.mod['port']}")
            pt2.close_modbus(self.mod)

        log.info(f"{self.mod['port']}: connecting to radiometer")
        pt2.open_modbus(self.mod)

        sleeptime = None
        t0 = time.perf_counter()
        timeout = 20
        log.info(f"{self.mod['port']}: checking sensor sleep state")
        while (sleeptime is None) and (time.perf_counter() - t0 < timeout):
            sleeptime = pt2.read_one_register(self.mod, 'deep_sleep_timeout')
            if sleeptime is None:
                log.warning(f"{self.mod['port']}: failed to read sensor sleep state. Retry for {timeout - (time.perf_counter() - t0):2.1f} s")
                time.sleep(1.0)
            else:
                log.info(f"{self.mod['port']}: deep sleep status/time: {sleeptime}")

        log.info(f"{self.mod['port']}: checking sensor measurement timer")
        meastime = pt2.read_one_register(self.mod, 'measurement_timeout')
        if meastime is None:
            log.warning(f"{self.mod['port']}: failed to read sensor measurement timer.")
        else:
            log.info(f"{self.mod['port']}: Measurement timer: {meastime}")

        log.info(f"{self.mod['port']}: checking sensor LAN state")
        lanstate0 = pt2.get_lan_state(self.mod)
        if lanstate0 is None:
            log.warning(f"{self.mod['port']}: failed to detect LAN state.")
        elif lanstate0:
            log.info(f"{self.mod['port']}: disable LAN state.")
            pt2.set_lan_state(self.mod, False)
        else:
            log.info(f"{self.mod['port']}: LAN state: {lanstate0}.")

        log.info(f"{self.mod['port']}: checking sensor auto-trigger setting")
        autotrig = pt2.read_one_register(self.mod, 'self_trigger_activated')
        if autotrig is None:
            log.warning(f"{self.mod['port']}: failed to detect auto-trigger setting.")
        else:
            log.info(f"{self.mod['port']}: auto-trigger mode: {autotrig}.")

        log.info(f"{self.mod['port']}: checking integration time setting")
        inttime = pt2.read_one_register(self.mod, 'integration_time_cfg')
        if inttime is None:
            log.warning(f"{self.mod['port']}: failed to detect integration time setting.")
        elif inttime > 0:
            log.info(f"{self.mod['port']}: setting integration time to auto (0)")
            pt2.set_integration_time(self.mod, inttime=0)
            inttime = pt2.read_one_register(self.mod, 'integration_time_cfg')
            log.info(f"{self.mod['port']}: Integration time: {inttime}")
        else:
            log.info(f"{self.mod['port']}: Integration time: {inttime}")

        self.ready = True
        self.busy = False

    def sample_one(self, trigger_time=True):
        """
        Prime for sampling, set sensor status to busy
        trigger_time can be a datetime object or True
        The running thread will read the status and do any waiting required.
        """
        self.busy = True
        self.trigger_sample = trigger_time
        log.info(f"Next sample trigger: {self.trigger_sample}")

    def get_identity(self):
        """
        Prime to identify sensor, set sensor status to busy
        The running thread will read the status and reset the busy flag
        """
        self.busy = True
        self.identify = True

    def _identify(self):
        """called by thread monitor to identify connected sensor"""
        self.busy = True
        log.info("Checking for trios sensor")
        self.sam = pt2.report_slave_id(self.mod)

        if self.sam is None:
            pt2.close_modbus(self.mod)
            self.ready = False
            log.critical(f"No Ramses G2 sensor found on {self.mod['port']}")
        else:
            self.ready = True
            self.busy = False

    def stop(self):
        """
        Stops the sampling thread
        """
        self.busy = True
        log.info(f"Stopping RAMSES G2 thread {self.thread.ident} on port {self.mod['port']}")
        self.stop_monitor = True
        time.sleep(1 * self.sleep_interval)
        if self.thread is not None:
            log.info(self.thread)
            self.thread.join(2 * self.sleep_interval)
        log.info(f"RAMSES G2 thread on port {self.mod['port']} running: {self.thread.is_alive()}")
        self.started = False
        self.busy = False
        self.ready = False

    def run(self):
        """
        Main loop of the thread.
        This will listen for requested actions and execute them, monitoring whether the sensor is available.
        """
        while not self.stop_monitor:
            if self.identify:
                self._identify()
                self.identify = False

            if self.trigger_sample:
                if isinstance(self.trigger_sample, datetime.datetime):
                    sec_remaining = (self.trigger_sample - datetime.datetime.now()).total_seconds()
                    if sec_remaining > 0:
                        time.sleep(self.sleep_interval)
                        continue

                # now sample
                log.info(f"Measurement requested on {self.mod['port']}")
                self.result = None
                self.last_sampled = datetime.datetime.now()
                self.result = pt2.sample_one(self.mod)
                try:
                    if self.result.spectrum is not None:
                        self.last_received = datetime.datetime.now()
                except Exception as err:
                    log.exception(err)
                    pass

                self.trigger_sample = False
                self.busy = False

            time.sleep(self.sleep_interval) # sleep for a standard period, ideally close to the refresh frequency of the sensor (0.01s)
            continue


class TriosManager(object):
    """
    Trios G1 manager class
    """
    def __init__(self, rad):
        # import pytrios only if used
        global ps
        from PyTrios import PyTrios as ps
        self.config = rad  # dictionary with radiometry settings
        self.ed_sampling = rad['ed_sampling']
        #self.ports = [self.config['port1'], self.config['port2'], self.config['port3']]  # list of strings
        self.ports = rad['ports']
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

    def stop(self):
        ps.tchannels = {}
        ps.TClose(self.coms)

    def connect_sensors(self):
        """(re)connect all serial ports and query all sensors"""
        self.busy = True

        log.info("(re)connecting to radiometers: closing com ports (wait 5 sec)")
        ps.TClose(self.coms)
        ps.tchannels = {}
        time.sleep(5)

        log.info("(re)connecting to radiometers: restarting listening threads (wait 2 sec)")
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
            log.info(self.tc)
            tc_ed_index = self.sns.index(self.config['ed_sensor_id'])  # index (in sams list) of the ed sensor
            self.tk_ed = self.tk[tc_ed_index]
        except Exception as err:
            log.warning("Ed sensor not found (looking for {0}), got {1}. Disabling any Ed sampling schedule".format(self.config['ed_sensor_id'], self.sns))
            self.tk_ed = None
            self.ed_sampling = False
            #log.exception(err)

        if self.config['verbosity_com'] > 1:
            log.info("found SAM modules: {0}".format(list(zip(self.chns, self.sns))))
        if self.config['verbosity_com'] > 2:
            log.info("found channels: {0}".format(list(self.tk)))

    def power_cycle_sensors(self):
        """reboot sensors by cycling power through GPIO/relay control
        All sensors must then be reconnected/identified"""
        self.busy = True
        GPIO.setmode(GPIO.BCM)
        pin = self.config['gpio1']
        GPIO.setup(pin, GPIO.OUT)
        GPIO.output(pin, GPIO.LOW)
        time.sleep(30)
        GPIO.output(pin, GPIO.HIGH)
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
        edsam = self.tk_ed
        if not isinstance(edsam, list):
            edsam = [edsam]
        log.info("Triggering Ed sensor = {0} ({1})".format(edsam, type(edsam)))
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
            pre_incs = [None]
            post_incs = [None]
            temp_incs = [None]
            # specs, sids, itimes may be empty lists, Last three fields for forward compatibility
            return trigger_id, specs, sids, itimes, pre_incs, post_incs, temp_incs

        except Exception as m:
            ps.TClose(self.coms)
            log.exception("Exception in TriosManager: {}".format(m))
            raise

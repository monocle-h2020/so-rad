#!/usr/bin/python3
# -*- coding: utf-8 -*-
"""
This script provides classes to interface with temperature, relative humidity (and maybe pressure) sensors. 

Implements a class for each type of RHT manager. A class is provided for:
 - Adafruit DHT22

The manager will use a monitoring thread if averaging is needed.

Plymouth Marine Laboratory
License: see README.md

"""
import logging
import threading
import datetime
import time
log = logging.getLogger('rht')
try:
    import Adafruit_DHT
except Exception as err:
    log.error("Module not imported - either missing or due to unsupported platform. Some functions may not work")
    log.exception(err)


class Ada_dht22(object):
    """
    Adafruit DHT22 class, normally initalised from initialisation.py
    Connects to the board over a single data pins on the Raspberry Pi. Probably won't work away from the RPi.
    """
    def __init__(self, rht):
        """
        Set up
        : rht is the [RHT] part of the config file interpreted as a dictionary in initialisation.py
        """
        self.pin = rht['pin']
        self.temp = None
        self.rh  = None
        self.updated = None
        self.thread = None
        self.started = False
        self.stop_monitor = False
        self.sleep_interval = 0.1
        self.sampling_time = rht['sampling_time']  # sampling cycle (for averagin) in seconds
        self.update_rht_single()   # init with first reading
        self.buffer_time =  [self.updated]
        self.buffer_temp =  [self.temp]
        self.buffer_rh = [self.rh]

    def update_rht_single(self):
        '''Read Relative Humidity and Temperature once'''
        self.rh, self.temp = Adafruit_DHT.read_retry(Adafruit_DHT.DHT22, self.pin)
        self.updated = datetime.datetime.now()
        return self.updated, self.rh, self.temp

    def __repr__(self):
        return "Temp {0:0.2f}C \tRelative Humidity {1:0.2f}%".format(self.temp, self.rh)

    def start(self):
        """
        Starts reading thread.
        """
        if not self.started:
            self.started = True
            self.thread = threading.Thread(target=self.run)  # use args = (arg1,arg2) if needed
            self.thread.start()
            log.info("Started RHT manager")
        else:
            log.warn("Could not start RHT manager")

    def stop(self):
        """
        Stop the sampling thread
        """
        log.info("Stopping RHT manager")
        self.stop_monitor = True
        time.sleep(1*self.sleep_interval)
        log.info(self.thread)
        self.thread.join(2*self.sleep_interval)
        log.info("RHT manager running = {0}".format(self.thread.is_alive()))
        self.started = False

    def run(self):
        """
        Main loop of the thread.
        This will run and read new data and pass it back
        """
        log.info("Starting RHT monitor thread")
        while not self.stop_monitor:
            timestamp, rh, temp = self.update_rht_single()
            if len(self.buffer_time)<10:
                self.buffer_time.append(timestamp)
                self.buffer_temp.append(temp)
                self.buffer_rh.append(rh)
                time.sleep(self.sleep_interval)
                continue
            else:
                # housekeeping, purge old entries from buffer
                time_cutoff = datetime.datetime.now() - datetime.timedelta(seconds=self.sampling_time)

                current_keep = argwhere(array(self.buffer_time) >= time_cutoff)
                current_keep = array([k[0] for k in current_keep]) # flatten, not sure why this is needed

                self.buffer_time  = list(array(self.buffer_time)[current_keep])
                self.buffer_temp  = list(array(self.buffer_temp)[current_keep])
                self.buffer_rh =    list(array(self.buffer_rh)[current_keep])
                self.buffer_time.append(timestamp)
                self.buffer_temp.append(temp)
                self.buffer_rh.append(rh)
                # buffer is now current

                buffer_age = (datetime.datetime.now() - self.buffer_time[0]).total_seconds()
                if buffer_age > self.sampling_time:
                    # average and stdev of buffered result
                    self.temp_avg  = nanmean(self.buffer_temp)
                    self.temp_std  = nanstd(self.buffer_temp)
                    self.rh_avg = nanmean(self.buffer_rh)
                    self.rh_std = nanstd(self.buffer_rh)
                    self.avg_updated = datetime.datetime.now()

            time.sleep(self.sleep_interval) # sleep for a standard period, ideally close to the refresh frequency of the sensor (0.01s)
            continue

    def __del__(self):
        self.stop()

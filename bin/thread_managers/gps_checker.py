#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
GPS Checker

Contains the GPS Checker object which instantiates the GPS Checker Thread for
calculating the mean, median and standard deviations for the latitude and
longitude coordinates of the GPS sensors, and uses them to calculate the ship
bearing from the mean and median lats and lons. Also splices and interpolates
the GPS times and data points.
"""
import time
import sys
import threading
import logging
import datetime
import traceback
#import functions.gps_functions as gps_func
from functions.compass_bearing import calculate_initial_compass_bearing
from numpy import mean, median, std, argwhere, array, interp, append, any, nan, isnan, min, max, nanmean, nanmedian, nanstd

log = logging.getLogger()   # report to root logger


class GPSCheckerThread(threading.Thread):
    """
    Thread to check the GPS data
    """
    def __init__(self, parent, gps_managers):
        threading.Thread.__init__(self)
        self._parent = parent

        self.observers = []
        self.stop_checker_thread = False

        self.gps_managers = gps_managers
        self.gps1_lat_mean = 0
        self.gps1_lon_mean = 0
        self.gps2_lat_mean = 0
        self.gps2_lon_mean = 0

        self.gps1_lat_median = 0
        self.gps1_lon_median = 0
        self.gps2_lat_median = 0
        self.gps2_lon_median = 0

        self.gps1_lat_std = []
        self.gps1_lon_std = []
        self.gps2_lat_std = []
        self.gps2_lon_std = []

        self.mean_bearing = 0
        self.median_bearing = 0
        self.prev_gps1_time = datetime.datetime(1970,1,1)
        self.prev_gps2_time = datetime.datetime(1970,1,1)
        self.last_reset = datetime.datetime.now()

        log.info("Starting GPS Checker thread")

    def run(self):
        log.info("checker thread running")

        try:
            # create numpy arrays for each variable list
            lat1_list = array([], dtype='float64')
            lon1_list = array([], dtype='float64')
            time1_list = array([], dtype='M')
            lat2_list = array([], dtype='float64')
            lon2_list = array([], dtype='float64')
            time2_list = array([], dtype='M')
        except Exception as emsg:
            traceback.print_exc(file=sys.stdout)
            log.critical('GPS checker array init failed: \n{0}'.format(emsg))
            time.sleep(10)

        while not self.stop_checker_thread:
            try:
                # get the newest data from the gps managers
                lat1 = self.gps_managers[0].lat
                lon1 = self.gps_managers[0].lon
                gps1_time = self.gps_managers[0].datetime

                lat2 = self.gps_managers[1].lat
                lon2 = self.gps_managers[1].lon
                gps2_time = self.gps_managers[1].datetime

                gps1_stopping = self.gps_managers[0].stop_gps
                gps2_stopping = self.gps_managers[1].stop_gps
                any_gps_stopping = gps1_stopping or gps2_stopping
                # If there isn't data, wait
                if ((gps1_time is None) or (gps2_time is None)) and (not any_gps_stopping):
                    log.warning("Waiting for GPS data")
                    time.sleep(1.12)
                    continue

                # Wait for a bit if the sensors are out of sync to allow one to catch up
                elif abs(gps1_time.timestamp() - gps2_time.timestamp()) > 1:
                    #self.gps_managers[0].flushbuffer()
                    #self.gps_managers[1].flushbuffer()
                    log.warning("GPS managers out of sync at {0} [1: {1} | 2: {2}]".\
                                format(datetime.datetime.now(), gps1_time.timestamp(), gps2_time.timestamp()))
                    #time_elapsed = datetime.datetime.now() - self.last_reset
                    #if time_elapsed.total_seconds() > 300:
                    #    self.last_reset = datetime.datetime.now()
                    #    log.info("Resetting GPS com ports")
                    #    self.gps_managers[0].reset_comports()
                    #    self.gps_managers[1].reset_comports()
                    time.sleep(1.12)
                    continue

                # if gps1 has newer data, add to and slice arrays
                if gps1_time > self.prev_gps1_time:
                    lat1_list = append(lat1_list, lat1)
                    lon1_list = append(lon1_list, lon1)
                    time1_list = append(time1_list, gps1_time)
                    if lat1_list.size > self._parent.avging_list_len:
                        lat1_list = lat1_list[-self._parent.avging_list_len:]
                        lon1_list = lon1_list[-self._parent.avging_list_len:]
                        time1_list = time1_list[-self._parent.avging_list_len:]

                # if gps2 has newer data, add to and slice arrays
                if gps2_time > self.prev_gps2_time:
                    lat2_list = append(lat2_list, lat2)
                    lon2_list = append(lon2_list, lon2)
                    time2_list = append(time2_list, gps2_time)
                    if lat2_list.size > self._parent.avging_list_len:
                        lat2_list = lat2_list[-self._parent.avging_list_len:]
                        lon2_list = lon2_list[-self._parent.avging_list_len:]
                        time2_list = time2_list[-self._parent.avging_list_len:]

                if not(any(time1_list)) or not(any(time2_list)):
                    #lat1_last = lat1_list.size-1
                    #lon1_last = lon1_list.size-1
                    #lat2_last = lat2_list.size-1
                    #lon2_last = lon2_list.size-1
                    #time1_last = time1_list.size-1
                    #time2_last = time2_list.size-1
                    log.warning("One or more GPS records missing: gps1 {0} | gps2 {1} records".format(len(time1_list), len(time2_list)))
                    time.sleep(1)
                    continue

                first_common_time = max([time1_list[0], time2_list[0]])
                last_common_time = min([time1_list[-1], time2_list[-1]])
                if first_common_time == last_common_time:
                    log.warning("Common GPS record too short for interpolation (c1). {0} - {1}".format(first_common_time, last_common_time))
                    time.sleep(1)
                    continue
                #log.debug("common_time {0} - {1}".format(first_common_time, last_common_time))

                try:
                    first_ind1 = argwhere(time1_list >= first_common_time)[0][0]
                    first_ind2 = argwhere(time2_list >= first_common_time)[0][0]
                    last_ind1 = argwhere(time1_list <= last_common_time)[-1][0]
                    last_ind2 = argwhere(time2_list <= last_common_time)[-1][0]
                except:
                    log.info("Common GPS record too short for interpolation (c2)")
                    time.sleep(1)
                    continue
                if (first_ind1 == last_ind1) or (first_ind2 == last_ind2):
                    log.info("Common GPS record too short for interpolation (c3)")
                    time.sleep(1)
                    continue

                #log.debug("first ind1 {0} last ind1 {1}".format(first_ind1, last_ind1))
                #log.debug("first ind1 {0} last ind1 {1}".format(first_ind2, last_ind2))

                common_lat1_list  = lat1_list[first_ind1:last_ind1+1]
                common_lon1_list  = lon1_list[first_ind1:last_ind1+1]
                common_time1_list = time1_list[first_ind1:last_ind1+1]
                common_lat2_list  = lat2_list[first_ind2:last_ind2+1]
                common_lon2_list  = lon2_list[first_ind2:last_ind2+1]
                common_time2_list = time2_list[first_ind2:last_ind2+1]

                # the following only handled 2 out of 4 cases, replaced with code above
                # it also seems risky to alter the same objects that new data are supposed to go into
                #time2_extra = argwhere(array(time2_list) > array(time1_list)[time1_last]+datetime.timedelta(microseconds=100000))
                #print(time2_extra)
                #if time2_extra.size: #if the list 'time2_extra' isn't empty
                #    lat2_list = lat2_list[:time2_extra[0][0]]
                #    lon2_list = lon2_list[:time2_extra[0][0]]
                #    time2_list = time2_list[:time2_extra[0][0]]

                #time1_extra = argwhere(array(time1_list) < array(time2_list)[0]-datetime.timedelta(microseconds=100000))
                #if time1_extra.size:
                #    lat1_list = lat1_list[time1_extra[0][-1]:]
                #    lon1_list = lon1_list[time1_extra[0][-1]:]
                #    time1_list = time1_list[time1_extra[0][-1]:]

                times1 = array([date.timestamp() for date in common_time1_list], dtype='float64')
                times2 = array([date.timestamp() for date in common_time2_list], dtype='float64')

                time1_diff = common_time1_list[-1] - common_time1_list[0]
                time2_diff = common_time2_list[-1] - common_time2_list[0]

                if time1_diff < datetime.timedelta(seconds=3):
                    log.warning("GPS1 record too short for interpolation: ({0}s)".format(time1_diff))
                    time.sleep(0.2)
                    continue
                elif time2_diff < datetime.timedelta(seconds=3):
                    log.warning("GPS2 record too short for interpolation: ({0}s)".format(time2_diff))
                    time.sleep(0.2)
                    continue

                gps2latinterp = interp(times1, times2, common_lat2_list, left=nan, right=nan)
                gps2loninterp = interp(times1, times2, common_lon2_list, left=nan, right=nan)

                #gps2latinterp = array([num for num in gps2latinterp if not isnan(num)])
                #gps2loninterp = array([num for num in gps2loninterp if not isnan(num)])

                times2 = times1
                common_time2_list = common_time1_list

                self.gps1_lat_mean = nanmean(common_lat1_list)
                self.gps1_lon_mean = nanmean(common_lon1_list)
                self.gps2_lat_mean = nanmean(gps2latinterp)
                self.gps2_lon_mean = nanmean(gps2loninterp)
                # self.gps2_lat_mean = mean(lat2_list)
                # self.gps2_lon_mean = mean(lon2_list)

                self.gps1_lat_median = nanmedian(common_lat1_list)
                self.gps1_lon_median = nanmedian(common_lon1_list)
                self.gps2_lat_median = nanmedian(gps2latinterp)
                self.gps2_lon_median = nanmedian(gps2loninterp)
                # self.gps2_lat_median = median(lat2_list)
                # self.gps2_lon_median = median(lon1_list)

                self.gps1_lat_std = nanstd(common_lat1_list)
                self.gps1_lon_std = nanstd(common_lon1_list)
                self.gps2_lat_std = nanstd(gps2latinterp)
                self.gps2_lon_std = nanstd(gps2loninterp)
                # self.gps2_lat_std = std(lat2_list)
                # self.gps2_lon_std = std(lon2_list)

                self.mean_bearing = calculate_initial_compass_bearing((self.gps1_lat_mean, self.gps1_lon_mean),
                                                                       (self.gps2_lat_mean, self.gps2_lon_mean))
                self.median_bearing = calculate_initial_compass_bearing((self.gps1_lat_median, self.gps1_lon_median),
                                                                       (self.gps2_lat_median, self.gps2_lon_median))

                self.prev_gps1_time = gps1_time
                self.prev_gps2_time = gps2_time

                self._parent.update(self.mean_bearing, self.median_bearing, self.gps1_lat_std,
                                    self.gps1_lon_std, self.gps2_lat_std, self.gps2_lon_std,
                                    self.gps1_lat_mean, self.gps1_lon_mean)

            except Exception as m:
                log.warning("Exception ignored in checker thread: \n{0}".format(m))
                traceback.print_exc(file=sys.stdout)
                time.sleep(1)
                pass

            time.sleep(0.12)


class GPSChecker(object):
    """Object to start the thread for calculating mean and median ship bearings"""
    def __init__(self, gps_managers):
        self.mean_bearing = 0.0
        self.median_bearing = 0.0
        self.avging_list_len = 70

        self.gps1_lat_mean = 0.0
        self.gps1_lon_mean = 0.0
        self.gps1_lat_std = []
        self.gps1_lon_std = []
        self.gps2_lat_std = []
        self.gps2_lon_std = []

        self.started = False

        self.gps_managers = gps_managers

        self.checker_observers = []
        self.checker_thread = None
        self.checker_lock = threading.Lock()

    def __del__(self):
        self.stop()

    def start(self):
        """Start the GPSChecker thread if not currently running"""
        if not self.started:
            self.started = True
            self.checker_thread = GPSCheckerThread(self, self.gps_managers)
            time.sleep(0.2)
            self.checker_observers.append(self.checker_thread)
        else:
            log.warn("GPS Checker thread alread started")

        self.checker_thread.start()
        log.info("Started GPS Checker thread")

    def stop(self):
        """Stop the GPSChecker thread"""
        log.info("Stopping GPS Checker thread")
        self.checker_lock.acquire(True)
        self.checker_thread.stop_checker_thread = True
        time.sleep(1)
        self.checker_thread.join(0.1)
        log.info("GPS Checker alive? = {}".format(self.checker_thread.is_alive()))
        self.started = False
        self.checker_lock.release()

    def update(self, mean_bearing, median_bearing, gps1_lat_std, gps1_lon_std, gps2_lat_std, gps2_lon_std, gps1_lat_mean, gps1_lon_mean):
        """Update the GPSChecker object values using the values passed in as arguments"""
        self.checker_lock.acquire(True)
        self.mean_bearing = mean_bearing
        self.median_bearing = median_bearing
        self.gps1_lat_std = gps1_lat_std
        self.gps1_lon_std = gps1_lon_std
        self.gps2_lat_std = gps2_lat_std
        self.gps2_lon_std = gps2_lon_std
        self.gps1_lat_mean = gps1_lat_mean
        self.gps1_lon_mean = gps1_lon_mean
        self.checker_lock.release()

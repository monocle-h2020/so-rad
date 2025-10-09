#!/usr/bin/python3
# -*- coding: utf-8 -*-
"""
Manager class to manage dataset generation for downloads by local users

Plymouth Marine Laboratory
License: see README.md
"""
import logging
import threading
import os
import sys
import time
import glob
import numpy as np
import datetime
import functions.redis_functions as rf
import functions.download_functions as df
from rq import Queue
from redis import Redis

# initiate logging
log = logging.getLogger('datasets')

# link to or create redis queue 'sorad_q'
sorad_q = Queue('sorad_q', connection=Redis())

class DatasetsManager(object):
    """
    Parseserver export manager: upload to remote server and automate generation of downloadable HDFs
    """
    def __init__(self, datasets_dict):
        """
        Initialise this class from a dictionary reflecting a section of the config file.
        : config_dict is a specific section [EXPORT] of the config file interpreted as a dictionary in initialisation.py
        """
        self.datasets_dict = datasets_dict

        self.use_downloads = datasets_dict['used']
        self.storage_path  = datasets_dict['storage_path']
        self.database_path = datasets_dict['database_path']
        self.platform_id   = datasets_dict['platform_id']
        self.platform_uuid = datasets_dict['platform_uuid']
        self.max_storage = datasets_dict['max_storage_gb']
        self.storage_protocol = datasets_dict['storage_protocol']

        self.stored_gb = None
        self.last_storage_check = None
        self.storage_check_interval_sec = 60
        self.check_storage()

        self.updated = None  # typically a datetime to indicate last time the class instance values were updated
        self.thread = None
        self.started = False
        self.stop_monitor = False
        self.sleep_interval = 1.0  # minimum interval between cycles
        self.hdf_creation_interval_mins = 60

        # on initialisation set the last hdf creation time to the top of the current hour
        self.last_hdf_requested = datetime.datetime.now().replace(minute=0, second=0, microsecond=0)

    def update_values(self):
        """
        docstring for update_values function
        """
        self.updated = datetime.datetime.now()
        return

    def __repr__(self):
        return f"Download Manager"

    def start(self):
        """
        Starts reading thread.
        """
        if not self.started:
            self.started = True
            self.thread = threading.Thread(target=self.run)  # use args = (arg1,arg2) if needed
            self.thread.start()
            log.info("Started Datasets Manager")
        else:
            log.warn("Could not start Datasets Manager")

    def stop(self):
        """
        Stop the sampling thread
        """
        log.info("Stopping Datasets manager")
        self.stop_monitor = True
        time.sleep(1*self.sleep_interval)
        log.info(self.thread)
        self.thread.join(2*self.sleep_interval)
        log.info("Datasets manager running = {0}".format(self.thread.is_alive()))
        self.started = False

    def __del__(self):
        self.stop()

    def check_storage(self):
        '''
        Check storage volume
        '''
        total_bytes = 0
        for file in os.listdir(self.storage_path):
            filepath = os.path.join(self.storage_path, file)
            if not os.path.islink(filepath):
                total_bytes += os.path.getsize(filepath)
        total_mb = total_bytes / 1024**2
        self.stored_gb = total_bytes / 1024**3
        self.last_storage_check = datetime.datetime.now()
        log.info(f"Total volume for downloadable datasets: {self.stored_gb:.3f} Gb ({total_mb:.3f} Mb)")
        # self.update_redis()

    def limit_storage(self):
        '''
        Limit used storage.
        Several methods may be implemented here.
        Currently we use a rolling archive: remove a number of files as needed to bring stored volume back below threshold, oldest files first.
        '''
        if self.storage_protocol == 'rolling_archive':
            filelist_csv = glob.glob(os.path.join(self.storage_path, '*.csv'))
            filelist_hdf = glob.glob(os.path.join(self.storage_path, '*.hdf'))
            filelist = np.array(filelist_csv + filelist_hdf)
            filedates = np.array([os.stat(f).st_mtime for f in filelist])
            filesizes = np.array([os.stat(f).st_size for f in filelist])
            filesizes_sorted = filesizes[np.argsort(filedates)]
            filelist_sorted = filelist[np.argsort(filedates)]

            excess_gb = self.stored_gb - self.max_storage
            removed_gb = 0
            log.info(f"Excess storage volume: {excess_gb} Gb")

            for f, s in zip(filelist_sorted, filesizes_sorted):
                removed_gb += s/1024**3
                log.info(f"Removing {f} to reduce stored dataset volume by {s/1024**3:.3f}Gb")
                os.remove(f)
                if removed_gb >= excess_gb:
                    break

            self.check_storage()

    def run(self):
        """
        Main loop of the thread.
        This will run and read new data and update the instance values.
        It will also monitor storage volumes and remove older datasets as needed.
        """
        log.info("Starting Datasets manager thread")
        export_result = None

        while not self.stop_monitor:

            # hdf generation
            if datetime.datetime.now() > (self.last_hdf_requested + datetime.timedelta(minutes=60)):
                try:
                    hdf_start_time = self.last_hdf_requested
                    hdf_end_time = self.last_hdf_requested.replace(minute=59, second=59, microsecond=999999)
                    log.info(f"Requesting HDF dataset from {hdf_start_time.isoformat()} to {hdf_end_time.isoformat()}")
                    job = sorad_q.enqueue(df.hdf_from_web_request, self.storage_path, self.database_path,
                                                                   hdf_start_time, hdf_end_time,
                                                                   self.platform_id, self.platform_uuid)
                    self.last_hdf_requested = datetime.datetime.now().replace(minute=0, second=0, microsecond=0)
                    log.info(job)
                except Exception as err:
                    log.exception(err)


            # check and adjust stored datasets volume periodically
            elif (self.last_storage_check is None) or \
                (self.last_storage_check < (datetime.datetime.now() -datetime.timedelta(seconds=self.storage_check_interval_sec))):

                self.check_storage()
                if self.stored_gb > self.max_storage:
                    log.info(f"Dataset store ({self.stored_gb:.3f} Gb) exceeds {self.max_storage:.3f} limit. Starting maintenance.")
                    self.limit_storage()

            # sleep for a standard period, ideally close to the refresh frequency
            time.sleep(self.sleep_interval)
            continue

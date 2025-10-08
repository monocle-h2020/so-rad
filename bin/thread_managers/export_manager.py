#!/usr/bin/python3
# -*- coding: utf-8 -*-
"""
Manager class to manage data uploads to parseserver

Plymouth Marine Laboratory
License: see README.md
"""
import logging
import threading
import sys
import time
import numpy as np
import datetime
import functions.redis_functions as rf
from functions.export_functions import run_export, update_status_parse_server, identify_new_local_records
from functions.check_functions import check_internet, check_remote_data_store
import functions.download_functions as df
from rq import Queue
from redis import Redis

# initiate logging
log = logging.getLogger('export')
# initiate redis connection
redis_client = rf.init()

# link to or create redis queue 'sorad_q'
sorad_q = Queue('sorad_q', connection=Redis())

class ParseExportManager(object):
    """
    Parseserver export manager
    """
    def __init__(self, export_dict, db_dict):
        """
        Initialise this class from a dictionary reflecting a section of the config file.
        : config_dict is a specific section [EXPORT] of the config file interpreted as a dictionary in initialisation.py
        """
        self.export_dict = export_dict
        self.db_dict = db_dict

        self.storage_path  = export_dict['storage_path']
        self.database_path = db_dict['file']

        self.updated = None  # typically a datetime to indicate last time the class instance values were updated
        self.thread = None
        self.started = False
        self.stop_monitor = False
        self.sleep_interval = 1.0  # minimum interval between cycles
        self.upload_interval = int(export_dict['data_upload_interval_sec'])
        self.status_update_interval = int(export_dict['status_update_interval_sec'])
        self.hdf_creation_interval_mins = 60
        self.connection_retry_interval = 300

        self.n_total = None
        self.n_not_inserted = None
        self.all_not_inserted = None

        # prime all timers
        self.last_db_check = datetime.datetime.now() - datetime.timedelta(seconds=self.upload_interval)
        self.last_status_update = datetime.datetime.now() - datetime.timedelta(seconds=self.status_update_interval)
        self.last_data_export = datetime.datetime.now() - datetime.timedelta(seconds=self.upload_interval)
        self.last_connectivity_check_time = datetime.datetime.now() - datetime.timedelta(seconds=self.connection_retry_interval)
        self.last_connectivity_check_result = False
        # on initialisation set the last hdf creation time to the top of the current hour
        self.last_hdf_requested = datetime.datetime.now().replace(minute=0, second=0, microsecond=0)

    def update_values(self):
        """
        docstring for update_values function
        """
        self.updated = datetime.datetime.now()
        return

    def __repr__(self):
        return f"Export Manager x: {x:0.2f} y: {y:0.2f} z: {z:0.2f}"

    def start(self):
        """
        Starts reading thread.
        """
        if not self.started:
            self.started = True
            self.thread = threading.Thread(target=self.run)  # use args = (arg1,arg2) if needed
            self.thread.start()
            log.info("Started Export Manager")
        else:
            log.warn("Could not start Export Manager")

    def stop(self):
        """
        Stop the sampling thread
        """
        log.info("Stopping Export manager")
        self.stop_monitor = True
        time.sleep(1*self.sleep_interval)
        log.info(self.thread)
        self.thread.join(2*self.sleep_interval)
        log.info("Export manager running = {0}".format(self.thread.is_alive()))
        self.started = False

    def __del__(self):
        self.stop()

    def run(self):
        """
        Main loop of the thread.
        This will run and read new data and update the instance values
        """
        log.info("Starting Export manager thread")
        export_result = None

        while not self.stop_monitor:

            # hdf generation
            if datetime.datetime.now() > (self.last_hdf_requested + datetime.timedelta(minutes=60)):
                try:
                    hdf_start_time = self.last_hdf_requested
                    hdf_end_time = self.last_hdf_requested.replace(minute=59, second=59, microsecond=999999)
                    log.info(f"Requesting HDF dataset from {hdf_start_time.isoformat()} to {hdf_end_time.isoformat()}")
                    platform_id = self.export_dict['platform_id']
                    platform_uuid = self.export_dict['platform_uuid']
                    job = sorad_q.enqueue(df.hdf_from_web_request, self.storage_path, self.database_path,
                                                                   hdf_start_time, hdf_end_time, platform_id, platform_uuid)
                    self.last_hdf_requested = datetime.datetime.now().replace(minute=0, second=0, microsecond=0)
                    log.info(job)
                except Exception as err:
                    log.exception(err)

            # check how many samples need uploading, upload a batch and check again
            if self.last_db_check + datetime.timedelta(seconds=self.upload_interval) < datetime.datetime.now():
                # check local db
                self.n_total, self.n_not_inserted, self.all_not_inserted = identify_new_local_records(self.db_dict, limit=0)
                self.last_db_check = datetime.datetime.now()

                if self.n_not_inserted > 0:
                    log.info(f"{self.n_not_inserted} samples pending upload")
                    rf.store(redis_client, 'samples_pending_upload', self.n_not_inserted, expires=30)

            # connectivity check
            if (not self.last_connectivity_check_result) and \
               (self.last_connectivity_check_time + datetime.timedelta(seconds=self.connection_retry_interval) < datetime.datetime.now()):
                # we didn't have a connection last time, and have waited the requisite interval before retrying
                if not check_internet():
                    log.info(f"Internet connection timed out. Retry in 300s")
                    rf.store(redis_client, 'upload_status', 'no_internet_connection', expires=30)
                    self.last_connectivity_check_result = False
                    self.last_connectivity_check_time = datetime.datetime.now()
                    time.sleep(self.sleep_interval)
                    continue
                else:
                    log.info(f"Internet connection restored.")
                    self.last_connectivity_check_result = True
                    self.last_connectivity_check_time = datetime.datetime.now()
            elif not self.last_connectivity_check_result:
                time.sleep(self.sleep_interval)
                continue

            # system status upload
            if self.last_status_update + datetime.timedelta(seconds=self.status_update_interval) < datetime.datetime.now():
                if check_remote_data_store(self.export_dict)[0]:
                    self.last_connectivity_check_result = True
                    self.last_connectivity_check_time = datetime.datetime.now()
                    export_result, resultcode = update_status_parse_server(self.export_dict, self.db_dict)
                    sucorfail = {True: 'succeeded', False:'failed'}[export_result]
                    log.info(f"Instrument status update on remote server {sucorfail}")
                    if export_result:
                        rf.store(redis_client, 'upload_status', 'remote_status_updated', expires=30)
                    self.last_status_update = datetime.datetime.now()
                else:
                    log.info(f"No connection to remote server to update instrument status. Retry in 300s")
                    rf.store(redis_client, 'upload_status', 'no_connection_to_server', expires=30)
                    self.last_connectivity_check_result = False
                    self.last_connectivity_check_time = datetime.datetime.now()
                    time.sleep(self.sleep_interval)
                    continue
            else:
                time.sleep(self.sleep_interval)
                continue

            # data upload, unless an export/update just failed
            if (self.n_not_inserted > 0) and \
                  (export_result in [True, None]) and \
                  (self.last_data_export + datetime.timedelta(seconds=self.upload_interval) < datetime.datetime.now()):

                if check_remote_data_store(self.export_dict)[0]:
                    self.last_connectivity_check_result = True
                    self.last_connectivity_check_time = datetime.datetime.now()
                    while (self.n_not_inserted > 0) and (export_result) and (not self.stop_monitor):
                        # upload data until no more samples remain or an upload fails.
                        log.debug("Uploading latest 10 samples ({n_not_inserted} pending)")
                        export_result, resultcode, successes = run_export(self.export_dict, self.db_dict, limit=10, test_run=False, fail_limit=3)
                        log.info(f"{successes} sensor records uploaded. Request completed: {export_result}")
                        if export_result:
                            rf.store(redis_client, 'upload_status', f'{successes}_records_uploaded', expires=30)
                        self.n_total, self.n_not_inserted, self.all_not_inserted = identify_new_local_records(self.db_dict, limit=0)
                        rf.store(redis_client, 'samples_pending_upload', self.n_not_inserted, expires=30)
                        time.sleep(0.05)
                    self.last_data_export = datetime.datetime.now()
                else:
                    log.debug(f"No connection to remote server. Retry in 300s")
                    rf.store(redis_client, 'upload_status', 'no_connection', expires=30)
                    self.last_connectivity_check_result = False
                    self.last_connectivity_check_time = datetime.datetime.now()
                    time.sleep(self.sleep_interval)

            else:
                rf.store(redis_client, 'upload_status', 'idle', expires=30)

            # sleep for a standard period, ideally close to the refresh frequency
            time.sleep(self.sleep_interval)
            continue

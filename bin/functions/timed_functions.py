#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Timed functions are a collection of maintenance functions that are called at set intervals,
and do not form part of a larger collection of functions related to data collection, storage, etc.

The following functions are currently specified (* means it is in place):
* Check clock drift and set/sync hardware and system clocks from GPS input
- Check and report (via redis) the size of the database
- Check and report (via redis) data transfer rates

"""
import os
import sys
import logging
import datetime
from functions import redis_functions as rf

redis_client = rf.init()
log = logging.getLogger('timed')
#log.setLevel('DEBUG')

def sync_clocks():
    """
    Compare most recent GPS and System time and sync accordingly.
    The GPS manager writes location/time info to Redis, which gets timestamped.
    We must record the last time we synced and only sync again if we have a newer input via redis.

    NTP is likely more reliable if the system is online:
    - GPS refresh frequency is ~1s
    - NTP drift gets corrected in the microsecond range
    -> Allow a high drift threshold (> 3s) before any correction is made.

    Procedure:
    - obtain most recent GPS record via redis
    - compare the system time of the update with the GPS time
    - ensure the system time was relatively recent - if not:
      -- we may not have a recent GPS record
      -- a correction has already been made via NTP
    - calculate the drift
    - if drift exceeds threshold, set hwclock and sync system clock:
       sudo hwclock --set --date="2012-12-15 20:49:00"
       # synchronize:
       sudo hwclock -s

    """
    latest_gps, latest_gps_updated, fresh = rf.retrieve(client, key, freshness=5)
    log.info(f"Latest gps: {latest_gps} updated at {latest_gps_updated}. Recent: {fresh}")

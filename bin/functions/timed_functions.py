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
from numpy import sign
import subprocess

redis_client = rf.init()
log = logging.getLogger('timed')

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
    latest_gps, latest_gps_updated, expired = rf.retrieve(redis_client, 'gps_manager', freshness=5)

    # Check that system timezone is UTC or Etc/UTC
    timezone_name = datetime.datetime.now(datetime.datetime.now().astimezone().tzinfo).tzname()
    if 'UTC' not in timezone_name:
        log.error(f"Not implemented: local timezone is {timezone_name}, expecting 'UTC'")
        return

    if expired:
        log.debug(f"Latest gps update is from {latest_gps_updated}. No action taken.")
        return
    elif not expired:
        log.debug(f"Latest gps timestamp: {latest_gps['datetime']} updated at {latest_gps_updated}. Proceed.")

    # get sync offset in seconds
    delta = latest_gps['last_update'] - latest_gps['datetime']  # system time vs gps time at time of update, +ve means system is ahead
    delta_s = delta.total_seconds()

    if abs(delta_s) > 3.0:
        if sign(delta_s) > 0:
            log.info(f"System clock is {abs(delta_s)} ahead of GPS. Synchronizing.")
        else:
            log.info(f"System clock is {abs(delta_s)} behind GPS. Synchronizing")

        # adjust the hwclock
        target_time = datetime.datetime.now() - datetime.timedelta(seconds=delta_s)
        target_str = datetime.datetime.strftime(target_time, "%Y-%m-%d %H:%M:%S")
        log.info(f"Set system time to {target_str}")
        cmd = f"sudo timedatectl --no-ask-password set-ntp false; sudo timedatectl --no-ask-password set-time '{target_str}'; sudo timedatectl --no-ask-password set-ntp true"
        proc = subprocess.run(cmd, shell=True, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        log.debug(proc.stdout)
        log.debug(proc.stderr)
        log.info(f"System time adjusted by {delta_s} s")

    else:
        log.debug(f"System clock is within {abs(delta_s)} from GPS.")


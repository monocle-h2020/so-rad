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
from redis import Redis

redis_client = rf.init()
log = logging.getLogger('timed')
#log.setLevel('DEBUG')


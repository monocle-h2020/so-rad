#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Monitoring system values using in-memory database

These functions send and retrieve system information to a redis instance
so it can be retrieved in multiple scopes.

Warning: all objects are converted to str when passed to redis.
This is not lossless. Use this for system health monitoring rather than data collection.

"""

import os
import sys
import logging
import time
import datetime
import redis

TIMEOUT=5  # timeout for getting a response on data upload. 
TIMEOUT_SHORT = 1 # timeout for getting response on connectivity tests, status queries

log = logging.getLogger('redis')
#log.setLevel('DEBUG')

def nptobase(x):
    """
    State base python dtype equivalent to a numpy dtype where possible
    """
    try:
       x = x.item()
    except Exception as msg:
        log.debug(msg)
        pass

    return x


def init(host='localhost', port=6379):
    """
    Set up client to speak to Redis service
    """
    try:
        client = redis.StrictRedis(host='localhost', port=port, db=0)
        client.set("client_updated", datetime.datetime.now().isoformat())
        client.set("client_updated_dtype", "datetime")

    except Exception as msg:
        log.exception("Redis not available")
        return None

    return client


def retrieve(client, key, freshness=30):
    """
    Retrieve values from redis by key

    : client     Redis client configured using init function
    : key        Name of the redis object
    : freshness  Time in seconds to consider the value sufficiently recent.
                 Return None and log a warning if this window has elapsed.
                 If freshness = None, a value will be returned if a value
                 exist for the key. However, if the elapsed time exceeds
                 the expires attribute, a warning will be logged.
                 To prevent using expired values, freshness should be set
                 regardless of what the expires attribute states, as the
                 threshold for this condition may vary between uses.
    """

    value = client.get(key).decode('utf-8')

    dtype = client.get(f"{key}_dtype").decode('utf-8')
    if dtype == "float":
        value = float(value)
    elif dtype == "int":
        value = int(value)
    elif dtype == "str":
        value = str(value)
    elif dtype == "datetime":
        value = datetime.datetime.strptime(value, "%Y-%m-%dT%H:%M:%S.%f")
    else:
        log.warning(f"reading dtype {dtype} not implemented")

    updated = client.get(f"{key}_updated").decode('utf-8')
    updated = datetime.datetime.strptime(updated, "%Y-%m-%dT%H:%M:%S.%f")
    expires = int(client.get(f"{key}_expires").decode('utf-8'))

    log.debug(f"Freshness: {freshness} | Expiry: {expires}")
    log.debug(f"Age in s: {(datetime.datetime.now() - updated).total_seconds()}")

    if (freshness is not None) and ((datetime.datetime.now() - updated).total_seconds() > freshness):
        log.warning(f"Stale value {key} = {value} ignored.")
        return None, updated

    elif (freshness is None) and ((datetime.datetime.now() - updated).total_seconds() > expires):
        log.warning(f"Stale value {key} = {value} passed because freshness threshold is not set.")
        return value, updated

    return value, updated


def store(client, key, value, expires=30):
    """
    Store values in redis by key

    : client     Redis client configured using init function
    : key        Name of the redis object
    : value      Value for the key, must be float, str, int or datetime or a numpy equivalent
    : expires    Time in seconds to consider the value sufficiently recent.
                 Retrieving the key/value will throw a warning if this time has expired.
    """
    value = nptobase(value)

    if isinstance(value, float):
        client.set(f"{key}_dtype", "float")
    elif isinstance(value, str):
        client.set(f"{key}_dtype", "str")
    elif isinstance(value, int):
        client.set(f"{key}_dtype", "int")
    elif isinstance(value, datetime.datetime):
        client.set(f"{key}_dtype", "datetime")
    else:
        log.warning(f"Setting dtype {type(value)} not implemented")

    if isinstance(value, datetime.datetime):
        client.set(key, value.isoformat())
    else:
        client.set(key, str(value))

    client.set(f"{key}_updated", datetime.datetime.now().isoformat())
    client.set(f"{key}_expires", str(int(expires)))
    client.set(f"client_updated", datetime.datetime.now().isoformat())


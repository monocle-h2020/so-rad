#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Monitoring system values using in-memory database

These functions send and retrieve system information to a redis instance
so it can be retrieved in multiple scopes.

Warning: standard objects are converted to str when passed to redis.
This is not lossless. Use this for health monitoring rather than data collection.
To preserve integrity, provide tuples, dicts or lists as these will be pickled/unpickled.
"""

import os
import sys
import logging
import time
import datetime
import redis
import pickle

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

    dtype = client.get(f"{key}_dtype")
    if dtype is None:
        log.warning(f"Key {key} not registerd in redis")
        return None, None, None
    dtype = dtype.decode('utf-8')
    value = client.get(key)

    updated = client.get(f"{key}_updated").decode('utf-8')
    updated = datetime.datetime.strptime(updated, "%Y-%m-%dT%H:%M:%S.%f")
    expires = int(client.get(f"{key}_expires").decode('utf-8'))

    log.debug(f"Freshness: {freshness} | Expiry: {expires}")
    log.debug(f"Age in s: {(datetime.datetime.now() - updated).total_seconds()}")

    if dtype in ['float', 'int', 'str', 'datetime']:
        value = value.decode('utf-8')

    if dtype == "float":
        value = float(value)
    elif dtype == "int":
        value = int(value)
    elif dtype == "str":
        value = str(value)
    elif dtype == "datetime":
        value = datetime.datetime.strptime(value, "%Y-%m-%dT%H:%M:%S.%f")
    elif dtype == "pickle":
        value = pickle.loads(client.get(key))
    else:
        log.warning(f"reading dtype {dtype} not implemented")
        return None, updated, None

    if (freshness is not None) and ((datetime.datetime.now() - updated).total_seconds() > freshness):
        log.debug(f"Stale value {key} = {value} ignored.")
        return None, updated, True

    elif (freshness is None) and ((datetime.datetime.now() - updated).total_seconds() > expires):
        log.debug(f"Stale value {key} = {value} passed because freshness threshold is not set.")
        return value, updated, True

    return value, updated, False


def store(client, key, value, expires=30):
    """
    Store values in redis by key

    : client     Redis client configured using init function
    : key        Name of the redis object
    : value      Value for the key, must be float, str, int, datetime or a numpy equivalent.
                 Any other type will be pickled.
    : expires    Time in seconds to consider the value sufficiently recent.
                 Retrieving the key/value will throw a warning if this time has expired.
    """
    # deal with any numpy dtypes
    value = nptobase(value)
    pickleit = False

    if isinstance(value, float):
        client.set(f"{key}_dtype", "float")
    elif isinstance(value, str):
        client.set(f"{key}_dtype", "str")
    elif isinstance(value, int):
        client.set(f"{key}_dtype", "int")
    elif isinstance(value, datetime.datetime):
        client.set(f"{key}_dtype", "datetime")
    elif (isinstance(value, list)) or (isinstance(value, tuple)) or \
         (isinstance(value, dict)) or (isinstance(value, np.array)):
        client.set(f"{key}_dtype", "pickle")
        pickleit=True
    else:
        log.warning(f"Setting dtype {type(value)} not implemented")

    if isinstance(value, datetime.datetime):
        client.set(key, value.isoformat())
    elif pickleit:
        client.set(key, pickle.dumps(value))
    else:
        client.set(key, str(value))

    client.set(f"{key}_updated", datetime.datetime.now().isoformat())
    client.set(f"{key}_expires", str(int(expires)))
    client.set(f"client_updated", datetime.datetime.now().isoformat())


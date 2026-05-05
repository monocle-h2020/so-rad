#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Connect to db to provide latest activity from solar tracking radiometry platform (So-Rad).
"""
import redis
import pickle
import datetime


def redis_init(host='localhost', port=6379):
    """
    Set up client to speak to Redis service
    """
    try:
        client = redis.StrictRedis(host='localhost', port=port, db=0)
        client.set("client_updated", datetime.datetime.now().isoformat())
        client.set("client_updated_dtype", "datetime")

    except Exception as msg:
        print("Redis not available")
        return None

    return client


def redis_retrieve(client, key, freshness=30):
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
        return None, None
    dtype = dtype.decode('utf-8')
    value = client.get(key)


    updated = client.get(f"{key}_updated").decode('utf-8')
    updated = datetime.datetime.strptime(updated, "%Y-%m-%dT%H:%M:%S.%f")
    expires = int(client.get(f"{key}_expires").decode('utf-8'))

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
        return None, updated

    if (freshness is not None) and ((datetime.datetime.now() - updated).total_seconds() > freshness):
        return None, updated
    elif (freshness is None) and ((datetime.datetime.now() - updated).total_seconds() > expires):
        return value, updated

    return value, updated

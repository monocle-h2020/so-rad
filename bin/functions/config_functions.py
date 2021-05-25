#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""

Autonomous operation of hyperspectral radiometers with optional rotating measurement platform, solar power supply and remote connectivity

Plymouth Marine Laboratory

Functions to read and update instrument configuration files
"""
import configparser
import logging


def read_config(config_file, local_config_file=None):
    """Opens and reads the config file

    :param config_file: the config.ini file
    :type config_file: file
    :return: dictionary of the config file's contents
    :rtype: dictionary
    """
    config = configparser.ConfigParser()
    config.read(config_file)
    return config


def update_config(config, local_config_file=None):
    """replace any default config values with local overrides"""
    log = logging.getLogger()
    if local_config_file is None:
        return config

    local = configparser.ConfigParser()
    local.read(local_config_file)
    for section in local.sections():
        if len(local[section].items()) > 0:
            for key, val in local[section].items():
                if section in ['EXPORT']:
                    # keep these values out of the log files
                    log.info("Local config override: {0}-{1} {2}>{3}"\
                             .format(section, key, config[section][key], '(hidden)'))
                else:
                    log.info("Local config override: {0}-{1} {2}>{3}"\
                             .format(section, key, config[section][key], val))
                config[section][key] = val
    return config


def read_remote_config(remote_config_file):
    """read a remotely retrieved config file and override selected local settings"""
    # WIP
    return

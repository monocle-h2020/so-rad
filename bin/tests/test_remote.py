#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
A simple test to check TriOS Radiometer connectivity.
@author: stsi
"""
import sys
import os
import inspect
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(inspect.getfile(inspect.currentframe())))))
from main_app import parse_args
from functions.check_functions import check_internet, check_remote_data_store
import functions.config_functions as cf

def run_test(conf):
    """Test connectivity to internet and remote stores"""
    result = check_internet()
    print(f"Internet connection: {result}")

    result = check_remote_data_store(conf)
    print(f"Remote store connection: {result}")


if __name__ == '__main__':
    args = parse_args()
    conf = cf.read_config(args.config_file)
    conf = cf.update_config(conf, args.local_config_file)
    run_test(conf)

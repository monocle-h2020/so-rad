#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
A simple test to check connectivity to the database
"""
import os
import sys
import inspect
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(inspect.getfile(inspect.currentframe())))))
import initialisation
from main_app import parse_args
from functions import db_functions
import functions.config_functions as cf


if __name__ == '__main__':
    args = parse_args()
    conf = cf.read_config(args.config_file)
    conf = cf.update_config(conf, args.local_config_file)

    try:
        db_dict = initialisation.db_init(conf['DATABASE'])
        conn, cur = db_functions.connect_db(db_dict)
    except:
        raise
        sys.exit(1)
    print("Succesfully connected to database")

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
import main_app
from functions import db_functions

if __name__ == '__main__':
    args = main_app.parse_args()
    conf = main_app.read_config(args.config_file)
    db_dict = initialisation.db_init(conf['DATABASE'])
    conn, cur = db_functions.connect_db(db_dict)

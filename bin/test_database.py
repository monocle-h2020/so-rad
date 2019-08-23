#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test database setup
"""
import initialisation
import main_app
from functions import db_functions

if __name__ == '__main__':
    args = main_app.parse_args()
    conf = main_app.read_config(args.config_file)
    db_dict = initialisation.db_init(conf['DATABASE'])
    conn, cur = db_functions.connect_db(db_dict)

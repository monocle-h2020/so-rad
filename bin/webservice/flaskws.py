#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Connect to db to provide latest activity from solar tracking radiometry platform (SO-RAD).
"""

from flask import Flask, Blueprint, render_template, abort
from jinja2 import TemplateNotFound
import sqlite3
import configparser
import sys
import os

def read_config(config_file):
    config = configparser.ConfigParser()
    config.read(config_file)
    return config


# allow config file to be found from working dir, parent dir or command line arg to allow different ways to start this script
if os.path.isfile("config.ini"):
    conf = read_config("config.ini")
elif os.path.isfile("../config.ini"):
    conf = read_config("../config.ini")
else:
    conf = read_config(sys.argv[1])

log_file_location = conf['LOGGING'].get('log_file_location')
db_path = conf['DATABASE'].get('database_path')

status_page = Blueprint('status_page', __name__,
                        template_folder='templates')
log_page = Blueprint('log_page', __name__,
                        template_folder='templates')
log_full_page = Blueprint('log_full_page', __name__,
                        template_folder='templates')

@status_page.route('/')
def show_status():
    try:
        rows = get_one_row_from_db(db_path)
        return render_template('welcome.html', message=rows)

    except TemplateNotFound:
        abort(404)
    except Exception:
        abort(404)

@log_page.route('/log')
def show_log():
    try:
        with open(log_file_location, 'r') as logfile:
            rows = logfile.readlines()
        if len(rows) > 100:
            rows = rows[-100:]
        rows.reverse()
        return render_template('log.html', message=rows)

    except TemplateNotFound:
        abort(404)
    except Exception:
        abort(404)

@log_full_page.route('/logfull')
def show_full_log():
    try:
        with open(log_file_location, 'r') as logfile:
            rows = logfile.readlines()
        rows.reverse()
        return render_template('log.html', message=rows)

    except TemplateNotFound:
        abort(404)
    except Exception:
        abort(404)

def get_one_row_from_db(db_path):
    conn = sqlite3.connect(db_path)
    cursor=conn.cursor()
    cursor.execute("SELECT * FROM (SELECT * FROM sorad_metadata ORDER BY id_ DESC LIMIT 10) ORDER BY id_ ASC;")
    return cursor.fetchall()

app = Flask(__name__)
app.register_blueprint(status_page)
app.register_blueprint(log_page)
app.register_blueprint(log_full_page)

if __name__=='__main__':
    app.run(host='0.0.0.0', port=8080, debug=False)

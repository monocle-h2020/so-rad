#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Connect to db to provide latest activity from solar tracking radiometry platform (SO-RAD).
"""

from flask import Flask, render_template, abort, flash, redirect, url_for, request
#from flask import Blueprint
from jinja2 import TemplateNotFound
import sqlite3
import configparser
import sys
import os
from forms import LoginForm
from flask_login import LoginManager, current_user, login_user, logout_user, UserMixin, login_required
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.urls import url_parse
import uuid
from math import sin, cos, radians

def read_config():
    """uses local conf and global config_file objects"""
    config = configparser.ConfigParser()
    config.read(config_file)
    return config

def update_config():
    """replace any default config values with local overrides"""
    if local_config_file is None:
        return conf

    local = configparser.ConfigParser()
    local.read(local_config_file)
    for section in local.sections():
        if len(local[section].items()) > 0:
            for key, val in local[section].items():
                conf[section][key] = val

# define environment
# find config.ini
if os.path.isfile("config.ini"):
    config_file = "./config.ini"
elif os.path.isfile("../config.ini"):
    config_file = "../config.ini"
else:
    config_file = sys.argv[1]
# find config-local.ini
if os.path.isfile("config-local.ini"):
    local_config_file = "config-local.ini"
elif os.path.isfile("../config-local.ini"):
    local_config_file = "../config-local.ini"
else:
    local_config_file = sys.argv[2]

global conf
conf = read_config()
update_config()

log_file_location = conf['LOGGING'].get('log_file_location')
db_path = conf['DATABASE'].get('database_path')

global common
common = {}  # store some elements that are common to all pages

def update_common_items():
    global common
    common['platform_id']  = conf['EXPORT']['platform_id']
    common['platform_uuid'] = conf['EXPORT']['platform_uuid']
    common['home_pos'] = float(conf['MOTOR']['home_pos'])
    common['cw_limit_deg'] = float(conf['MOTOR']['cw_limit_deg'])
    common['ccw_limit_deg'] = float(conf['MOTOR']['ccw_limit_deg'])
    common['nrows'] = 100
    return

update_common_items()

def save_updates_to_local_config(updates):
    """called by settings page when new values are provided"""
    newtext = ""
    with open(local_config_file, "r") as lcf:
        for line in lcf:
            for key, val in updates.items():
                update = f"{key} = {val}"
                if line.find(key) == 0:
                    print(f"To update: {update}")
                    line = update + "\n"
                    flash(f"Updated {key} in local config: {update}")
            newtext = newtext + line

    with open(local_config_file, "w") as lcfout:
        try:
            lcfout.write(newtext)
            flash("Written new local config file")
        except Exception as err:
            flash(f"Failed to write local config file: {err}")

    # need to re-read config file somehow and make conf global
    update_config()
    update_common_items()
    return

# users
class User(UserMixin):
    def __init__(self, name, hash):
        self.id = str(uuid.uuid1())
        self.name = name
        self.hash = hash

    def check_password(self, password):
        return check_password_hash(self.hash, password)

    def __repr__(self):
        #return f"<User {self.name}>"
        return f"<User {self.name}> id {self.id} hash {self.hash}"

admin_hash = os.environ.get('admin_hash')
users = {'admin': User('admin', admin_hash)}




# define app
app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY')
login = LoginManager(app)
login.login_view = 'login'


# user selector required by login
@login.user_loader
def load_user(id):
    for u, k in users.items():
        if k.id == id:
            return k
    return None



# define functions used by routes below

def read_log(log_file_location, n=100, reverse=True):
    """Read the last n lines from a logfile"""
    if not os.path.exists(log_file_location):
        return None
    if n is None:
        with open(log_file_location, 'r') as logfile:
            rows = logfile.readlines()
        if reverse:
            rows.reverse()
        return rows
    rows = []
    if reverse:
        bufsize = 1024
        fsize = os.stat(log_file_location).st_size
        iter = 0
        with open(log_file_location, 'r+') as logfile:
            if bufsize > fsize:
                bufsize = fsize-1
            while True:
                iter += 1
                logfile.seek(fsize-bufsize * iter)
                rows.extend(logfile.readlines())
                if len(rows) >= n or logfile.tell() == 0:
                    break
        rows.reverse()
        rows = rows[0:n]
        return rows
    with open(log_file_location, 'r') as logfile:
        nn=0
        while nn < n:
            row = logfile.readline()
            if not row:
                break
            rows.append(logfile.readline())
            nn+=1
    return rows


def log2dict(line, values={}):
    """Update a dictionary from lines in the log file. This should perhaps be threaded rather than called on request."""
    try:
        logtype = line.split(' ')[5]
        if logtype not in ['INFO']:
            return values
        values['datestr'] = line.split(' ')[0].strip()
        values['timestr'] = line.split(' ')[1].strip()

        values['batt_ok'] = line.split('Bat')[1].split(' ')[1].strip()
        values['gps_ok'] = line.split('GPS')[1].split(' ')[1].strip()
        values['heading_ok'] = line.split('Head')[1].split(' ')[1].strip()
        values['rad_ok'] = line.split('Rad')[1].split(' ')[1].strip()
        values['speed_ok'] = line.split('Spd')[1].split(' ')[1].strip()
        values['motor_ok'] = line.split('Motor')[1].split(' ')[1].strip()
        values['motor_alarm'] = line.split('Motor')[1].split(' ')[2].strip('() ')
        values['sun_elevation_ok'] = line.split('Sun')[1].split(' ')[1].strip()

        values['sun_elevation'] =    line.split('Sun')[1].split(' ')[2].strip('() ')
        values['tilt'] = line.split('Tilt')[1].split(' ')[1].strip()
        values['sun_azimuth'] = line.split('SunAz')[1].split(' ')[1].strip()
        values['ship_heading'] = line.split('Ship')[1].split(' ')[1].strip()
        values['motor_heading'] = line.split('Ship')[1].split(' ')[3].strip('|')

        values['fix'] = line.split('Fix')[1].split(' ')[1].strip()
        values['nsat'] = line.split('Fix')[1].split(' ')[2].split('(')[1].strip()

        values['relviewaz'] = line.split('RelViewAz')[1].split(' ')[1].strip()

        values['latitude'] = line.split('loc')[1].split(' ')[1].strip()
        values['longitude'] = line.split('loc')[1].split(' ')[2].strip()

    except ValueError:
        # probably the wrong log line, so stop parsing here
        return values

    return values


def get_from_db(db_path, n=10):
    """return last n rows from database"""
    if not os.path.exists(db_path):
        return None
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor=conn.cursor()
    cursor.execute(f"SELECT * FROM sorad_metadata ORDER BY id_ DESC LIMIT {int(n)}")
    results = cursor.fetchall()
    if len(results) == 0:
        return None, None
    conn.close()
    return results

def restart_service(service):
    "restart a systemd service"
    return

def stop_service(service):
    "stop a systemd service"
    return

def service_status(service):
    "display system service status"
    assert ' ' not in service  # 1 word allowed
    status = os.system(f"service status {service}")
    if status == '0':
        return True
    else:
        return False

def run_test(test):
    "Run a system test"
    return


# pass math functions to jinja2
@app.context_processor
def utility_processor():
    return dict(cos=cos, sin=sin, radians=radians)



####  ROUTES  ####

# define routes
@app.route('/', methods=['GET', 'POST'])
@app.route('/index', methods=['GET', 'POST'])
def index():
    """Home page showing instrument status"""
    try:
        if request.method == 'POST':
            common['nrows'] = int(request.form['nrows'])
            if 'All' in request.form.keys():
                common['nrows'] = None
            elif '100' in request.form.keys():
                common['nrows'] = 100
            if common['nrows'] == 0:
                common['nrows'] = 1

        errormessage = False

        # info from log
        logrows = read_log(log_file_location, n=common['nrows'], reverse=True)
        if logrows is not None and len(logrows) > 0:
            common['nrows'] = len(logrows)
            logvalues = []
            for logrow in logrows:
                if 'Sun' in logrow:
                    logvalues.append(log2dict(logrow))

            labels = [logrow['timestr'] for logrow in logvalues]
            timeseries = {
                'sun_azimuth':   [float(logrow['sun_azimuth']) for logrow in logvalues],
                'motor_heading': [float(logrow['motor_heading']) for logrow in logvalues],
                'ship_heading':  [float(logrow['ship_heading']) for logrow in logvalues],
                'relviewaz':     [float(logrow['relviewaz']) for logrow in logvalues],
                'sensoraz':      [float(logrow['sun_azimuth']) + float(logrow['relviewaz']) for logrow in logvalues],
                'cw_limit':      [float(logrow['ship_heading']) + common['home_pos'] + common['cw_limit_deg'] for logrow in logvalues],
                'ccw_limit':     [float(logrow['ship_heading']) + common['home_pos'] - common['cw_limit_deg'] for logrow in logvalues]
            }
        else:
            flash("Log file not found.")
            errormessage = True

        # info from db
        dbrows = get_from_db(db_path, n=1)
        if dbrows is not None and len(dbrows) > 0:
            dbtable = dict(dbrows[0])
        else:
            flash("Database file not found or database empty.")
            errormessage = True

        # read so-rad status
        common['so-rad_status'] = service_status('so-rad')
        print(common['so-rad_status'])

        if errormessage:
            return render_template('layout.html', message = '', common=common)
        else:
            return render_template('status.html', logvalues=logvalues, dbtable=dbtable,
                               labels=labels, timeseries=timeseries, common=common)

    except Exception as msg:
        return msg


@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    form = LoginForm()
    if form.validate_on_submit():
        if form.username.data in users.keys():
            user = users[form.username.data]
        else:
            flash('Invalid username or password')
            return redirect(url_for('login'))
        if (form.username.data is None) or (not user.check_password(form.password.data)):
            flash('Invalid username or password')
            return redirect(url_for('login'))
        login_user(user, remember=form.remember_me.data)
        next_page = request.args.get('next')
        if not next_page or url_parse(next_page).netloc != '':
            next_page = url_for('index')
        return redirect(next_page)
    return render_template('login.html', title='Sign In', form=form, common=common)


@app.route('/database')
def database():
    """Show latest db entries"""
    try:
        # info from db
        dbrows = get_from_db(db_path, 10)
        if dbrows is not None and len(dbrows) > 0:
            dbtable = [dict(dbrow) for dbrow in dbrows]
            return render_template('database.html', dbtable=dbtable, common=common)
        else:
            flash("Database file not found or database empty.")
            return render_template('layout.html', message = '', common=common)

    except Exception as msg:
        return msg

@app.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('index'))


def collect_settings_formdata():
    """allow some system configurations to be updated through the web interface"""
    formdata = {
                'ccw_limit_deg': {'label':     'Counter-clockwise turn limit',
                                  'setting':   int(conf['MOTOR']['ccw_limit_deg']),
                                  'postlabel': 'degrees',
                                  'comment':   'positive or negative, must be smaller than cw_limit',
                                  'min':       -180,
                                  'max':       180},
                'cw_limit_deg':  {'label':     'Clockwise turn limit',
                                  'setting':   int(conf['MOTOR']['cw_limit_deg']),
                                  'postlabel': 'degrees',
                                  'comment':   'positive or negative, must be greater than ccw_limit',
                                  'min':       -180,
                                  'max':       180},
                'home_pos':      {'label':     'Motor home to platform axis offset',
                                  'setting':   int(conf['MOTOR']['home_pos']),
                                  'postlabel': 'degrees',
                                  'comment':    'normally 0 (motor aligned with platform forward heading)',
                                  'min':       -180,
                                  'max':       180},
                'gps_offset':     {'label':    'GPS receivers to platform axis offset',
                                  'setting':   int(conf['GPS']['gps_heading_correction']),
                                  'postlabel': 'degrees',
                                  'comment':   'normally 0 or 90',
                                  'min':       -180,
                                  'max':       180},
                'sampling_speed_limit':
                                  {'label':    'Minimum speed to allow sampling',
                                  'setting':   float(conf['SAMPLING']['sampling_speed_limit']),
                                  'postlabel': 'kn',
                                  'comment':   '0 = no minimum speed',
                                  'min':       0,
                                  'max':       999},
                'solar_elevation_limit':
                                  {'label':    'Minimum sun elevation to allow sampling',
                                  'setting':   float(conf['SAMPLING']['solar_elevation_limit']),
                                  'postlabel': 'degrees',
                                  'comment':   'normally 30. Allowed range [-90, 90]',
                                  'min':       -90,
                                  'max':       90},
                'sampling_interval':
                                  {'label':    'Interval between radiometric observations',
                                  'setting':   int(conf['RADIOMETERS']['sampling_interval']),
                                  'postlabel': 'seconds',
                                  'comment':   'Normally >= 15 s',
                                  'min':       10,
                                  'max':       99999}
         }
    return formdata

@app.route('/settings', methods=['GET', 'POST'])
@login_required
def settings():
    forminput = {}
    global conf

    try:
        formdata = collect_settings_formdata()

        if request.method == 'POST':
            print(request.form)
            try:
                forminput['ccw_limit_deg'] = int(request.form['ccw_limit_deg'])
                forminput['cw_limit_deg']  = int(request.form['cw_limit_deg'])
                forminput['home_pos']      = int(request.form['home_pos'])
                forminput['gps_offset']    = int(request.form['gps_offset'])
                forminput['sampling_speed_limit']  = float(request.form['sampling_speed_limit'])
                forminput['solar_elevation_limit'] = float(request.form['solar_elevation_limit'])
                forminput['sampling_interval']     = int(request.form['sampling_interval'])
            except Exception:
                raise

            print(forminput)
            # process any updates
            updates = {}
            for key, val in formdata.items():
                if forminput[key] != formdata[key]['setting']:
                    vmin = formdata[key]['min']
                    vmax = formdata[key]['max']
                    if (forminput[key] > vmax) or (forminput[key] < vmin):
                        flash(f"The value for {key} must be in the range {vmin} - {vmax}")
                    else:
                        flash(f"A new value for {key} was provided: {forminput[key]}")
                        updates[key] = forminput[key]
            if len(updates) > 0:
                save_updates_to_local_config(updates)

            formdata = collect_settings_formdata()

        return render_template('settings.html', formdata=formdata, common=common)

    except Exception as err:
        return f"An unexpected error occurred handling your request: {err}"


#@log_full_page.route('/log')
@app.route('/log', methods=['GET', 'POST'])
def log():
    try:
        if request.method == 'POST':
            common['nrows'] = int(request.form['nrows'])
            if 'All' in request.form.keys():
                common['nrows'] = None
            elif '100' in request.form.keys():
                common['nrows'] = 100
            if common['nrows'] == 0:
                common['nrows'] =1

        rows = read_log(log_file_location, n=common['nrows'], reverse=True)
        if rows is not None and len(rows) > 0:
            common['nrows'] = len(rows)
            return render_template('log.html', message=rows, common=common)
        else:
            flash("Log file not found.")
            return render_template('layout.html', message = '', common=common)

    except Exception as err:
        return f"An unexpected error occurred handling your request: {err}"


if __name__=='__main__':
    app.run(host='0.0.0.0', port=8080, debug=True)

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Connect to db to provide latest activity from solar tracking radiometry platform (So-Rad).
"""

from flask import Flask, render_template, abort, \
                  flash, redirect, url_for, request,\
                  Markup, jsonify, send_file
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
import datetime
import subprocess
import redis
import pickle
from PIL import Image
import glob

from log_functions import read_log, log2dict
from control_functions import restart_service, stop_service, service_status, run_gps_test, run_export_test
from redis_functions import redis_init, redis_retrieve


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
    common['use_camera'] = conf['CAMERA']['use_camera']
    print(common['use_camera'])
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
            flash(Markup(f"""Written new local config file. You will need to restart the So-Rad service for changes to take effect <a href="/control" class="alert-link">here</a>"""))

        except Exception as err:
            flash(f"Failed to write local config file: {err}")

    update_config()
    update_common_items()
    return

# users
class User(UserMixin):
    def __init__(self, name, id, hash):
        self.id = id
        self.name = name
        self.hash = hash
        self.is_authenticated = self.is_authenticated()
        self.is_active = self.is_active()

    def check_password(self, password):
        return check_password_hash(self.hash, password)

    def is_authenticated(self):
        return True

    def is_active(self):
        return True

    def get_id(self):
        return self.id

    def __repr__(self):
        #return f"<User {self.name}>"
        return f"<User {self.name}> id {self.id}"

admin_hash = conf['FLASK']['admin_hash']
users = {'admin': User('admin', 'bosh', admin_hash)}


# define app
app = Flask(__name__)
app.config['SECRET_KEY'] = conf['FLASK']['key1'] or str(uuid.uuid1())
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


# pass math functions to jinja2
@app.context_processor
def utility_processor():
    return dict(cos=cos, sin=sin, radians=radians)

####  ROUTES  ####

# define routes
@app.route('/test')
def test():
    """Just to check that nginx/flask are working"""
    return "Test OK"


@app.route('/', methods=['GET'])
@app.route('/index', methods=['GET'])
def index():
    return render_template('layout.html', common=common)


@app.route('/redis_live', methods=['GET'])
def redis_live():
    """populate a live data section from redis and display as json object"""
    try:
        client = redis_init()
        if client is None:
           raise Exception("Redis not initialised")

        redisvals = {}
        for key in ['system_status',
                    'sampling_status',
                    'counter',
                    'upload_status',
                    'samples_pending_upload',
                    'disk_free_gb',
                    'tilt_avg',
                    'tilt_std',
                    'tilt_updated']:
            try:
                redisvals[key], redisvals[f"{key}_updated"] = redis_retrieve(client, key, freshness=None)
            except:
                redisvals[key] = ''

        values, values_updated = redis_retrieve(client, 'values', freshness=None)

        redisvals['values_updated'] = values_updated
        for key in values.keys():
            if key in ['speed',
                       'nsat0',
                       'motor_pos',
                       'motor_deg',
                       'ship_bearing_mean',
                       'solar_az',
                       'solar_el',
                       'rel_view_az',
                       'batt_voltage',
                       'lat0',
                       'lon0',
                       'headMot',
                       'relPosHeading',
                       'accHeading',
                       'fix',
                       'flags_headVehValid',
                       'flags_diffSolN',
                       'flags_gnssFixOK',
                       'tilt_avg',
                       'tilt_std',
                       'inside_temp',
                       'inside_rh',
                       'motor_alarm',
                       'driver_temp',
                       'motor_temp',
                       'pi_temp']:
                redisvals[key] = values[key]

        # read so-rad status
        common['so-rad_status'], message = service_status('so-rad')

        try:
            return jsonify(redisvals)
        except Exception as err:
            print(err)
            flash("Unable to provide system_status")
            return jsonify(None)

    except Exception as msg:
        return msg


@app.route('/live', methods=['GET'])
def live():
    """Home page showing live instrument status from redis"""
    try:
        client = redis_init()
        if client is None:
           raise Exception("Redis not initialised")

        redisvals = {}
        for key in ['system_status', 'sampling_status', 'counter', 'upload_status', 'samples_pending_upload', 'disk_free_gb', 'values']:
            try:
                redisvals[key], redisvals[f"{key}_updated"] = redis_retrieve(client, key, freshness=None)
            except AttributeError:
                redisvals[key] = ''
        # read so-rad status
        common['so-rad_status'], message = service_status('so-rad')

        try:
            return render_template('live.html', common=common, redisvals=redisvals)
        except Exception as err:
            flash("Unable to load the requested page")
            flash(err)
            return render_template('layout.html', common=common)

    except Exception as msg:
        return msg


@app.route('/camera', methods=['GET', 'POST'])
def camera():
    """
    Show latest camera image if a camera is present/active
    """

    camera_vals = {'n_images_shown': 100,
                   'max_storage_gb': conf['CAMERA']['max_storage_gb']}

    filelist = glob.glob(os.path.join(conf['CAMERA']['storage_path'], '*.jpg'))

    # get image store size
    total_bytes = 0
    filesizes = []
    for file in filelist:
        filesizes.append(os.path.getsize(file))
    camera_vals['stored_gb'] = f"{sum(filesizes) / 1024**3:.2f}"

    try:
        if request.method == 'POST':
            camera_vals['n_images_shown'] = int(request.form['n_images_shown'])
            if 'All' in request.form.keys():
                camera_vals['n_images_shown'] = len(filelist)
            elif '100' in request.form.keys():
                camera_vals['n_images_shown'] = 100
            else:
                for key in request.form.keys():
                    if 'download_' in key:
                        filepath = os.path.join(conf['CAMERA']['storage_path'], '_'.join(key.split('_')[1:]))
                        if os.path.exists(filepath):
                            return send_file(filepath)
                        else:
                            break

        camera_vals['n_images'] = len(filelist)
        if len(filelist) < camera_vals['n_images_shown']:
            camera_vals['n_images_shown'] = len(filelist)

        filelist = [os.path.basename(f) for f in filelist]
        filelist.sort()
        filelist.reverse()
        camera_vals['image_list'] = filelist[0:camera_vals['n_images_shown']]
        camera_vals['image_sizes'] = [os.path.getsize(os.path.join(conf['CAMERA']['storage_path'],file))/1024. for file in filelist]

    except Exception as err:
        return f"An unexpected error occurred handling a /camera request: {err}"

    try:
        client = redis_init()
        if client is None:
           raise Exception("Redis not initialised")

        try:
            camera_vals['last_picam_path'], camera_vals['last_picam_updated'] = redis_retrieve(client, 'last_picam_image', freshness=None)
        except Exception as err:
            camera_vals['last_picam_path'] = camera_vals['last_picam_updated'] = ""
            print(err)

        dest = os.path.join('.','static','latest_image_full.jpg')
        if os.path.islink(dest) and not os.path.exists(dest):
            # link points to purged file
            try:
                os.remove(dest)
                os.remove(dest.replace('_full', ''))
            except: pass

        # is a camera image available according to redis?
        if (len(camera_vals['last_picam_path']) > 0) and (os.path.exists(camera_vals['last_picam_path'])):

            # are existing files/links different?
            if (not os.path.exists(dest)) or \
               (not os.path.exists(dest.replace('_full', '_thumbnail'))) or \
               (os.stat(dest).st_mtime != os.stat(camera_vals['last_picam_path']).st_mtime):

                if os.path.islink(dest) or os.path.exists(dest):
                    # remove existing link/thumbnail
                    try:
                        os.remove(dest)
                        os.remove(dest.replace('_full', '_thumbnail'))
                    except: pass

                os.symlink(camera_vals['last_picam_path'], dest)
                # scale down the image
                im = Image.open(dest)
                im.thumbnail((500,500))
                im.save(dest.replace('_full', '_thumbnail'))

            # download full version of latest image using send_file
            if (request.method == 'POST') and ('download-latest' in request.form.keys()):
                return send_file(dest, as_attachment=True)

        else:
            camera_vals['last_picam_path'] = ''

        try:
            return render_template('camera.html',
                                   common=common,
                                   camera_vals=camera_vals,
                                   zip=zip)
        except Exception as err:
            return err
            flash("Unable to load the requested page")
            flash(err)
            return render_template('layout.html', common=common)

    except Exception as msg:
        return msg


@app.route('/control', methods=['GET', 'POST'])
@login_required
def control():
    """Home page showing instrument status"""

    selection = ''
    common['so-rad_status'], message = service_status('so-rad')

    if request.method == 'GET':
         return render_template('control.html', common=common)

    selection = list(request.form.keys())[0]   # key = name
    flash(f"{selection} requested")

    if ('test' in selection) and (common['so-rad_status']):
        print("debug checkpoint")
        flash("Please stop the So-Rad service before running this command. If you already stopped the service, click the check button below to verify that the service has stopped.")
        return render_template('control.html', common=common)

    if selection == 'restart':
        status = restart_service('so-rad')
        common['so-rad_status'] = status
        return render_template('control.html', common=common)

    elif selection == 'stop':
        status = stop_service('so-rad')
        common['so-rad_status'] = status
        return render_template('control.html', common=common)

    elif selection == 'check':
        common['so-rad_status'], message = service_status('so-rad')
        flash(f"So-Rad service status: {message}")
        return render_template('control.html', common=common)

    elif selection == 'gps_test':
        # run a so-rad test script.
        status, messages = run_gps_test()
        return render_template('control.html', messages=messages, common=common)

    elif selection == 'export_test':
        # use to check data upload status and force uploads
        status, messages = run_export_test()
        return render_template('control.html', messages=messages, common=common)
    elif selection == 'export_test_force':
        # use to check data upload status and force uploads
        status, messages = run_export_test(force=True)
        return render_template('control.html', messages=messages, common=common)

    elif selection == 'reboot':
        status = os.system('/usr/bin/sudo shutdown -r 1 &')
        print(status)
        flash(f"Reboot scheduled one minute from {datetime.datetime.utcnow().isoformat()}")
        return render_template('control.html', common=common)

    elif selection == 'cancelreboot':
        status = os.system('/usr/bin/sudo shutdown -c')
        print(status)
        return render_template('control.html', common=common)

    elif selection == 'shutdown':
        status = os.system('/usr/bin/sudo shutdown -h 1 &')
        print(status)
        flash(f"Shutdown scheduled 1 minute from {datetime.datetime.utcnow().isoformat()}")
        return render_template('control.html', common=common)

    else:
        flash("Unknown request posted")
        return render_template('control.html', common=common)


@app.route('/status', methods=['GET', 'POST'])
@app.route('/latest', methods=['GET', 'POST'])
def latest():
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

        common['systemlog'] = True
        common['dbreads'] = True
        common['plot'] = True

        # info from log
        logvalues = []
        timeseries = {}
        labels = []

        logrows = read_log(log_file_location, n=common['nrows'], reverse=True)
        if logrows is not None and len(logrows) > 0:
            print(f"read {len(logrows)} log rows")
            common['nrows'] = len(logrows)
            for row in logrows:
                if 'Sun' in row:
                    logrow_parsed = {}  # force new instance
                    logrow_parsed = log2dict(row, logrow_parsed)
                    logvalues.append(logrow_parsed)
            #print(f"{len(logvalues)} system orientation log lines parsed")
            #print(logvalues)

        else:
            print("Log file not found.")
            flash("Log file not found.")
            common['systemlog'] = False

        if len(logvalues) > 0:
            labels = [lrow['timestr'] for lrow in logvalues]
            print(labels)
            #for lrow in logvalues:
            #    print(lrow['timestr'])
            timeseries = {
                  'sun_azimuth':   [lr['sun_azimuth'] for lr in logvalues if 'sun_azimuth' in lr.keys()],
                  'motor_heading': [lr['motor_heading'] for lr in logvalues if 'motor_heading' in lr.keys()],
                  'ship_heading':  [lr['ship_heading'] for lr in logvalues if 'ship_heading' in lr.keys()],
                  'relviewaz':     [lr['relviewaz'] for lr in logvalues if 'relviewaz' in lr.keys()],
                  'cw_limit':      [lr['ship_heading'] + common['home_pos'] + common['cw_limit_deg'] for lr in logvalues if 'ship_heading' in lr.keys()],
                  'ccw_limit':     [lr['ship_heading'] + common['home_pos'] - common['ccw_limit_deg'] for lr in logvalues if 'ship_heading' in lr.keys()],
                  'sensoraz':      [lr['sun_azimuth'] + lr['relviewaz'] for lr in logvalues if ('sun_azimuth' in lr.keys()) and ('relviewaz' in lr.keys())]
                  }
            for key, val in timeseries.items():
                if len(val) == 0:
                     print(f"{key} is missing data")
                     common['plot'] = False
                     common['systemlog'] = False

            if not common['plot']:
                print("Some plot values could not be read. Try increasing the number of rows read or consult system logs")
                flash("Some plot values could not be read. Try increasing the number of rows read or consult system logs")
        else:
            print("No recent system status information read from log file. Try increasing the number of rows read or consult system logs")
            flash("No recent system status information read from log file. Try increasing the number of rows read or consult system logs")
            common['systemlog'] = False

        # info from db
        dbrows = get_from_db(db_path, n=1)
        if dbrows is not None and len(dbrows) > 0:
            dbtable = dict(dbrows[0])
        else:
            flash("Database file not found or database empty.")
            common['dbreads'] = False

        # read so-rad status
        common['so-rad_status'], message = service_status('so-rad')

        try:
            return render_template('latest.html', logvalues=logvalues, dbtable=dbtable,
                                   labels=labels, timeseries=timeseries, common=common)
        except:
            flash("Unable to load the requested page")
            return render_template('layout.html', common=common)

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
        else:
            login_user(user, remember=form.remember_me.data)
            flash(f"User {current_user.name} logged in.")

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
                'gps_heading_correction':
                                 {'label':    'GPS receivers to platform axis offset',
                                  'setting':   int(conf['GPS']['gps_heading_correction']),
                                  'postlabel': 'degrees',
                                  'comment':   'normally 0 or 90',
                                  'min':       -181,
                                  'max':       181},
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
                forminput['gps_heading_correction']    = int(request.form['gps_heading_correction'])
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
    app.run(host='0.0.0.0', port=8080, debug=False)

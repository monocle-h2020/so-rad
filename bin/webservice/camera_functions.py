#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Camera functions for So-Rad web interface
"""

from flask import Flask, render_template, abort, \
                  flash, redirect, url_for, request,\
                  Markup, jsonify, send_file
from jinja2 import TemplateNotFound
import os
import datetime
import redis
from PIL import Image
from io import BytesIO
import glob
import zipfile
from redis_functions import redis_init, redis_retrieve
from numpy import argsort, array
import re

def camera_zip(filepaths, label):
    try:
        with zipfile.ZipFile(os.path.join(".", "static", f"{label}.zip"),
                             'w', zipfile.ZIP_DEFLATED) as z:
            for file in filepaths:
                 z.write(file)
        return True
    except:
        return False


def get_file_lists(conf):
    """
    list image files and zip archives
    """
    filelist = glob.glob(os.path.join(conf['CAMERA']['storage_path'], '*.jpg'))
    # get image store size
    total_bytes = 0
    filesizes = []
    for file in filelist:
        filesizes.append(os.path.getsize(file))

    # get image timestamps from filenames (to get observation trigger times)
    filetimes = []
    pat = '.*(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}).*'
    for file in filelist:
        match = re.match(pat, file)
        if match:
            filetimes.append(datetime.datetime.strptime(match.group(1), '%Y-%m-%dT%H:%M:%S'))

    # sort filelist by observation timestamp
    filelist  = array(filelist)[argsort(filetimes)]
    filesizes = array(filesizes)[argsort(filetimes)]
    filetimes = array(filetimes)[argsort(filetimes)]

    zip_archives = glob.glob(os.path.join('.', 'static', '*.zip'))

    return filelist, filesizes, filetimes, zip_archives


def camera_main(common, conf):
    """
    Show latest camera image if a camera is present/active
    """
    try:
        client = redis_init()
        if client is None:
           raise Exception("Redis not initialised")
        camera_dict, u = redis_retrieve(client, 'camera_dict', freshness=None)

        camera_vals = {'n_images_shown': 100,
                       'max_storage_gb': conf['CAMERA']['max_storage_gb'],
                       'redis_camera_dict': camera_dict}

        filelist, filesizes, filetimes, zip_archives = get_file_lists(conf)
        camera_vals['stored_gb'] = f"{sum(filesizes) / 1024**3:.2f}"

        if request.method == 'POST':

            camera_vals['n_images_shown'] = int(request.form['n_images_shown'])
            if 'All' in request.form.keys():
                camera_vals['n_images_shown'] = len(filelist)

            elif '100' in request.form.keys():
                camera_vals['n_images_shown'] = 100

            elif 'makezip' in request.form.keys():
                 filelist_start = -1
                 filelist_end = -2

                 start_dt_str = request.form['start_dt']
                 end_dt_str = request.form['end_dt']

                 if start_dt_str.lower() == 'first':
                     filelist_start = 0
                 else:
                     print(start_dt_str)
                     try:
                         start_dt = datetime.datetime.strptime(start_dt_str, '%Y-%m-%dT%H:%M:%S')
                     except ValueError:
                         return f"{start_dt_str} is not a valid timeformat for 'YYYY-mm-ddTHH:MM:SS'"
                     for i, ft in enumerate(filetimes):
                         if ft >= start_dt:
                             filelist_start = i
                             break
                 if end_dt_str.lower() == 'last':
                      filelist_end = -1
                 else:
                     try:
                         end_dt = datetime.datetime.strptime(end_dt_str, '%Y-%m-%dT%H:%M:%S')
                     except ValueError:
                         return f"{end_dt_str} is not a valid timeformat for 'YYYY-mm-ddTHH:MM:SS'"

                     for i, ft in enumerate(filetimes):
                         if ft <= end_dt:
                             filelist_end = i
                         else:
                             break

                 if filelist_end < filelist_start:
                     flash("No images found matching that time frame")

                 else:
                     label = f"{filetimes[filelist_start].isoformat()}-{filetimes[filelist_end].isoformat()}"
                     zipresult = camera_zip(filelist,label)  # replace with selection
                     if zipresult:
                         flash(f"Created image archive {label}.zip")
                     else:
                         flash(f"Error creating image archive.")

            elif 'clear_storage' in request.form.keys():
                print(1)
                for f in filelist:
                    if os.path.exists(f):
                        os.remove(f)
                filelist, filesizes, filetimes, zip_archives = get_file_lists(conf)
                camera_vals['stored_gb'] = f"{sum(filesizes) / 1024**3:.2f}"

            else:
                for key in request.form.keys():
                    if 'download_' in key:
                        fileselected = '_'.join(key.split('_')[1:])
                        if os.path.basename(fileselected)[-3:] == 'jpg':
                            rootpath = conf['CAMERA']['storage_path']
                        elif os.path.basename(fileselected)[-3:] == 'zip':
                            rootpath = './static'
                        else:
                            print(f"Unknown download request for {fileselected}")
                            break
                        filepath = os.path.join(rootpath, fileselected)
                        if os.path.exists(filepath):
                            return send_file(filepath, as_attachment=True, mimetype='zip')
                        else:
                            break

                    if 'delete_' in key:
                        fileselected = '_'.join(key.split('_')[1:])
                        print(fileselected)
                        if os.path.basename(fileselected)[-3:] == 'jpg':
                            rootpath = conf['CAMERA']['storage_path']
                        elif os.path.basename(fileselected)[-3:] == 'zip':
                            rootpath = './static'
                        filepath = os.path.join(rootpath, fileselected)
                        if os.path.exists(filepath):
                            os.remove(filepath)
                            filelist, filesizes, filetimes, zip_archives = get_file_lists(conf)
                            camera_vals['stored_gb'] = f"{sum(filesizes) / 1024**3:.2f}"
                        else:
                            break

        camera_vals['n_images'] = len(filelist)
        if len(filelist) < camera_vals['n_images_shown']:
            camera_vals['n_images_shown'] = len(filelist)

        filenames_short = [os.path.basename(f) for f in filelist]
        filenames_short.sort()
        filenames_short.reverse()
        camera_vals['image_list'] = filenames_short[0:camera_vals['n_images_shown']]
        camera_vals['image_sizes'] = [os.path.getsize(os.path.join(conf['CAMERA']['storage_path'],file))/1024. for file in filenames_short]
        camera_vals['zip_list'] = [os.path.basename(z) for z in zip_archives]
        camera_vals['zip_sizes'] = [os.path.getsize(z)/1024.**2 for z in zip_archives]

        # camera_vals = get_latest_image(camera_vals)

        dest = os.path.join('.','static','latest_image_full.jpg')
        # download full version of latest image using send_file
        if (request.method == 'POST') and ('download-latest' in request.form.keys()):
            return send_file(dest, as_attachment=True, mimetype='jpg')

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


def latest_image(quality):
    """
    send latest image from redis
    param quality: 1-100 jpg compression quality
    type quality:  int

    Can be embedded in html tags e.g. <img src="{{ url_for('latest_image', quality=10) }} />
    """
    try:
        client = redis_init()
        if client is None:
           raise Exception("Redis not initialised")
        camera_dict, u = redis_retrieve(client, 'camera_dict', freshness=None)
        camera_response, u = redis_retrieve(client, 'camera_last_image', freshness=None)
        print(camera_response)
        if camera_response is None:
            return ''
        img = camera_response.content
        img_io = BytesIO()
        pil_img = Image.open(BytesIO(img))
        pil_img.save(img_io, 'JPEG', quality=int(quality))
        img_io.seek(0)
    except Exception as err:
        return f"Error serving latest image:\n{err}"
    return send_file(img_io, mimetype='image/jpeg')

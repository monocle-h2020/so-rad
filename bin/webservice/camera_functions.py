#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Camera functions for So-Rad web interface
"""

from flask import Flask, render_template, abort, \
                  flash, redirect, url_for, request,\
                  jsonify, send_file
from jinja2 import TemplateNotFound
import os
import datetime
import redis
from PIL import Image
from io import BytesIO
import glob
from redis import Redis
from redis_functions import redis_init, redis_retrieve
from numpy import argsort, array
import re
import sys
import inspect
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(inspect.getfile(inspect.currentframe())))))
from functions import download_functions as df
from rq import Queue
from dataset_functions import queue_info


# link to or create redis queue 'sorad_q'
sorad_q = Queue('sorad_q', connection=Redis())


def get_file_lists(conf, storage_dir, mask='*.jpg'):
    """
    list files by extension
    """
    filelist = glob.glob(os.path.join(storage_dir, mask))
    # get image store size
    total_bytes = 0
    filesizes = []
    filemods = []
    for file in filelist:
        filesizes.append(os.path.getsize(file))

    # get image timestamps from filenames (to get observation trigger times)
    filetimes = []
    pat = '.*(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}).*'
    for file in filelist:
        match = re.match(pat, file)
        if match:
            filetimes.append(datetime.datetime.strptime(match.group(1), '%Y-%m-%dT%H:%M:%S'))
            filemods.append(datetime.datetime.strftime(
                                     datetime.datetime.fromtimestamp(os.path.getmtime(file)),
                                     '%Y%m%dT%H%M%S'))

    # sort filelist by observation timestamp
    filelist  = array(filelist)[argsort(filetimes)]
    filesizes = array(filesizes)[argsort(filetimes)]
    filetimes = array(filetimes)[argsort(filetimes)]
    filemods =  array(filemods)[argsort(filetimes)]

    return filelist, filesizes, filetimes, filemods


def camera_main(common, conf):
    """
    Show latest camera image if a camera is present/active
    """
    print(0)
    try:
        storage_path = conf['DOWNLOAD'].get('storage_path')
        imgdir = conf['CAMERA'].get('storage_path')

        client = redis_init()
        if client is None:
           raise Exception("Redis not initialised")
        camera_dict, u = redis_retrieve(client, 'camera_dict', freshness=None)

        camera_vals = {'n_images_shown': 100,
                       'n_datasets_shown': 10,
                       'max_storage_gb': conf['CAMERA']['max_storage_gb'],
                       'redis_camera_dict': camera_dict,
                       'make_zip_start_current': datetime.datetime.strftime(datetime.datetime.now()-datetime.timedelta(hours=24), '%Y-%m-%dT%H:%M'),
                       'make_zip_end_current': datetime.datetime.strftime(datetime.datetime.now(), '%Y-%m-%dT%H:%M'),
                       'queue_status_message': queue_info(sorad_q)}

        print(1)

        filelist, filesizes, filetimes, filemods = get_file_lists(conf, storage_dir=imgdir, mask='*.jpg')
        ziplist, zipsizes, ziptimes, zipmods = get_file_lists(conf, storage_path, mask='*.zip')
        camera_vals['stored_gb'] = f"{sum(filesizes) / 1024**3:.2f}"

        if request.method == 'POST':

            print(2)

            camera_vals['n_images_shown'] = int(request.form['n_images_shown'])
            if 'All' in request.form.keys():
                camera_vals['n_images_shown'] = len(filelist)

            elif '100' in request.form.keys():
                camera_vals['n_images_shown'] = 100

            elif 'makezip' in request.form.keys():
                 filelist_start = -1
                 filelist_end = -2
                 print(3)

                 print(request.form['make_zip_start'])
                 print(request.form['make_zip_end'])
                 zip_start = datetime.datetime.strptime(request.form['make_zip_start'], "%Y-%m-%dT%H:%M")
                 zip_end = datetime.datetime.strptime(request.form['make_zip_end'], "%Y-%m-%dT%H:%M")
                 print(f"zip archive {zip_start} - {zip_end} requested")

                 camera_vals['make_csv_start_current'] = datetime.datetime.strftime(zip_start, '%Y-%m-%dT%H:%M')
                 camera_vals['make_csv_end_current']   = datetime.datetime.strftime(zip_end, '%Y-%m-%dT%H:%M')
                 print(3.1)

                 for i, ft in enumerate(filetimes):
                     if ft >= zip_start:
                         filelist_start = i
                         break

                 for i, ft in enumerate(filetimes):
                     if ft <= zip_end:
                         filelist_end = i
                     else:
                         break
                 print(3.2)

                 if filelist_end < filelist_start:
                     flash("No images found matching that time frame")
                 else:
                     try:
                         print(4)

                         label = f"{filetimes[filelist_start].isoformat()}-{filetimes[filelist_end].isoformat()}"
                         print(f"requested zip file containing files from {filelist[filelist_start]} to {filelist[filelist_end]}")
                         job = sorad_q.enqueue(df.camera_zip_from_web_request,
                                               storage_path,
                                               filelist[filelist_start:filelist_end],
                                               label,
                                               common['platform_id'],
                                               job_timeout=3400)

                         flash(f"Job {job.id} was added to the processing queue")

                     except Exception as err:
                         print(err)

            elif 'clear_img_storage' in request.form.keys():
                print('clear_img_storage')
                for f in filelist:
                    if os.path.exists(f):
                        os.remove(f)
                filelist, filesizes, filetimes, filemods = get_file_lists(conf, storage_dir=imgdir, mask='*.jpg')
                camera_vals['stored_gb'] = f"{sum(filesizes) / 1024**3:.2f}"

            elif 'clear_zip_storage' in request.form.keys():
                print('clear_zip_storage')
                for f in ziplist:
                    if os.path.exists(f):
                        os.remove(f)
                ziplist, zipsizes, ziptimes, zipmods = get_file_lists(conf, storage_path, mask='*.zip')


            else:
                for key in request.form.keys():
                    if 'download_' in key:
                        fileselected = '_'.join(key.split('_')[1:])
                        if os.path.basename(fileselected)[-3:] == 'jpg':
                            rootpath = imgdir
                        elif os.path.basename(fileselected)[-3:] == 'zip':
                            rootpath = storage_path
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
                            rootpath = imgdir
                        elif os.path.basename(fileselected)[-3:] == 'zip':
                            rootpath = storage_path
                        filepath = os.path.join(rootpath, fileselected)
                        if os.path.exists(filepath):
                            os.remove(filepath)
                            filelist, filesizes, filetimes, filemods = get_file_lists(conf, storage_dir=imgdir, mask='*.jpg')
                            ziplist, zipsizes, ziptimes, zipmods = get_file_lists(conf, storage_path, mask='*.zip')
                            camera_vals['stored_gb'] = f"{sum(filesizes) / 1024**3:.2f}"
                        else:
                            break

        print(5)

        camera_vals['n_datasets'] = len(ziplist)
        if camera_vals['n_datasets'] < camera_vals['n_datasets_shown']:
            camera_vals['n_datasets_shown'] = camera_vals['n_datasets']

        print(5.1)

        camera_vals['n_images'] = len(filelist)
        if len(filelist) < camera_vals['n_images_shown']:
            camera_vals['n_images_shown'] = len(filelist)

        filenames_short = [os.path.basename(f) for f in filelist]
        filenames_short.sort()
        filenames_short.reverse()
        camera_vals['image_list'] = filenames_short[0:camera_vals['n_images_shown']]
        camera_vals['image_sizes'] = [os.path.getsize(os.path.join(conf['CAMERA']['storage_path'],file))/1024. for file in filenames_short]

        camera_vals['zip_list'] = [os.path.basename(z) for z in ziplist]
        camera_vals['zip_sizes'] = [os.path.getsize(z)/1024.**2 for z in ziplist]
        camera_vals['zip_dataset_mods'] = list(zipmods)

        print(6)

        dest = os.path.join('.','static','latest_image_full.jpg')
        if os.path.exists(dest):
            os.remove(dest)
        try:
            os.symlink(filelist[-1], dest)
        except: pass

        # download full version of latest image using send_file
        if (request.method == 'POST') and ('download-latest' in request.form.keys()):
            return send_file(dest, as_attachment=True, mimetype='jpg')

        try:
            print(7)

            return render_template('camera.html',
                                   common=common,
                                   camera_vals=camera_vals,
                                   zip=zip)

        except Exception as err:
            return err
            flash("Unable to load the requested page")
            flash(err)
            print(err)
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
        if camera_response is None:
            print("No redis entry 'camera_last_image'")
            return ''
        print(f"Reading last camera image, {len(camera_response)} bytes")
        pil_img = Image.open(BytesIO(camera_response))
        #pil_img.save(img_io, 'JPEG', quality=int(quality))
        #img_io.seek(0)
    except Exception as err:
        return f"Error serving latest image:\n{err}"
    #return send_file(img_io, mimetype='image/jpeg')
    return send_file(BytesIO(camera_response), mimetype='image/jpeg')

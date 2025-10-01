#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Dataset download functions for So-Rad web interface
"""

from flask import Flask, render_template, abort, \
                  flash, redirect, url_for, request,\
                  Markup, jsonify, send_file
from jinja2 import TemplateNotFound
import os
import datetime
import redis
import glob
import zipfile
from redis_functions import redis_init, redis_retrieve
from redis import Redis
from numpy import argsort, array
import re
import sys
import inspect
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(inspect.getfile(inspect.currentframe())))))
from functions import download_functions as df
from rq import Queue

# link to or create redis queue 'sorad_q'
sorad_q = Queue('sorad_q', connection=Redis())

def get_file_lists(conf, mask='*.csv'):
    """
    list csv or hdf data files that have already been prepared
    """
    filelist = glob.glob(os.path.join(conf['DOWNLOAD']['storage_path'], mask))
    # get image store size
    total_bytes = 0
    filesizes = []
    for file in filelist:
        filesizes.append(os.path.getsize(file))
    # get image timestamps from filenames (to get observation trigger times)
    filetimes = []
    pat = r"(\w{9})_(\d{8}T\d{6})-(\d{8}T\d{6}).\w{3}"
    for file in filelist:
        match = re.match(pat, os.path.basename(file))
        if match:
            filetimes.append(datetime.datetime.strptime(match.group(2), '%Y%m%dT%H%M%S'))

    # sort filelist by observation timestamp
    filelist  = array(filelist)[argsort(filetimes)]
    filesizes = array(filesizes)[argsort(filetimes)]
    filetimes = array(filetimes)[argsort(filetimes)]

    return filelist, filesizes, filetimes

def queue_info(queue):
    """
    Retrieve queue info
    """
    nqueueing = len(queue.job_ids)
    nstarted =  queue.started_job_registry.count
    nfinished = queue.finished_job_registry.count
    nfailed =   queue.failed_job_registry.count
    result = f"Current and recent jobs: {nqueueing} queueing, {nstarted} started, {nfinished} finished, {nfailed} failed."
    return result


def download_main(common, conf):
    """
    Show datasets available for download
    """
    try:
        client = redis_init()
        if client is None:
           raise Exception("Redis not initialised")

        dataset_vals = {'n_datasets_shown': 100,
                       'max_storage_gb': conf['DOWNLOAD']['max_storage_gb'],
                       'make_csv_start_current': datetime.datetime.strftime(datetime.datetime.now()-datetime.timedelta(hours=24), '%Y-%m-%dT%H:%M'),
                       'make_csv_end_current': datetime.datetime.strftime(datetime.datetime.now(), '%Y-%m-%dT%H:%M'),
                       'queue_status_message': queue_info(sorad_q)}

        print(0)
        try:
            csv_filelist, csv_filesizes, csv_filetimes = get_file_lists(conf, mask='*.csv')
            hdf_filelist, hdf_filesizes, hdf_filetimes = get_file_lists(conf, mask='*.hdf')
            filesizes = list(csv_filesizes) + list(hdf_filesizes)
            dataset_vals['stored_gb'] = f"{sum(filesizes) / 1024**3:.2f}"
        except Exception as err:
            print(err)

        print(1)

        if request.method == 'POST':

            dataset_vals['n_datasets_shown'] = int(request.form['n_datasets_shown'])

            if 'All' in request.form.keys():
                dataset_vals['n_datasets_shown'] = len(csv_filelist) + len(hdf_filelist)

            elif '100' in request.form.keys():
                dataset_vals['n_datasets_shown'] = 100

            elif 'make_csv' in request.form.keys():
                try:
                    print(request.form['make_csv_start'])
                    print(request.form['make_csv_end'])
                    csv_start = datetime.datetime.strptime(request.form['make_csv_start'], "%Y-%m-%dT%H:%M")
                    csv_end = datetime.datetime.strptime(request.form['make_csv_end'], "%Y-%m-%dT%H:%M")
                    print(f"{csv_start} - {csv_end} requested")
                    #name_to_queue = df.filename_from_dates(common['platform_id'],
                    job = sorad_q.enqueue(df.csv_from_web_request, conf,
                                          csv_start, csv_end, common['platform_id'])
                    flash(f"Job {job.id} was added to the processing queue")

                except Exception as err:
                    print(err)

            elif 'clear_csv_storage' in request.form.keys():
                for f in csv_filelist:
                    if os.path.exists(f):
                        os.remove(f)
                csv_filelist, csv_filesizes, csv_filetimes = get_file_lists(conf, mask='*.csv')
                filesizes = list(csv_filesizes) + list(hdf_filesizes)
                dataset_vals['stored_gb'] = f"{sum(filesizes) / 1024**3:.2f}"

            elif 'clear_hdf_storage' in request.form.keys():
                for f in filelist:
                    if os.path.exists(f):
                        os.remove(f)
                hdf_filelist, hdf_filesizes, hdf_filetimes = get_file_lists(conf, '*.hdf')
                filesizes = list(csv_filesizes) + list(hdf_filesizes)
                dataset_vals['stored_gb'] = f"{sum(filesizes) / 1024**3:.2f}"

            else:
                for key in request.form.keys():
                    if 'download_' in key:
                        fileselected = '_'.join(key.split('_')[1:])
                        print(f"File delete request: {fileselected}")
                        if os.path.basename(fileselected)[-3:] in ['csv', 'hdf']:
                            rootpath = conf['DOWNLOAD']['storage_path']
                        else:
                            print(f"Unknown download request for {fileselected}")
                            break
                        filepath = os.path.join(rootpath, fileselected)
                        if os.path.exists(filepath):
                            return send_file(filepath, as_attachment=True, mimetype='csv')
                        else:
                            break

                    if 'delete_' in key:
                        fileselected = '_'.join(key.split('_')[1:])
                        print(f"File delete request: {fileselected}")
                        if os.path.basename(fileselected)[-3:] in ['csv', 'hdf']:
                            rootpath = conf['DOWNLOAD']['storage_path']
                        filepath = os.path.join(rootpath, fileselected)
                        if os.path.exists(filepath):
                            os.remove(filepath)
                            csv_filelist, csv_filesizes, csv_filetimes = get_file_lists(conf, mask='*.csv')
                            hdf_filelist, hdf_filesizes, hdf_filetimes = get_file_lists(conf, mask='*.hdf')
                            filesizes = list(csv_filesizes) + list(hdf_filesizes)
                            dataset_vals['stored_gb'] = f"{sum(filesizes) / 1024**3:.2f}"
                        else:
                            print(f"File delete request failed. Could not find file {filepath}")
                            break


        print(2)

        dataset_vals['n_datasets'] = max([len(csv_filelist), len(hdf_filelist)])
        if dataset_vals['n_datasets'] < dataset_vals['n_datasets_shown']:
            dataset_vals['n_datasets_shown'] = dataset_vals['n_datasets']

        try:
            csv_filenames_short = [os.path.basename(f) for f in csv_filelist]
            csv_filenames_short.sort()
            csv_filenames_short.reverse()
            dataset_vals['csv_dataset_list'] = csv_filenames_short[0:dataset_vals['n_datasets_shown']]
            dataset_vals['csv_dataset_sizes'] = [os.path.getsize(os.path.join(conf['DOWNLOAD']['storage_path'],file))/1024. for file in csv_filenames_short]
        except Exception as err:
            print(err)

        hdf_filenames_short = [os.path.basename(f) for f in hdf_filelist]
        hdf_filenames_short.sort()
        hdf_filenames_short.reverse()
        dataset_vals['hdf_dataset_list'] = hdf_filenames_short[0:dataset_vals['n_datasets_shown']]
        dataset_vals['hdf_dataset_sizes'] = [os.path.getsize(os.path.join(conf['DOWNLOAD']['storage_path'],file))/1024. for file in hdf_filenames_short]

        try:
            return render_template('downloads.html',
                                   common=common,
                                   dataset_vals=dataset_vals, zip=zip)

        except Exception as err:
            print(err)
            flash("Unable to load the requested page")
            flash(err)
            return render_template('layout.html', common=common)

    except Exception as msg:
        return msg

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
from PIL import Image
from io import BytesIO
import glob
import zipfile
from redis_functions import redis_init, redis_retrieve
from numpy import argsort, array
import re


def get_file_lists(conf, mask='*.csv'):
    """
    list csv or hdf data files that have already been prepared
    """
    filelist = glob.glob(os.path.join(os.path.dirname(conf['DOWNLOAD']['storage_path']), mask))
    # get image store size
    total_bytes = 0
    filesizes = []
    for file in filelist:
        filesizes.append(os.path.getsize(file))
    # get image timestamps from filenames (to get observation trigger times)
    filetimes = []
    #pat = r"\w{9}_\d{8}T\d{6}-\d{8}T\d{6}.csv"
    pat = r"(\w{9})_(\d{8}T\d{6})-(\d{8}T\d{6}).csv"
    for file in filelist:
        match = re.match(pat, os.path.basename(file))
        if match:
            filetimes.append(datetime.datetime.strptime(match.group(2), '%Y%m%dT%H%M%S'))

    # sort filelist by observation timestamp
    filelist  = array(filelist)[argsort(filetimes)]
    filesizes = array(filesizes)[argsort(filetimes)]
    filetimes = array(filetimes)[argsort(filetimes)]

    return filelist, filesizes, filetimes


def download_main(common, conf):
    """
    Show datasets available for download
    """
    try:
        client = redis_init()
        if client is None:
           raise Exception("Redis not initialised")

        dataset_vals = {'n_datasets_shown': 100,
                       'max_storage_gb': conf['DOWNLOAD']['max_storage_gb']}

        try:
            csv_filelist, csv_filesizes, csv_filetimes = get_file_lists(conf, mask='*.csv')
            hdf_filelist, hdf_filesizes, hdf_filetimes = get_file_lists(conf, mask='*.hdf')
            filesizes = csv_filesizes + hdf_filesizes
            dataset_vals['stored_gb'] = f"{sum(filesizes) / 1024**3:.2f}"
        except Exception as err:
            print(err)

        if request.method == 'POST':

            dataset_vals['n_datasets_shown'] = int(request.form['n_datasets_shown'])
            if 'All' in request.form.keys():
                dataset_vals['n_datasets_shown'] = len(filelist)

            elif '100' in request.form.keys():
                datasets_vals['n_datasets_shown'] = 100

            elif 'clear_csv_storage' in request.form.keys():
                for f in csv_filelist:
                    if os.path.exists(f):
                        os.remove(f)
                csv_filelist, csv_filesizes, csv_filetimes = get_file_lists(conf, mask='*.csv')
                filesizes = csv_filsizes + hdf_filesizes
                dataset_vals['stored_gb'] = f"{sum(filesizes) / 1024**3:.2f}"

            elif 'clear_hdf_storage' in request.form.keys():
                for f in filelist:
                    if os.path.exists(f):
                        os.remove(f)
                hdf_filelist, hdf_filesizes, hdf_filetimes = get_file_lists(conf, '*.hdf')
                filesizes = csv_filsizes + hdf_filesizes
                dataset_vals['stored_gb'] = f"{sum(filesizes) / 1024**3:.2f}"

            else:
                for key in request.form.keys():
                    if 'download_' in key:
                        fileselected = '_'.join(key.split('_')[1:])
                        if os.path.basename(fileselected)[-3:] in ['csv', 'hdf']:
                            rootpath = os.path.dirname(conf['DOWNLOAD']['storage_path'])
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
                        print(fileselected)
                        if os.path.basename(fileselected)[-3:] in ['csv', 'hdf']:
                            rootpath = os.path.dirname(conf['DOWNLOAD']['storage_path'])
                        filepath = os.path.join(rootpath, fileselected)
                        if os.path.exists(filepath):
                            os.remove(filepath)
                            csv_filelist, csv_filesizes, csv_filetimes = get_file_lists(conf, mask='*.csv')
                            hdf_filelist, hdf_filesizes, hdf_filetimes = get_file_lists(conf, mask='*.hdf')
                            filesizes = csv_filsizes + hdf_filesizes
                            dataset_vals['stored_gb'] = f"{sum(filesizes) / 1024**3:.2f}"
                        else:
                            break

        dataset_vals['n_datasets'] = max([len(csv_filelist), len(hdf_filelist)])
        if dataset_vals['n_datasets'] < dataset_vals['n_datasets_shown']:
            dataset_vals['n_datasets_shown'] = dataset_vals['n_datasets']

        csv_filenames_short = [os.path.basename(f) for f in csv_filelist]
        csv_filenames_short.sort()
        csv_filenames_short.reverse()
        dataset_vals['csv_dataset_list'] = csv_filenames_short[0:dataset_vals['n_datasets_shown']]
        dataset_vals['csv_dataset_sizes'] = [os.path.getsize(os.path.join(os.path.dirname(conf['DOWNLOAD']['storage_path']),file))/1024. for file in csv_filenames_short]

        hdf_filenames_short = [os.path.basename(f) for f in hdf_filelist]
        hdf_filenames_short.sort()
        hdf_filenames_short.reverse()
        dataset_vals['hdf_dataset_list'] = hdf_filenames_short[0:dataset_vals['n_datasets_shown']]
        dataset_vals['hdf_dataset_sizes'] = [os.path.getsize(os.path.join(os.path.dirname(conf['DOWNLOAD']['storage_path']),file))/1024. for file in hdf_filenames_short]

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

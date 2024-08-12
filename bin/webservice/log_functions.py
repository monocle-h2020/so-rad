#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Read and parse log file to provide recent So-Rad activity in web interface.
"""

import os


def read_log(log_file_location, n=100, reverse=True):
    """Read the last n lines from a logfile"""
    rows = []

    if not os.path.exists(log_file_location):
        return rows

    bufsize = 1024
    fsize = os.stat(log_file_location).st_size

    if (bufsize >= fsize) or n is None:
        with open(log_file_location, 'r') as logfile:
            rows = logfile.readlines()
        if reverse:
            rows.reverse()
        return rows

    if reverse:
        with open(log_file_location, 'r+') as logfile:
            logfile.seek(0, 2)
            i = 0
            while True:
                i += 1
                seekpos = logfile.tell() - bufsize * i
                if seekpos < 0:
                    seekpos = 0
                logfile.seek(seekpos)
                rows = logfile.readlines()
                if len(rows) >= n or logfile.tell() == 0 or seekpos == 0:
                    break
        rows.reverse()
        rows = rows[0:n]
        return rows

    else:
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
        values['datestr'] =          line.split(' ')[0].strip()
        values['timestr'] =          line.split(' ')[1].strip()
        values['gps_ok'] =           bool(int(line.split('GPS')[1].split(' ')[1].strip()))
        values['heading_ok'] =       bool(int(line.split('Head')[1].split(' ')[1].strip()))
        values['rad_ok'] =           bool(int(line.split('Rad')[1].split(' ')[1].strip()))
        values['speed_ok'] =         bool(int(line.split('Spd')[1].split(' ')[1].strip()))
        values['speed'] =            float(line.split('Spd')[1].split(' ')[2].strip('() '))
        values['motor_ok'] =         bool(int(line.split('Motor')[1].split(' ')[1].strip()))
        values['motor_alarm'] =      int(line.split('Motor')[1].split(' ')[2].strip('() '))
        values['sun_elevation_ok'] = bool(int(line.split('Sun')[1].split(' ')[1].strip()))
        values['latitude'] =         float(line.split('loc')[1].split(' ')[1].strip())
        values['longitude'] =        float(line.split('loc')[1].split(' ')[2].strip())
        values['tilt'] =             float(line.split('Tilt')[1].split(' ')[1].strip())
        values['fix'] =              int(line.split('Fix:')[1].split(' ')[1].strip())
        values['nsat'] =             int(line.split('Fix:')[1].split(' ')[2].split('(')[1].strip())
        values['sun_elevation'] =    float(line.split('Sun')[1].split(' ')[2].strip('() '))
        values['sun_azimuth'] =      float(line.split('SunAz')[1].split(' ')[1].strip())
        values['ship_heading'] =     float(line.split('Ship')[1].split(' ')[1].strip())
        values['motor_heading'] =    float(line.split('Ship')[1].split(' ')[3].strip('|'))
        values['relviewaz'] =        float(line.split('RelViewAz:')[1].split(' ')[1].strip())
        values['batt_ok'] =          bool(int(line.split('Bat')[1].split(' ')[1].strip()))
    except:
        # probably the wrong log line, so stop parsing here
        return values
    return values

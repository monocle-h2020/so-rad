# -*- coding: utf-8 -*-
"""
Created on Sun Dec 27 22:21:27 2015

Methods to import TriOS RAMSES calibration files and calibrate raw spectra

If multiple calibration files are presented for the same sensor, the most
recent calibration preceding each measurement will be selected.

Calibration files representing different calibration events must be stored
in separate subfolders under the destination targeted by 'CalFolder' to avoid
confusion with similar filenames or partial calibration info.

@author: stsi
"""
from __future__ import print_function  # hello future!
import os
import sys
import numpy as np
import datetime


def importCalFiles(CalFolder):
    folders = os.listdir(CalFolder)
    caldict = []
    for f in folders:
        cdct = _ProcessDatIniFiles(os.path.join(CalFolder, f))
        if cdct:
            caldict.append(cdct)
    return caldict


class Ini(object):
    def __init__(self, DeviceType=None, SensorName=None,
                 SAMDevice=None, DeviceTypeSub1=None, DeviceTypeSub2=None,
                 DarkPixelStart=None, DarkPixelStop=None, Reverse=None,
                 WavelengthRange=None, c0s=None,
                 c1s=None, c2s=None, c3s=None, cs=None):
        pass


class Cal(object):
    def __init__(self, SAMDevice_Aqua=None, SAMDevice_Air=None,
                 SAMDevice_Back=None, SAMDateTime_Aqua=None,
                 SAMDateTime_Air=None, SAMDateTime_Back=None,
                 SAMspectrum_Aqua=None, SAMspectrum_Air=None,
                 SAMspectrum_Back0=None, SAMspectrum_Back1=None, ini=Ini):
        self.ini = ini()


def _ProcessDatIniFiles(foldername):
    """Cal_SAM_[****].dat contains calibration data for air
    CalAQ_SAM[****].dat contains calbration data for underwater measurements
    Back_SAM_[****].dat contains background information
    [****] is the module serial number"""
    files = os.listdir(foldername)
    calOut = None
    inis = []  # allow parsing multiple .ini files
    for f in files:
        out = ''
        if f.endswith('.dat'):
            print("\tparsing {0}".format(f), file=sys.stdout)
            out = _ParseDatFile(os.path.join(foldername, f))
            if out['IDDataTypeSub1'] == 'BACK':
                back = out
            elif out['IDDataTypeSub1'] == 'CAL':
                if out['IDDataTypeSub2'].startswith('AIR'):
                    cal_air = out
                elif out['IDDataTypeSub2'].startswith('AQ'):
                    cal_water = out
        elif f.endswith('.ini'):
            print("\tparsing {0}".format(f), file=sys.stdout)
            iniOut = _ParseIniFile(os.path.join(foldername, f))
            inis.append(iniOut)
        if len(inis) == 1:
            ini = inis[0]
        else:
            for key in ['DeviceType', 'SensorName', 'SAMDevice',
                        'IDDeviceTypeSub1', 'IDDeviceTypeSub2',
                        'DarkPixelStart', 'DarkPixelStop', 'Reverse',
                        'WavelengthRange',
                        'c0s', 'c1s', 'c2s', 'c3s', 'cs']:
                    n = [getattr(z, key) for z in inis if hasattr(z, key)]
                    if len(n) > 0:
                        setattr(ini, key, n[0])
    if back and cal_air and cal_water and ini:
        calOut = Cal()
        calOut.SAMDevice_Aqua = cal_water['IDDevice']
        calOut.SAMDevice_Air = cal_air['IDDevice']
        calOut.SAMDevice_Back = back['IDDevice']
        calOut.SAMDateTime_Aqua = cal_water['CalDateTime']
        calOut.SAMDateTime_Air = cal_air['CalDateTime']
        calOut.SAMDateTime_Back = back['CalDateTime']
        calOut.SAMspectrum_Aqua = cal_water['spectrum0']
        calOut.SAMspectrum_Air = cal_air['spectrum0']
        calOut.SAMspectrum_Back0 = back['spectrum0']
        calOut.SAMspectrum_Back1 = back['spectrum1']
        calOut.ini = ini
    return calOut


def _ParseDatFile(filename):
    with open(filename, 'r') as f:
        line = ''
        IDDevice, TypeSub1, TypeSub2, CalDateTime = None, None, None, None
        spectrum0, spectrum1 = [], []
        while not line.startswith('[DATA]'):
            line = f.readline()
            if line.startswith('IDDevice'):
                IDDevice = line.split('=')[1].strip().split('_')[1]  # serial n
            if line.startswith('IDDataTypeSub1'):
                TypeSub1 = line.split('=')[-1].upper().strip()  # BACK or CAL
            if line.startswith('IDDataTypeSub2'):
                TypeSub2 = line.split('=')[-1].upper().strip()  # AIR or AQUA
            if line.startswith('DateTime'):
                t = line.split('=')[-1].strip()
                CalDateTime = datetime.datetime.strptime(t,
                                                         '%Y-%m-%d %H:%M:%S')
        line = f.readline()  # 1st line of data
        while not line.startswith('[END] of [DATA]'):
            spectrum0.append([float(i) for i in line.split()][1])
            spectrum1.append([float(i) for i in line.split()][2])
            line = f.readline()
        outdict = {'IDDevice': IDDevice, 'IDDataTypeSub1': TypeSub1,
                   'IDDataTypeSub2': TypeSub2, 'CalDateTime': CalDateTime,
                   'spectrum0': spectrum0, 'spectrum1': spectrum1}
    return outdict


def _ParseIniFile(filename):
    """parse ini files"""
    with open(filename, 'r') as f:
        f.seek(0, 2)
        eof = f.tell()
        f.seek(0, 0)
        pos = f.tell()
        firstread1, firstread2, firstread3 = False, False, False
        line = ''
        iniOut = Ini()
        while not pos == eof:
            pos = f.tell()
            line = f.readline()
            if line.startswith('IDDevice') and not firstread1:
                iniOut.DeviceType = line.split('=')[1].strip().split('_')[0]
                iniOut.SensorName = line.split('=')[1].strip().split('_')[1]
                firstread1 = True
            if line.startswith('IDDeviceTypeSub1') and not firstread2:
                iniOut.DeviceTypeSub1 = line.split('=')[1].strip()
                firstread2 = True
            if line.startswith('IDDeviceTypeSub2') and not firstread3:
                iniOut.DeviceTypeSub2 = line.split('=')[1].strip()
                firstread3 = True
            if line.startswith('IDDeviceMaster'):
                if len(line.split('=')[1].strip()) > 0:
                    iniOut.DeviceType = line.split('=')[1]\
                        .strip().split('_')[0]
                    iniOut.SensorName = line.split('=')[1]\
                        .strip().split('_')[1]
            if line.startswith('IDDeviceSAM'):
                iniOut.SAMDevice = line.split('=')[1].strip().split('_')[1]
            if line.startswith('DarkPixelStart'):
                iniOut.DarkPixelStart = int(line.split('=')[1].strip())
            if line.startswith('DarkPixelStop'):
                iniOut.DarkPixelStop = int(line.split('=')[1].strip())
            if line.startswith('Reverse'):
                iniOut.Reverse = int(line.split('=')[1].strip())
            if line.startswith('WavelengthRange'):
                iniOut.WavelengthRange = [float(x) for x in line.split('=')[1]
                                          .strip().split('..')]
            if line.startswith('c0s'):
                iniOut.c0s = float(line.split('=')[1].strip())
            if line.startswith('c1s'):
                iniOut.c1s = float(line.split('=')[1].strip())
            if line.startswith('c2s'):
                iniOut.c2s = float(line.split('=')[1].strip())
            if line.startswith('c3s'):
                iniOut.c3s = float(line.split('=')[1].strip())
            if line.startswith('cs'):  # not present in older versions
                iniOut.cs = float(line.split('=')[1].strip())
        return iniOut


def raw2cal_Air(spec, msdate, serialn,
                CalData, wlOut=np.arange(320, 955, 3.3)):
    """Calibration IN AIR according to Trios manual, page 13+
    * spec = raw spectrum (list of int)\n
    * msdate = measurement datetime\n
    * serialn = module serial number\n
    * CalData = set of calibration data\n
    * wlOut = output wavelength grid (numpy arange)\n"""

    SAMDateTime_Air = [i.SAMDateTime_Air for i in CalData]
    iniSensorName = [i.ini.SensorName for i in CalData]
    out = [np.nan]*len(wlOut)
    msintt = 2*2**(spec[0] & 0b1111)
    # find best calibration match
    calsensind = [i for i, j in enumerate(iniSensorName) if j == serialn]
    # pick most recent (never in future, in case of sensor repair)
    if len(calsensind) > 1:
        calsensdates = [SAMDateTime_Air[i] for i in calsensind]
        tdeltas = [(msdate-x) for x in calsensdates
                   if (msdate-x).days > 0]
        calsensind = [calsensind[tdeltas.index(min(tdeltas))]]

    Cal = CalData[calsensind[0]]
    B0 = np.array(Cal.SAMspectrum_Back0)
    B1 = np.array(Cal.SAMspectrum_Back1)
    S = np.array(Cal.SAMspectrum_Air)
    dp1 = Cal.ini.DarkPixelStart
    dp2 = Cal.ini.DarkPixelStop
    wave = [0.0] * 256
    for i in range(1, len(wave)+1, 1):
        wave[i-1] = (Cal.ini.c0s) + (Cal.ini.c1s*(i+1)) +\
            (Cal.ini.c2s*(i+1)**2) + (Cal.ini.c3s*(i+1)**3)

    t0 = 8192
    t1 = msintt  # in ms
    # pad array with nans and fill with normalized RawData
    M = np.array([np.nan]*256)
    M[0:len(spec)] = np.array(spec)/float(65535)
    # scale Background cal data to integration time
    B = B0 + (t1/t0*B1)
    C = M - B
    # subtract dark offset,
    Offset = np.mean(C[dp1-1:dp2])  # dark pixels
    D = C-Offset
    E = D*(t0/t1)
    # Scale the spectrum to the Air calibration
    F = E/S
    # resample spectrum to a strict 3.3 nm grid
    out = np.interp(wlOut, wave, F)
    return out

# -*- coding: utf-8 -*-
"""
Created on Wed Dec 23 20:18:22 2015

Classes for PyTrios library

Example use:
from TClasses import TProtocolError, TPacket, TChannel

@author: Stefan Simis
"""

import sys
import datetime
import struct
import serial
import numpy as np
from serial import Serial

# global definitions
TIMEOUT_SAM = 12
TIMEOUT_MF = 5


class TSerial(Serial):
    def __init__(self, port, timeout=0.01, baudrate=9600, xonxoff=True,
                 parity='N', stopbits=1, bytesize=8):#, verbosity=1):
        try:
            port = str(port)
            port = "/dev/ttyUSB"+port.strip('/dev/ttyUSB')
            Serial.__init__(self, port)
            self.baudrate = baudrate
            self.timeout = timeout
            self.xonxoff = xonxoff
            self.parity = parity
            self.stopbits = stopbits
            self.bytesize = bytesize
            #self.verbosity = verbosity
        except Exception:
            print("Error connecting to port {0}\n".format(self.port),
                  file=sys.stderr)
            return None


class TProtocolError(Exception):
    def __init__(self, value):
        self.value = value

    def __str__(self):
        return repr(self.value)


class TPackMeasKeyError(Exception):
    def __init__(self, value):
        self.value = value

    def __str__(self):
        return repr(self.value)


class TPacket(object):
    """TrioS sensor data package object"""
    def __init__(self, s2parse=None):
        self.packetType = None
        if s2parse is None:
            return
        self.timeStampPC = datetime.datetime.now()  # time of parsing
        # identity byte 1
        self.id1 = s2parse[0]
        # 3 msb give size of data frame
        self.id1_databytes = 2*2**(s2parse[0] >> 5)
        # 5th bit is for future compatibility
        self.id1_fut = (s2parse[0] & 0b10000) >> 4
        # first 4 lsb are identity bits
        self.id1_id = s2parse[0] & 0b1111
        # error defined in TriOS protocol
        if self.id1_databytes == 256:
            print("TPacket init: Blocksize invalid", file=sys.stderr)
            return
        formatstring = '<BBBBBB'+str(self.id1_databytes)+'BB'
        try:
            Data = struct.unpack(formatstring, s2parse)
        except:
            prettyhex = ":".join("{0:x}".format(c) for c in s2parse)
            print("TPacket init: cannot unpack block:\n\t{0}"
                  .format(prettyhex), file=sys.stderr)
            return
        # interpret framebyte and databytes
        # identity byte 2
        self.id2 = Data[1]
        # module ID byte
        self.moduleID = Data[2]
        # zipped data if 1, original data if 0
        self.moduleID_zipped = Data[2] & 0b1
        # Module I2C address in 7 msb
        self.moduleID_I2Cadd = Data[2] >> 1
        # Framebyte, 0=single or last frame, 255=module info, 254=error message
        self.framebyte = Data[3]
        # 0 = no realtime clock
        self.time1 = Data[4]
        # 0 = no realtime clock
        self.time2 = Data[5]
        self.databytes = Data[6:6+self.id1_databytes]
        self.checkbyte = Data[-1]  # not used
        self.tid1 = hex(self.id1_id)[2:].zfill(2)
        self.tid2 = hex(self.id2)[2:].zfill(2)
        self.tid3 = hex(self.moduleID)[2:].zfill(2)
        self.TID = self.tid1 + self.tid2 + self.tid3

        # PacketType
        if self.framebyte == 254:
            # sensor reports error
            self.packetType = 'error'
            emsg = "TSerial_parse: Instrument reports error, wrong command?"
            prettyhex = ":".join("{0:x}".format(c) for c in s2parse)
            print("{0}\n\t{1}".format(emsg, prettyhex), file=sys.stderr)
            return

        elif self.moduleID == 164:
            # MicroFlu configuration package (address A4)
            self.packetType = 'mfconfig'
            self.microFluConfig = self.MFluConfInterp(self)

        elif self.framebyte == 255:
            self.packetType = 'query'
            self.tchannel = self.QInterp()
            if self.tchannel.TInfo.ModuleType == 'MicroFlu':
                self.MFluReadSettings()
            elif self.tchannel.TInfo.ModuleType in['SAM', 'SAMIP']:
                self.SAMReadSettings()

        elif self.framebyte < 254:
            self.packetType = 'measurement'

    def QInterp(self):
        tchannel = TChannel()
        serlow = self.databytes[0]  # last 2 hex chars of SN
        serhi = self.databytes[1]  # first 2 hex chars of SN
        vals = [2, 4, 8, 9, 10, 12, 16, 20, 24]
        types = ['MicroFlu', 'IOM', 'COM', 'IPS',
                 'SAMIP', 'SCM', 'SAM', 'DFM', 'ADM']
        tchannel.TInfo.TID = self.TID
        tchannel.TInfo.serialn = str.upper(hex(serhi)[-2::]+hex(serlow)[-2::])
        # module type from 5 most sign Bits
        tchannel.TInfo.ModuleType = types[vals.index(serhi >> 3)]
        tchannel.TInfo.Firmware = self.databytes[3] +\
            0.01 * self.databytes[2]
        # operating freq. in MHz
        freqs = [np.nan, 2, 4, 6, 8, 10, 12, 20]
        tchannel.TInfo.ModFreq = freqs[self.databytes[4]]
        return tchannel

    def MFluReadSettings(self):
        "read MicroFlu instrument settings (part of query return)"
        settings = self.tchannel.TMicroFlu.Settings
        # 1 = chl; 2 = blue, 3 = CDOM, 4 = unknown, 5 = Red
        settings.Ftype = self.databytes[5]
        # Internal averaging n samples
        settings.SMit = self.databytes[6]
        # bit 7 = sampling is active
        settings.CtlStart = (self.databytes[7] & 0b10000000) >> 7
        # bit 6 Analog Power (0=OFF, 1=ON)
        settings.CtlAnalog = (self.databytes[7] & 0b01000000) >> 6
        # Bit 5: Range (0= highAmp, 1= lowAmp)
        settings.CtlRange = (self.databytes[7] & 0b00100000) >> 5
        # Bit 4: AutoRange (0= OFF, 1= ON)
        settings.CtlAutoR = (self.databytes[7] & 0b00010000) >> 4
        # Bit 3: Datastream (0= OnDemand, 1= Continously)
        settings.CtlContn = (self.databytes[7] & 0b00001000) >> 3

    def SAMReadSettings(self):
        "read SAM instrument settings (part of query return)"
        settings = self.tchannel.TSAM.Settings
        settings.SAMConfiguration = self.databytes[5]
        settings.SAMRange = self.databytes[6]
        settings.SAMStatus = self.databytes[7]

    def MFluConfInterp(self):
        "read MicroFlu configuration (not part of query request)"
        mfcfg = MFROMConfig()
        mfcfg.IntAvg = self.databytes[3]
        # 1 is Start measuring on startup
        mfcfg.Auto = (self.databytes[4] & 0b00001000) >> 3
        # 0/1/2 = high/auto/low
        mfcfg.Ampl = self.databytes[4] >> 4
        mfcfg.HighA_Offset = np.float(self.databytes[5] * 256 +
                                      self.databytes[6])
        mfcfg.LowA_Offset = np.float(self.databytes[7] * 256 +
                                     self.databytes[8])
        mfcfg.HighA_Scale = np.float(self.databytes[9])\
            + np.float(self.databytes[10]) / 256
        mfcfg.LowA_Scale = np.float(self.Databytes[11])\
            + np.float(self.databytes[12]) / 256
        return mfcfg

    def __repr__(self):
        msg = "<PyTrios {0} TPacket: {1}, ".format(self.packetType,
                                                   self.timeStampPC)\
              + "Framebyte {0} at {1}>".format(self.framebyte, hex(id(self)))
        return msg


class SAMSettings(object):
    def __init__(self, SAMConfiguration=None, SAMRange=None,
                 SAMStatus=None):
        pass


class TSAM(object):
    """Represents a SAM instrument:\n
    *Settings* = Sensor specific settings\n
    *lastRawSAM* = last uncalibrated spectrum from SAM unit\n
    *lastRawSAMTime* = Reception timestamp of last spectrum\n"""
    def __init__(self, Settings=SAMSettings, dataframes=[[None]]*8,
                 lastRawSAM=None, lastRawSAMTime=None, lastIntTime=None):
        self.Settings = Settings()
        self.dataframes = dataframes
        self.lastRawSAMTime = lastRawSAMTime
        self.lastRawSAM = lastRawSAM
        self.lastIntTime = lastIntTime

    def __repr__(self):
        ltime = self.lastRawSAMTime
        msg = "<PyTrios SAM, last measurement at {0}>".format(ltime)
        return msg


class TInfo(object):
    """Basic information about connected instrument:\n
    *TID* = Address\n
    *ModuleType* = SAM, SAMIP, MicroFlu\n
    *Firmware* = Sensor firmware\n
    *ModFreq* = Sensor internal frequency\n"""
    def __init__(self, TID=None, ModuleType=None, Firmware=None,
                 ModFreq=None, serialn=None):
        self.TID = TID
        self.ModuleType = ModuleType
        self.Firmware = Firmware
        self.ModFreq = ModFreq
        self.serialn = serialn

    def __repr__(self):
        msg = "<PyTrios {0}, TID={1}, serialn={2}, Firmware={3}>"\
            .format(self.ModuleType, self.TID,
                    self.serialn, self.Firmware)
        return msg


class MFSettings(object):
    """Microflu sensor specific settings\n
    *Ftype*:     1/2/3/4/5 = Chl, blue, CDOM, unkonwn, Red\n
    *Mit*: internal averaging\n
    *CtlStart*: sensor is active\n*CtlAnalog*:analog output on\n
    *CtlRange*: 0/1 = high/low gain\n
    *CtlAutoR*: 1/0 = Auto-range On/Off\n
    *CtlContn*: 0/1 = On Demand / Continuous\n"""
    def __init__(self, Ftype=None, SMit=None,
                 CtlStart=None, CtlAnalog=None, CtlRange=None,
                 CtlAutoR=None, CtlContn=None):
        pass


class MFROMConfig(object):
    "IntAvg, Auto, Ampl, HighA_Offset, LowA_Offset, HighA_Scale, LowA_Scale"
    def __init__(self, IntAvg=None, Auto=None, Ampl=None,
                 HighA_Offset=None, LowA_Offset=None,
                 HighA_Scale=None, LowA_Scale=None):
        pass


class TMicroFlu(object):
    """Represents a MicroFlu instrument:\n
    *Settings* = Sensor settings\n
    *ROMConfig* = Sensor startup configuration\n
    *lastFluRaw* = last raw measurement (amplification, value)\n
    *lastFluCal* = last calibrated measurement\n
    *lastFluTime* = local timestamp of last measurement\n"""
    def __init__(self, Settings=MFSettings, ROMConfig=MFROMConfig,
                 lastFluRaw=None, lastFluCal=None, lastFluTime=None):
        self.Settings = Settings()
        self.ROMConfig = ROMConfig()
        self.lastfluRaw = lastFluRaw
        self.lastFluCal = lastFluCal
        self.lastFluTime = lastFluTime

    def __repr__(self):
        ftypes = ['', 'Chl', 'Blue', 'CDOM']
        try:
            msg = "<PyTrios MicroFlu-{0}, Averaging={1}, \
                Continuous={2}, Autorange={3}, \
                last measurement={4}: {5}>".format(ftypes[self.Settings.Ftype],
                                                   self.Settings.Mit,
                                                   self.Settings.CtlContn,
                                                   self.Settings.CtlAutoR,
                                                   self.lastFluTime,
                                                   self.lastFluCal)
            return msg
        except:
            return str(None)


class TChannel(object):
    """Stores Trios Instrument info/data, identified by address (self.TID)"""
    def __init__(self, TInfo=TInfo, TMicroFlu=TMicroFlu,
                 TSAM=TSAM, verbosity=3):
        self.TInfo = TInfo()
        self.TMicroFlu = TMicroFlu()
        self.TSAM = TSAM()
        self.verbosity = verbosity
        self.serial = None  # recursively link ser object when query received
        self.lasttrigger = None
        self.lastcommand = 'query'

    def is_pending(self):
        '''check whether new measurement is pending (False if timed out)'''
        if (self.lastcommand != 'measurement')\
                or (self.lasttrigger is None)\
                or (self.is_finished()):
            return False
        elapsed = datetime.datetime.now() - self.lasttrigger
        if self.TInfo.ModuleType in ['SAM', 'SAMIP']:
            return elapsed.total_seconds() < TIMEOUT_SAM
        elif self.TInfo.ModuleType == 'MicroFlu':
            return elapsed.total_seconds() < TIMEOUT_MF

    def is_finished(self):
        '''check whether new measurement has arrived since last trigger'''
        lastmeas = None
        if self.lastcommand != 'measurement' or self.lasttrigger is None:
            return False
        if self.TInfo.ModuleType in ['SAM', 'SAMIP']:
            lastmeas = self.TSAM.lastRawSAMTime
        elif self.TInfo.ModuleType == 'MicroFlu':
            lastmeas = self.TMicroFlu.lastFluTime
        if lastmeas is not None:
            return lastmeas > self.lasttrigger

    def _send_command(self, ser, command, par='00'):
        if self.TInfo.ModuleType in ['SAM', 'SAMIP']:
            commandset = 'SAM'
        elif self.TInfo.ModuleType == 'MicroFlu':
            commandset = 'MicroFlu'
        else:
            if self.verbosity >= 1:
                print("command not imnplemented for moduletype {0}"
                      .format(self.TInfo.ModuleType), file=sys.stderr)
            return
        ipschan = self.TInfo.TID[0:2]
        TCommandSend(ser, commandset, command, ipschan, par1=par)

    def query(self, ser, trigger=datetime.datetime.now()):
        self.lastcommand = 'query'
        self.lasttrigger = trigger
        self._send_command(ser, command='query')

    def startIntAuto(self, ser, trigger=datetime.datetime.now()):
        if self.TInfo.ModuleType not in ['SAM', 'SAMIP']:
            if self.verbosity >= 1:
                print("tchannel: startIntAuto not implemented for {0}"
                      .format(self.TInfo.ModuleType), file=sys.stderr)
            return
        self.lastcommand = 'measurement'
        self.lasttrigger = trigger
        self._send_command(ser, command='startIntAuto', par='00')

    def startIntSet(self, ser, inttime, trigger=datetime.datetime.now()):
        """ *inttime in ms to be one of
        0 (autorange), 8 , 16 32 64 128 256 512 1024 2048 4096 8192
        """
        if self.TInfo.ModuleType not in ['SAM', 'SAMIP']:
            if self.verbosity >= 1:
                print("tchannel: startIntSet not implemented for {0}"
                      .format(self.TInfo.ModuleType), file=sys.stderr)
            return
        inttimes = {0: '00', 8: '02', 16: '03', 32: '04', 64: '05',
                    128: '06', 256: '07', 512: '08', 1024: '09',
                    2048: '0A', 4096: '0B', 8192: '0C'}
        par = inttimes[inttime]
        self.lastcommand = 'measurement'
        self.lasttrigger = trigger
        self._send_command(ser, command='startIntSet', par=par)

    def __repr__(self):
        try:
            msg = "<PyTrios channel {0}: {1} {2} at {3}>"\
                .format(self.TInfo.TID,
                        self.TInfo.ModuleType,
                        self.TInfo.serialn,
                        hex(id(self)))
            return msg
        except Exception as e:
            print(e)  # debug
            return "<PyTrios channel (no info)>"


def TCommandSend(ser, commandset, command='query', ipschan='00', par1='00'):
    """Send command to a TriOS device.\n
    Device configuration commands are not supported.\n

    Command sets implemented:
        QUERY, not instrument specific: TCommandSend(ser,None,'query')
        *MicroFlu*  e.g. TCommandSend(ser,'MicroFlu',command='cont_off')
        *SAM*       e.g. TCommandSend(ser,'SAM',command='startIntAuto')

    The reboot command is not implemented until it is better understood:\n
    SAM: 'reboot':
        bytearray.fromhex("23 "+str(ipschan)+" 00 80 00 00 00 01")\n
    Micrflu: 'reboot':
        bytearray.fromhex("23 "+str(ipschan)+" 00 00 00 00 00 01")\n

    For sensors on an IPS4 box, specify channel as
    *ipschan* = '02','04','06','08' for channels 1-4 respectively.\n\n
    *par1* is the first user-configurable parameter mentioned in
    the documentation, even when listed as parameter2 in the docs.
    Most commands require at most one argument.\n\n
    """
    commandsetdict = {None: 0, 'MicroFlu': 1, 'SAM': 2}
    commanddict = ['']*len(commandsetdict)
    commanddict[0] = {'query': bytearray.fromhex("23 "
                      + str(ipschan) + " 00 80 B0 00 00 01")}
    commanddict[1] = {
        'ReadCfg': bytearray.fromhex("23 " + str(ipschan)
                                     + " 00 00 c0 00 00 01 23 " + ipschan
                                     + " 00 00 08 00 03 01 23 " + ipschan
                                     + " 00 00 08 00 04 01 23 " + ipschan
                                     + " 00 00 a0 a4 10 01"),
        'cont_on': bytearray.fromhex("23 " + str(ipschan)
                                     + " 00 00 78 0f 01 01"),
        'cont_off': bytearray.fromhex("23 " + str(ipschan)
                                      + " 00 00 78 0f 00 01"),
        'query': bytearray.fromhex("23 " + str(ipschan)
                                   + " 00 00 B0 00 00 01"),
        'start': bytearray.fromhex("23 " + str(ipschan)
                                   + " 00 00 A8 00 81 01"),
        'stop': bytearray.fromhex("23 " + str(ipschan)
                                  + " 00 00 A8 00 82 01"),
        'autoamp_on': bytearray.fromhex("23 " + str(ipschan)
                                        + " 00 00 78 06 01 01"),
        'autoamp_off': bytearray.fromhex("23 " + str(ipschan)
                                         + " 00 00 78 06 00 01"),
        'lowamp_on': bytearray.fromhex("23 " + str(ipschan)
                                       + " 00 00 78 05 01 01"),
        'lowamp_off': bytearray.fromhex("23 " + str(ipschan)
                                        + " 00 00 78 05 00 01"),
        'int_avg': bytearray.fromhex("23 " + str(ipschan)
                                     + " 00 00 78 04 " + str(par1) + " 01")}

    # SAM address = 80
    # SAMIP address = 80 but 20 for IP and 30 for SAM commands
    commanddict[2] = {
        'startIntAuto': bytearray.fromhex("23 " + str(ipschan)
                                          + " 00 30 78 05 00 01 23 "
                                          + str(ipschan)
                                          + " 00 80 A8 00 81 01"),
        # valid par1 values for startIntset:
        'startIntSet': bytearray.fromhex("23 " + str(ipschan)
                                         + " 00 30 78 05 " + str(par1)
                                         + " 01 23 " + str(ipschan)
                                         + " 00 80 A8 00 81 01"),
        'cont_mode_off': bytearray.fromhex("23 " + str(ipschan)
                                           + " 00 30 78 F0 02 01"),
        'cont_mode_on': bytearray.fromhex("23 " + str(ipschan)
                                          + " 00 30 78 F0 03 01"),
        'setIntTime': bytearray.fromhex("23 " + str(ipschan)
                                        + " 00 30 78 05 "+str(par1)+" 01"),
        'sleep': bytearray.fromhex("23 " + str(ipschan)
                                   + " 00 80 A0 00 00 01"),
        'setbaud': bytearray.fromhex("23 " + str(ipschan)
                                     + " 00 30 50 01 "+str(par1)+" 01"),
        'fastauto': bytearray.fromhex("23 " + str(ipschan)
                                      + " 00 30 50 01 0C 01 23 " + str(ipschan)
                                      + " 00 30 78 F0 03 01"),
        'query_sam': bytearray.fromhex("23 " + str(ipschan)
                                       + " 00 30 B0 00 00 01")}

    """
    Note baudrate changes did not function with an IPS box. Test further.
    valid (hex) par1 values for setbaud:
    2 400 baud: par = CF
    4 800 baud: par = 67
    9 600 baud: par = 33
    19 200 baud: par = 19
    38 400 baud: par = 0C
    (57 600 baud: par = 08, only at 8MHz)

    valid (hex) pars for inttime:
    00: autorange
    02 8ms, 03 16ms, 04 32ms, 05 64ms, 06 128ms, 07 256ms
    08 512ms, 09 1024ms, 0A 2048ms, 0B 4096ms, 0C 8192ms
    """

    commandhex = commanddict[commandsetdict[commandset]][command]
    try:
        if ser.out_waiting > 0:
            ser.flush()
        ser.write(commandhex)
        if ser.verbosity >= 3:
            print("{0} written to {1} ({2})".format(command,
                                                    ser.port,
                                                    ipschan), file=sys.stdout)
    except serial.SerialException as e:
        print(e.message, file=sys.stderr)
        pass
    except KeyError:
        if ser.verbosity >= 1:
            emsg = "TCommandSend: Command or command set not recognized"
            print(emsg, file=sys.stderr)
        pass
    except Exception:
        if ser.verbosity >= 1:
            emsg = "TCommandSend: Unidentified error, please check format"
            print(emsg, file=sys.stderr)
        pass

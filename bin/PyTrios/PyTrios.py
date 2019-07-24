# -*- coding: utf-8 -*-
"""
Implements serial communication with TriOS sensors in Python\n

Copyright (C) 2015  Stefan Simis, Plymouth Marine Laboratory\n
Email stsi[_at_]pml .ac. uk

    This program is free software: you can redistribute it and/or modify
    it under the terms of the GNU General Public License as published by
    the Free Software Foundation, either version 3 of the License, or
    (at your option) any later version.

    This program is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    GNU General Public License for more details.

    You should have received a copy of the GNU General Public License
    along with this program.  If not, see <http://www.gnu.org/licenses/>.

Note: PyTrios uses the *serial* module by Chris Liechti

Tested on Python 2.7.3\n
Last update: see __version__\n

*For example use please see the enclosed PyTrios_Examples.py script.*
"""

import sys
import time
import struct
import numpy as np
import threading
from .TClasses import TProtocolError, TPackMeasKeyError,\
    TPacket, TSerial, TCommandSend

__version__ = "2015.12.28"
__author__ = "Stefan Simis"
__license__ = "GPL v3"

tchannels = {}


def handlePacket(ser, packet):
    global tchannels
    "Directs incoming packets to appropriate interpreters, updating tchannels"
    p = packet  # shorten
    if p.packetType is None:
        if ser.verbosity >= 1:
            print("handlePacket: empty packet", file=sys.stderr)

    if p.packetType == 'error':
        if ser.verbosity >= 1:
            print("handlePacket: error packet", file=sys.stderr)

    if p.packetType == 'query':
        if p.tchannel.TInfo.ModuleType == 'IPS':
            for c in ['02', '04', '06', '08']:
                # query submodule information
                TCommandSend(ser, commandset=None, ipschan=c, command='query')
                TCommandSend(ser, commandset='SAM', ipschan=c,
                             command='query_sam')

    if p.packetType == 'query' and p.tchannel.TInfo.ModuleType == 'MicroFlu':
        ch = p.tchannel
        ch.serial = ser
        port_tid = ser.port + '_' + p.TID
        tchannels[port_tid] = ch
        # Follow microflu query by ROM Config request for full sensor info
        TCommandSend(ser, commandset='MicroFlu',
                     ipschan=ch.TInfo.TID[0:2],
                     command='ReadCfg')
        # after config request reset the sensor to previous sampling state
        cont_on_off = {0: 'cont_off', 1: 'cont_on'}
        command = cont_on_off[ch.TMicroFlu.Settings.CtlContn]
        TCommandSend(ser, commandset='MicroFlu',
                     ipschan=ch.TInfo.TID[0:2], command=command)

    if p.packetType == 'mfconfig':
        port_tid = ser.port + '_' + p.TID
        # update ROMconfig on existing channel
        try:
            tchannels[port_tid].ROMConfig = p.microFluConfig
        except KeyError:
            if ser.verbosity >= 1:
                emsg = "handlePacket (mfconfig):" +\
                    " no MicroFlu registered on {0}"\
                    .format(port_tid)
                raise Warning(emsg)
        except:
            if ser.verbosity >= 1:
                emsg = "handlePacket (mfconfig): MicroFlu " +\
                    " config update failed on {0}"\
                    .format(port_tid)
                raise Warning(emsg)

    if p.packetType == 'query' and\
            p.tchannel.TInfo.ModuleType in ['SAMIP', 'SAM']:
        ch = p.tchannel
        ch.serial = ser
        port_tid = ser.port + '_' + p.TID
        tchannels[port_tid] = ch

    if p.packetType == 'measurement':
        if int(p.tid3) in [20, 30]:
            port_tid = ser.port + '_' + p.TID[0:4] + '80'
        else:
            port_tid = ser.port + '_' + p.TID
        interpreter = ''
        try:
            ch = tchannels[port_tid]
        except KeyError:
            emsg = "handlePacket (measurement):" +\
                " invalid address: {0}".format(port_tid)
            raise TPackMeasKeyError(emsg)
        try:
            if int(p.tid3) == 0:
                if tchannels[port_tid].TInfo.ModuleType in['SAM', 'SAMIP']:
                    interpreter = 'SAM'
                elif tchannels[port_tid].TInfo.ModuleType == 'MicroFlu':
                    interpreter = 'MicroFlu'
            elif int(p.tid3) == 20 and tchannels[port_tid].TInfo.ModuleType\
                    in ['COM', 'SAMIP']:
                # p.TID = p.tid1 + p.tid2 + '80'  # probably not necessary
                interpreter = 'ADM'
                if ch.verbosity >= 4:
                    print("ADM measurement received (not implemented",
                          file=sys.stdout)
            elif int(p.tid3) == 30 and tchannels[port_tid].TInfo.ModuleType\
                    in ['COM', 'SAMIP']:
                # p.TID = p.tid1 + p.tid2 + '80'  # probably not necessary
                interpreter = 'SAM'
            # port_tid = ser.port + '_' + p.TID  # probably not necessary
            if interpreter == 'MicroFlu':
                tchannels[port_tid] = MFInterpreter(tchannels[port_tid], p)

            elif interpreter == 'SAM':
                ch = SAMInterpreter(tchannels[port_tid], p)
                tchannels[port_tid] = ch
        except Exception as emsg:
            raise TProtocolError(emsg)


def SAMInterpreter(regch, packet):
    formatstring = '<'+'H'*int(packet.id1_databytes/2)
    rawdata = bytearray(y for y in packet.databytes)
    LEdata = struct.unpack(formatstring, rawdata)
    """ sloppy code comment:
    In the following, if we place LEdata directly into the dataframes slice
    it will be overwritten upon prompt arrival of a new packet, even if this
    concerns a different entry of the tchannels dictionary. Odd!
    Reading and writing back the list of dataframes first circumvents this.
    Packets arriving in rapid succession re-use memory blocks. So this
    possibly points to sloppy garbage collection?
    """
    dataframes = regch.TSAM.dataframes[:]
    dataframes[packet.framebyte] = LEdata
    regch.TSAM.dataframes = dataframes
    if regch.verbosity >= 4:
        print("SAMInterpreter: Spectrum framebyte {0} from {1} at {2}/{3}"
              .format(packet.framebyte, regch.TInfo.serialn,
                      regch.serial.port, regch.TInfo.TID),
              file=sys.stdout)
    if packet.framebyte == 0:
        frames = regch.TSAM.dataframes
        if sum(y is None for y in frames) == 0:
            outspec = []
            for sublist in frames:
                sl = list(sublist)
                sl.reverse()
                outspec = outspec+sl
            outspec.reverse()  # assuming this is not a UV sensor..
            regch.TSAM.lastRawSAM = outspec
            regch.TSAM.lastRawSAMTime = packet.timeStampPC
            msintt = 2*2**(outspec[0] & 0b1111)  # integration time
            regch.TSAM.lastIntTime = msintt
            # reset to receive the next spectrum
            regch.TSAM.dataframes = [[None]]*8
            if regch.verbosity >= 2:
                delay = packet.timeStampPC - regch.lasttrigger
                print("SAMInterpreter: Spectrum ({3}ms) from {0}, {1} ({2} s)"
                      .format(regch.TInfo.serialn, regch.TInfo.TID,
                              delay.total_seconds(), msintt),
                      file=sys.stdout)
        else:
            emsg = "SAM Interpreter: Incomplete spectrum, discarded"
            print(emsg, file=sys.stderr)
            raise TProtocolError(emsg)
            # reset to receive the next spectrum
            regch.TSAM.dataframes = [[None]]*8
    return regch


def MFInterpreter(regch, packet):
    # byteorder is big endian although documentation suggests different
    formatstring = '>'+'H'*int(packet.id1_databytes/2)
    BEdata = struct.unpack(formatstring,
                           ''.join([chr(y) for y in packet.Databytes]))
    gain = BEdata[0] >> 15  # 0 = high gain, 1 = low gain
    data = BEdata[0] & 0b111111111111
    regch.TMicroFlu.lastFluRaw = [gain, data]
    regch.TMicroFlu.lastFluTime = packet.timeStampPC
    if gain == 1:
        regch.TMicroFlu.lastFluCal = 100*data/np.float(2048)
    if gain == 0:
        regch.TMicroFlu.lastFluCal = 10*data/np.float(2048)
        if regch.verbosity > 1:
            gains = ['H', 'L']
            ftypes = [None, 'Chl', 'Blue', 'CDOM', 'unknown', 'Red']
            ftype = ftypes[regch.TMicroFlu.Settings.Ftype]
            if regch.verbosity >= 3:
                print("MicroFlu Interpreter: Microflu-{0} data on {1}/{2}\n\t"
                      + "gain {3}, raw {4}, cal {5}"
                      .format(ftype, regch.serial.port, regch.TInfo.TID,
                              gains[gain], data,
                              regch.TMicroFlu.lastFluCal), file=sys.stdout)
    return regch


def TMonitor(ports, baudrate=9600):
    """Initiate serial port listening threads. Start here."""
    try:
        if not type(ports) is list:
            ports = [ports]
        COMobjslst = []
        for p in ports:
            ser = TSerial(p, timeout=0.01, baudrate=baudrate, xonxoff=True,
                          parity='N', stopbits=1, bytesize=8)
            if ser.isOpen():
                # associated port listening thread
                ser.threadlisten = threading.Thread(target=TListen,
                                                    args=(ser,))
                ser.threadlive = threading.Event()   # clear to stop thread
                ser.threadactive = threading.Event()  # clear to pause thread
                ser.threadlive.set()
                ser.threadactive.set()
                COMobjslst.append(ser)
                ser.threadlisten.start()  # start thread
                ser.threadlisten.join(0.01)  # join calling thread
        if sum([1 for c in COMobjslst if c.isOpen()]) == 0:
            raise ValueError("TMonitor: no COM ports to watch")
            sys.exit(1)
        return COMobjslst
    except:
        TClose(COMobjslst)
        print("Uncaught exception. Threads and serial port(s) stopped.")
        raise


def _get_s2parse(s, ser):
    "extract data blocks from serial buffer"
    try:
        bitsatport = ser.inWaiting()
        if max([bitsatport, len(s)]) < 1:
            return s, None

        s = s+ser.read(1000)
        first, last = s.find(b'#'), s.rfind(b'#')
        s = TStrRepl(s)  # correct replacement chars
        if first < 0 or not last >= first:
            return s, None

        s = s[s.find(b'#', 0):]  # omit incomplete sequence at start
        if len(s) <= 1:  # 1st byte after # = size
            return s, None

        ndatabytes = 2*2**(s[1] >> 5)
        blocklength = 8+ndatabytes
        if len(s) >= blocklength:
            s2parse = s[1:blocklength]  # block to parse
            if ser.verbosity >= 4:
                prettyhex = ":".join("{0:x}".format(c) for c in s2parse)
                print("TListen: {0}".format(prettyhex), file=sys.stdout)
            s = s[blocklength:]  # remainder to next cycle
            return s, s2parse
        else:
            return s, None
    except TProtocolError as e:
        print("{0} {1}".format(e.message, ser.port), file=sys.stderr)
        pass
    except Exception:
        raise


def TListen(ser):
    """Monitors and maintains a serial port instance *ser*"""
    print("Start listening thread on {0}".format(ser.port), file=sys.stdout)
    s = b""
    timeouttimer = 0
    while ser.threadlive.isSet():
        while ser.threadactive.isSet():
            s, s2parse = _get_s2parse(s, ser)
            if s2parse is not None:
                timeouttimer = 0     # reset timeout
                try:
                    packet = TPacket(s2parse)
                    if packet is None:
                        if ser.verbosity >= 1:
                            print("TListen: bad packet on port {0}"
                                  .format(ser.port), file=sys.stderr)
                    else:
                        handlePacket(ser, packet)
                except TProtocolError as msg:
                    raise Warning(msg)
                except TPackMeasKeyError as msg:
                    raise Warning(msg)
                    if ser.isOpen:
                        ser.flushOutput()
                        ser.flushInput()
                        s = ''
                        # resend query?
                    else:
                        raise Exception('Unrecoverable error - reboot sensors')
                        sys.exit(1)
                except Exception as msg:
                    raise Warning(msg)
            elif timeouttimer - time.time() > 1:
                s = ""  # clear the buffer
                emsg = "Timeout while parsing buffer"
                raise Warning(emsg)
            elif timeouttimer == 0:  # set a new timer
                timeouttimer = time.time()
            time.sleep(0.02)  # pace this cycle
        time.sleep(0.1)  # check threadactive periodically to resume


def TClose(COMs):
    errors = ''
    if not type(COMs) is list:
        COMs = [COMs]
    for c in COMs:
        print("Closing ports", file=sys.stdout)
        try:
            c.threadactive.clear()
            c.threadlive.clear()
            c.close()
        except Exception:
            print("Error closing port {0}".format(c.port), file=sys.stderr)
            errors = '(with errors)'
            pass
    print("Finished closing ports {0}".format(errors), file=sys.stdout)


def TStrRepl(s):
    s = s.replace(b'@g', b'\x13')  # correct for escape chars (xOFF)
    s = s.replace(b'@f', b'\x11')  # correct for escape chars (xOn)
    s = s.replace(b'@e', b'\x23')  # correct for escape chars (data start #)
    s = s.replace(b'@d', b'\x40')  # correct for escape chars (escape char @)
    return s

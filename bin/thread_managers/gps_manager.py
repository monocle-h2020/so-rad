#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
GPS Manager

Creates GPS Manager objects which create serial reader threads for the GPS
sensor it is instantiated with. This takes in the serial data and parses it
using a library of GPS NMEA strings to extract the information.
"""
import datetime
import logging
import re
import threading
import time
import codecs
import struct
from numpy import min
import math
from pyubx2 import UBXReader

log = logging.getLogger('gps')


class GPSSerialReader(threading.Thread):
    """
    Thread to read from a serial port, used by all device interface classes
    """
    def __init__(self, serial_port, parent):
        threading.Thread.__init__(self)
        self.serial_port = serial_port
        self.parent = parent

        self.observers = []

        self.current_gps_dict = None
        log.info("Starting GPS reader thread")

    def run(self):
        """
        Main loop of the thread.

        This will run and read from a GPS string and when it is valid and decoded it'll be passed via the
        observer design pattern.
        """

        protocol = type(self.parent).__name__

        bitOfData = b''
        timeToSleep = 0.1
        lineCount = 0
        serialReader = self.serial_port
        LotOfData = []
        buffer_bytes_per_minute = 100
        buffer_bytes_total = 0
        buffer_bytes_from_read = 0
        # from pymemcache.client import base
        dataDictionary = {}
        minute_start_counter = datetime.datetime.now()

        counter = 0

        while not self.parent.stop_gps:
            counter +=1
            if protocol == "RTKUBX":
                if counter<=1:
                    log.warning("The homebrew RTKUBX protocol will be deprecated. Please test functionality on this system with PYUPBX2")
            elif protocol == "NMEA0183":
                old_gps_time = self.parent.datetime
            elif protocol == "PYUBX2":
                pass

            else:
                log.error("gps protocol '{0}' not implemented".format(protocol))

            if self.serial_port.inWaiting() > 1000:
                # if too much data in buffer, throw it away
                log.warning(">1kb in gps buffer on port {0}. Clearing input buffer.".format(self.serial_port.port))
                self.serial_port.reset_input_buffer()
                time.sleep(0.001)

                continue

            if protocol == "NMEA0183":
                if self.serial_port.inWaiting() > 0:
                    # if there is data, read it
                    gps_string = self.serial_port.readline()
                else:
                    time.sleep(0.01)
                    # sleep a bit longer than usual
                    continue

                log.debug("NMEA: {0}".format(gps_string.strip()))

                try:
                    self.current_gps_dict = GPSParser.parse(codecs.decode(gps_string, 'utf-8'))
                    self.notify_observers()
                except UnicodeDecodeError:
                    log.warning("UnicodeDecodeError on GPS string: {0}".format(gps_string))


            elif protocol == "RTKUBX":
                try:
                    dataDictionary, LotOfData = readFromUblox(dataDictionary, timeToSleep, serialReader, LotOfData, self, counter)
                    log.debug("Lines parsed: {0}".format(lineCount))

                except Exception as error:
                    log.exception("Error reading from ublox 8: {}".format(error))


            elif protocol == "PYUBX2":
                try:
                    dataDictionary = pyubx2_interface(dataDictionary, timeToSleep, serialReader, self, counter)

                except Exception as error:
                    log.exception("Error reading from ublox 9: {}".format(error))

            time.sleep(0.001)  # Sleep for a millisecond so that it doesn't max CPU


    def register_observer(self, observer):
        """
        Register an observer of the GPS thread.

        Observers must implement a method called "update"
        :param observer: An observer object.
        :type observer: object
        """
        if not observer in self.observers:
            self.observers.append(observer)

    def notify_observers(self):
        """
        This pushes the GPS dict to all observers.
        """
        if self.current_gps_dict is not None:
            for observer in self.observers:
                observer.update(self.current_gps_dict)


def pyubx2_interface(dataDictionary, timeToSleep, serialReader, self, counter):
    # Sleep so the program isn't spamming buffer with read requests
    time.sleep(timeToSleep)
    ubr = UBXReader(serialReader, protfilter=3, quitonerror=1, validate=1, msgmode=0)

    # We get the following messages but only use the NAV types
    #'NAV-RELPOSNED', 'NAV-PVT', 'GNRMC', 'GNVTG', 'GNGGA', 'GNGSA', 'GPGSV', 'GLGSV', 'GAGSV', 'GNGLL'
    rpn_read = False
    pvt_read = False

    while not all([rpn_read, pvt_read]):
        (raw_data, data) = ubr.read()
        try:
            identity = data.identity
        except AttributeError:
            continue

        if data.identity == 'NAV-RELPOSNED':
            log.debug("RPN message")
            rpn_read = True
            dataDictionary['version'] =      data.version
            dataDictionary['reserved1'] =    data.reserved1
            dataDictionary['refStationId'] = data.refStationID
            dataDictionary['relPosNed_iTOW'] = data.iTOW
            dataDictionary['relPosN'] =      data.relPosN
            dataDictionary['relPosE'] =      data.relPosE
            dataDictionary['relPosD'] =      data.relPosD
            dataDictionary['relPosLength'] = data.length
            dataDictionary['relPosHeading'] = data.relPosHeading
            dataDictionary['relPosHPN'] =    data.relPosHPN
            dataDictionary['relPosHPE'] =    data.relPosHPE
            dataDictionary['relPosHPD'] =    data.relPosHPD
            dataDictionary['relPosHPLength'] = data.relPosHPLength
            dataDictionary['accN'] =         data.accN
            dataDictionary['accE'] =         data.accE
            dataDictionary['accD'] =         data.accD
            dataDictionary['accLength'] =    data.accLength
            dataDictionary['accHeading'] =   data.accHeading
            dataDictionary['relPosNormalized'] = data.relPosNormalized
            dataDictionary['relPosHeadingValid'] = data.relPosHeadingValid
            dataDictionary['refObsMiss'] =   data.refObsMiss
            dataDictionary['refPosMiss'] =   data.refPosMiss
            dataDictionary['isMoving'] =     data.isMoving
            dataDictionary['carrSoln'] =     data.carrSoln
            dataDictionary['relPosValid'] =  data.relPosValid
            dataDictionary['diffSolN'] =     data.diffSoln
            dataDictionary['gnssFixOK'] =    data.gnssFixOK
        elif data.identity == 'NAV-PVT':
            log.debug("PVT message")
            pvt_read = True
            dataDictionary['iTOW'] = data.iTOW
            dataDictionary['year'] = data.year
            dataDictionary['month'] = data.month
            dataDictionary['day'] = data.day
            dataDictionary['hour'] = data.hour
            dataDictionary['min'] = data.min
            dataDictionary['sec'] = data.second
            dataDictionary['tAcc'] = data.tAcc
            dataDictionary['nano'] = data.nano
            dataDictionary['fixType'] = data.fixType
            dataDictionary['numSV'] = data.numSV
            dataDictionary['lon'] = data.lon
            dataDictionary['lat'] = data.lat
            dataDictionary['height'] = data.height
            dataDictionary['hMSL'] = data.hMSL
            dataDictionary['hAcc'] = data.hAcc
            dataDictionary['vAcc'] = data.vAcc
            dataDictionary['velN'] = data.velN
            dataDictionary['velE'] = data.velE
            dataDictionary['velD'] = data.velD
            dataDictionary['gSpeed'] = data.gSpeed
            dataDictionary['headMot'] = data.headMot
            dataDictionary['sAcc'] = data.sAcc
            dataDictionary['headAcc'] = data.headAcc
            dataDictionary['pDOP'] = data.pDOP
            dataDictionary['headVeh'] = data.headVeh
            dataDictionary['magDec'] = data.magDec
            dataDictionary['magAcc'] = data.magAcc
            dataDictionary['carrSoln'] = data.carrSoln
            dataDictionary['headVehValid'] = data.headVehValid
            dataDictionary['psmState'] = data.psmState
            dataDictionary['diffSolN'] = data.difSoln
            dataDictionary['gnssFixOK'] = data.gnssFixOk
            dataDictionary['confirmedTime'] = data.confirmedTime
            dataDictionary['confirmedDate'] = data.confirmedDate
            dataDictionary['confirmedAvai'] = data.confirmedAvai
            dataDictionary['validMag'] = data.validMag
            dataDictionary['fullyResolved'] = data.fullyResolved
            dataDictionary['validTime'] = data.validTime
            dataDictionary['validDate'] = data.validDate
            dataDictionary['lastCorrectionAge'] = data.lastCorrectionAge
            dataDictionary['invalidL1h'] = data.invalidLlh

        else:
            log.debug(f"Received {data.identity} - ignoring")

    if counter > 100:
        log.debug("After 100 passes, bytes in GPS buffer: {0}, Port open: {1}".format(serialReader.in_waiting, serialReader.isOpen()))
        counter = 0
    else:
        log.debug("Bytes in GPS buffer: {0}, Port open: {1}".format(serialReader.in_waiting, serialReader.isOpen()))

    try:
        self.current_gps_dict = dataDictionary
        self.notify_observers()

    except Exception as e:
        log.exception("Error on GPS string: {0}".format(dataDictionary))
        print(e)

    return dataDictionary


class GPSParser(object):
    """
    Class which contains a parse and checksum method for NMEA data.
    Will parse GPGGA and HCHDG NMEA sentences.
    """

    @staticmethod
    def checksum(sentence):
        """
        Check the GPS NMEA sentence and validates its checksum.

        :param sentence: NMEA sentence
        :type sentence: str

        :return: True if the sentences checksum is valid, False otherwise
        :rtype: bool
        """
        sentence = sentence.strip()
        match = re.search(r'^\$(.*\*.*)$', sentence)
        if match:
            try:
                sentence = match.group(1)
                nmeadata, cksum = re.split(r'\*', sentence)
                calc_cksum = 0
                for char in nmeadata:
                    calc_cksum ^= ord(char)
                return '0x'+cksum.lower() == hex(calc_cksum)
            except ValueError:
                return False
        return False

    @staticmethod
    def parse(gps_string):
        """
        Parse a GPS NMEA sentence, returns the output of the function which matches the string.

        :param gps_string: NMEA Sentence.
        :type gps_string: str

        :return: Function output or None
        """
        if GPSParser.checksum(gps_string):
            try:
                if gps_string.startswith('$GPGGA') or gps_string.startswith('$GNGGA') or gps_string.startswith('$GLGGA'):
                    return GPSParser.parse_gpgga(gps_string)
                elif gps_string.startswith('$GPRMC') or gps_string.startswith('$GNRMC') or gps_string.startswith('$GLRMC'):
                    return GPSParser.parse_gprmc(gps_string)
                elif gps_string.startswith('$GPVTG'):
                    return GPSParser.parse_gpvtg(gps_string)
                elif gps_string.startswith('$HCHDG'):
                    return GPSParser.parse_hchdg(gps_string)
                elif gps_string.startswith('$PMTK500'):
                    return GPSParser.parse_pmtk500(gps_string)
                elif gps_string.startswith('$GPGSA') or gps_string.startswith('$GNGSA') or gps_string.startswith('$GLGSA'):
                    return GPSParser.parse_gpgsa(gps_string)
            except:
                log.debug("Could not parse gps string:\n\t{0}".format(gps_string))
                pass

        return None

    @staticmethod
    def parse_gpgga(gpgga_string):
        """
        Parses a GPGGA sentence.

        :param gpgga_string: NMEA Sentence
        :type gpgga_string: str

        :return: Returns a dictionary with data extracted from the string.
        :rtype: dict
        """
        gps_parts = gpgga_string.split(',')[1:-1]
        # $GPGGA,113657.32,5021.9979,N,00407.9635,W,1,9,0.9,8.1,M,53.6,M,,*43
        #        0         1         2 3          4 5 6 7   8   9 10   11
        #                                                                ^12
        lat = int(gps_parts[1][0:2]) + (float(gps_parts[1][2:])/60.0)
        lon = int(gps_parts[3][0:3]) + (float(gps_parts[3][3:])/60.0)
        if gps_parts[2] == 'S':
            lat *= -1
        if gps_parts[4] == 'W':
            lon *= -1

        hour = int(gps_parts[0][0:2])
        mins = int(gps_parts[0][2:4])
        seconds = int(round(float(gps_parts[0][4:]), ndigits=0))

        #date = datetime.datetime.now()
        #date.replace(hour=hour, minute=mins, second=seconds)

        result = {
            'type': 'gpgga',
            'hour': hour,
            'min': mins,
            'seconds': seconds,
            #'date': date,
            'lat': lat,
            'lon': lon,
            'alt': float(gps_parts[8]),
            #'fix': int(gps_parts[5]),
            'satellite_number': int(gps_parts[6])
        }

        return result

    @staticmethod
    def parse_gprmc(gprmc_string):
        """
        Parses a GPRMC sentence.

        :param gprmc_string: NMEA Sentnce
        :type gprmc_string: str

        :return: Returns a dictionary with data extracted from the string.
        :rtype: dict
        """
        gps_parts = gprmc_string.split(',')[1:-1]
        # $GPRMC,113623.12,A,5021.9979,N,00407.9635,W,0.0,358.1,310315,2.2,W,A*3A
        #        0         1 2         3 4          5 6   7     8      9   10
        hour = int(gps_parts[0][0:2])
        mins = int(gps_parts[0][2:4])
        seconds = int(gps_parts[0][4:6])
        microseconds = int(gps_parts[0][7:])*1000

        day = int(gps_parts[8][0:2])
        month = int(gps_parts[8][2:4])
        year = int(gps_parts[8][4:6])
        if year < 1900:
            year += 2000

        date = datetime.datetime(year, month, day, hour, mins, seconds, microseconds)

        lat = int(gps_parts[2][0:2]) + (float(gps_parts[2][2:])/60.0)
        lon = int(gps_parts[4][0:3]) + (float(gps_parts[4][3:])/60.0)
        if gps_parts[3] == 'S':
            lat *= -1
        if gps_parts[5] == 'W':
            lon *= -1

        result = {
            'type': 'gprmc',
            'hour': hour,
            'min': mins,
            'seconds': seconds,
            'microseconds': microseconds,
            'day': day,
            'month': month,
            'year': year,
            'date': date,
            'lat': lat,
            'lon': lon,
            'speed': float(gps_parts[6]),
            'heading': float(gps_parts[7])
        }

        return result

    @staticmethod
    def parse_gpvtg(gpvtg_string):
        """
        Parses a GPVTG sentance.

        :param gpvtg_string: NMEA Sentance
        :type gpvtg_string: str

        :return: Returns a dictionary with data extracted from the string.
        :rtype: dict
        """
        gps_parts = gpvtg_string.split(',')[1:-1]
        # $GPVTG,232.7,T,234.9,M,1.3,N,2.4,K,A*2F
        #        0     1 2     3 4   5 6   7

        result = {
            'type': 'gpvtg',
            'heading': float(gps_parts[0]),
            'speed': float(gps_parts[4])
        }

        return result

    @staticmethod
    def parse_hchdg(hchdg_string):
        """
        Parses a HCHDG sentence.

        :param hchdg_string: NMEA Sentance
        :type hchdg_string: str

        :return: Returns a dictionary with data extracted from the string.
        :rtype: dict
        """
        gps_parts = hchdg_string.split(',')[1:-1]
        # $HCHDG,359.6,0.0,E,2.2,W*59
        #        0     1   2 3

        result = {
            'type': 'hchdg',
            'heading': float(gps_parts[0])
        }

        return result

    @staticmethod
    def parse_pmtk500(pmtk500_string):
        """
        Parses a PMTK500 sentence.

        :param pmtk500_string: NMEA Sentance
        :type pmtk500_string: str

        :return: Returns a dictionary with data extracted from the string.
        :rtype: dict
        """
        gps_parts = pmtk500_string.split(',')[1:-1]
        # $PMTK500,1000,0,0,0.0,0.0*1A
        #          0    1 2 3   4

        result = {
            'type': 'pmtk500',
            'update_rate': int(gps_parts[0])
        }

        return result

    @staticmethod
    def parse_gpgsa(gpgsa_string):
        """
        Parses a GPGSA sentence.

        :param gpgsa_string: NMEA Sentance
        :type gpgsa_string: str

        :return: Returns a dictionary with data extracted from the string.
        :rtype: dict
        """
        gps_parts = gpgsa_string.split(',')[1:-1]
        # $GPGSA,A,3,04,05,,09,12,,,24,,,,,2.5,1.3,2.1*39
        #        0 1 2                      3   4   5  6

        result = {
            'type': 'gpgsa',
            'fix': float(gps_parts[1])
        }

        return result


def readFromUblox(dataDictionary, timeToSleep, serialReader, LotOfData, self, counter):
    # Sleep so the program isn't spamming buffer with read requests
    time.sleep(timeToSleep)

    if serialReader.inWaiting() != 0:

        bitOfData = serialReader.read(serialReader.inWaiting())
        bitOfDataInAList = list(bitOfData)
        LotOfData =  LotOfData + bitOfDataInAList

        bitOfDataInAList = []
        listOfLines = []
        bitOfData = b''
        startIndices = [ i for i in range(len(LotOfData)-1) if (LotOfData[i] == 181 and LotOfData[i+1] == 98) ]
        if len(startIndices) >= 2:
            for currentStartIndex in range(len(startIndices)-1):
                # For all indexes that are start points, check if each is a full line.
                currentLine = LotOfData[startIndices[currentStartIndex]:startIndices[currentStartIndex+1]]
                currentHexLine, checkSumA, checkSumB = ValidateLine(currentLine)

                assert (len(currentHexLine)>1),"{} shorter then 2".format(currentHexLine)
                # If the line is complete and correct then append it to a list of lines.
                try:
                    if (checkSumA == currentHexLine[-2]) and (checkSumB == currentHexLine[-1]):
                        listOfLines.append(currentLine)
                    else:
                        # If the line is not complete, check if the "start index" was actually generated in the payload (middle of the message)
                        # If it was, check the following start indexes. If none are correct then discard the data.
                        for x in range(len(startIndices)-1):
                            currentLine = LotOfData[startIndices[currentStartIndex]:startIndices[x+1]]
                            currentHexLine, checkSumA, checkSumB = ValidateLine(currentLine)
                            if(checkSumA == currentHexLine[-2] and checkSumB == currentHexLine[-1]):
                                listOfLines.append(currentLine)
                                break
                except IndexError:
                    # get rid of poorly formatted package
                    log.info("Error parsing UBX GPS, clearing input buffer")
                    self.serial_port.reset_input_buffer()
                    LotOfData = []
                    startIndices = []
                    continue

            lineCount = 0
            for line in listOfLines:
                lineCount += 1

                payload = (line[6:-2])
                ID = line[3]
                CLASS = line[2]

                data = PayloadIdentifier(payload, ID, CLASS)

                if(len(data) == 27):
                    dataDictionary['version'] = data[0]
                    dataDictionary['reserved1'] = data[1]
                    dataDictionary['refStationId'] = data[2]
                    dataDictionary['relPosNed_iTOW'] = data[3]
                    dataDictionary['relPosN'] = data[4]
                    dataDictionary['relPosE'] = data[5]
                    dataDictionary['relPosD'] = data[6]
                    dataDictionary['relPosLength'] = data[7]

                    dataDictionary['relPosHeading'] = data[8]
                    dataDictionary['reserved2_1'] = data[9]
                    dataDictionary['reserved2_2'] = data[10]
                    dataDictionary['reserved2_3'] = data[11]
                    dataDictionary['reserved2_4'] = data[12]
                    dataDictionary['relPosHPN'] = data[13]
                    dataDictionary['relPosHPE'] = data[14]
                    dataDictionary['relPosHPD'] = data[15]
                    dataDictionary['relPosHPLength'] = data[16]
                    dataDictionary['accN'] = data[17]
                    dataDictionary['accE'] = data[18]
                    dataDictionary['accD'] = data[19]
                    dataDictionary['accLength'] = data[20]

                    dataDictionary['accHeading'] = data[21]

                    dataDictionary['reserved3_1'] = data[22]
                    dataDictionary['reserved3_2'] = data[23]
                    dataDictionary['reserved3_3'] = data[24]
                    dataDictionary['reserved3_4'] = data[25]
                    dataDictionary['relPosNed_flags'] = data[26]
                    dataDictionary['flag_relPosNormalized'] = data[26][21]
                    dataDictionary['flag_relPosHeadingValid'] = data[26][22]
                    dataDictionary['flag_refObsMiss'] = data[26][23]
                    dataDictionary['flag_refPosMiss'] = data[26][24]
                    dataDictionary['flag_isMoving'] = data[26][25]
                    dataDictionary['flag_carrSoln'] = data[26][26:28]
                    dataDictionary['flag_relPosValid'] = data[26][28]
                    dataDictionary['flag_diffSolN'] = data[26][29]
                    dataDictionary['flag_gnssFixOK'] = data[26][30]

                else:
                    dataDictionary['iTOW'] = data[0]
                    dataDictionary['year'] = data[1]
                    dataDictionary['month'] = data[2]
                    dataDictionary['day'] = data[3]
                    dataDictionary['hour'] = data[4]
                    dataDictionary['min'] = data[5]
                    dataDictionary['sec'] = data[6]
                    dataDictionary['valid'] = data[7]
                    dataDictionary['tAcc'] = data[8]
                    dataDictionary['nano'] = data[9]
                    dataDictionary['fixType'] = data[10]
                    dataDictionary['flags'] = data[11]
                    dataDictionary['flags2'] = data[12]
                    dataDictionary['numSV'] = data[13]
                    dataDictionary['lon'] = data[14]
                    dataDictionary['lat'] = data[15]
                    dataDictionary['height'] = data[16]
                    dataDictionary['hMSL'] = data[17]
                    dataDictionary['hAcc'] = data[18]
                    dataDictionary['vAcc'] = data[19]
                    dataDictionary['velN'] = data[20]
                    dataDictionary['velE'] = data[21]
                    dataDictionary['velD'] = data[22]
                    dataDictionary['gSpeed'] = data[23]
                    dataDictionary['headMot'] = data[24]
                    dataDictionary['sAcc'] = data[25]
                    dataDictionary['headAcc'] = data[26]
                    dataDictionary['pDOP'] = data[27]
                    dataDictionary['reserved1_1'] = data[28]
                    dataDictionary['reserved1_2'] = data[29]
                    dataDictionary['reserved1_3'] = data[30]
                    dataDictionary['reserved1_4'] = data[31]
                    dataDictionary['reserved1_5'] = data[32]
                    dataDictionary['reserved1_6'] = data[33]
                    dataDictionary['headVeh'] = data[34]
                    dataDictionary['magDec'] = data[35]
                    dataDictionary['magAcc'] = data[36]

                if counter > 100:
                    log.debug("After 100 passes, bytes in GPS buffer: {0}, Port open: {1}".format(serialReader.in_waiting, serialReader.isOpen()))
                    counter = 0
                else:
                    log.debug("Bytes in GPS buffer: {0}, Port open: {1}".format(serialReader.in_waiting, serialReader.isOpen()))

                # Set up memcache if needed
                # client = base.Client(('localhost', 11211))
                # Set key and value for memcache, with the line data as the value, and constantly update to be latest data.
                # client.set('GPS_UBLOX8', dataDictionary)

                # Check to see if the dictionary has all the data it needs from both messages before updating.
                if(len(dataDictionary) == 73):
                    try:
                        self.current_gps_dict = dataDictionary
                        self.notify_observers()

                    except Exception as e:
                        log.exception("Error on GPS string: {0}".format(dataDictionary))
                        print(e)

            # Any data that was not a complete line, and is in fact a part of the next line to be read in
            # is kept in the organised hex data list so the rest of the line can be appended.
            LotOfData = LotOfData[startIndices[len(startIndices)-1]:]

    return(dataDictionary, LotOfData)


def generateFletcherChecksum(byteArray):
    """
    Function to calculate the checksum from the received line of data.
    Returns the checksum generated from the line.
    """
    CK_A = 0
    CK_B = 0

    for I in range(len(byteArray)):
        CK_A = CK_A + byteArray[I]
        CK_A &= 0xFF
        CK_B = CK_B + CK_A
        CK_B &= 0xFF

    return (CK_A, CK_B)


def UnpackMessage(structFormat, payload):
    messageData = struct.unpack(structFormat, bytearray(payload))
    return (messageData)


def PayloadIdentifier(payload, ID, Class):
    """
    TODO: docstring
    """
    from thread_managers import ublox8Dictionary
    Class = str(hex(Class).lstrip("0x")).zfill(2)
    ID = str(hex(ID).lstrip("0x")).zfill(2)
    identifier = str(Class) + str(ID) #+ str(length)

    if identifier in ublox8Dictionary.ClassIDs.keys():
        if identifier == "0107":
            flag = payload[11]
            binaryFlag = "{0:b}".format(flag)
            binaryFlag = binaryFlag.zfill(8)
            valid = payload[7]
            binaryValid = "{0:b}".format(valid)
            binaryValid = binaryValid.zfill(8)
            flag2 = payload[12]
            binaryFlag2 = "{0:b}".format(flag2)
            binaryFlag2 = binaryFlag2.zfill(8)

            data = UnpackMessage(ublox8Dictionary.ClassIDs[identifier][0], payload)
            data = list(data)
            data[11] = binaryFlag
            data[12] = binaryFlag2
            data[7] = binaryValid
            return (data)
            # UnpackMessage(ClassIDs[identifier][0], payload)
        elif identifier == "013c":
            flags = payload[26]
            binaryFlags = "{0:b}".format(flags)
            binaryFlags = binaryFlags.zfill(31)
            data = UnpackMessage(ublox8Dictionary.ClassIDs[identifier][0], payload)
            data = list(data)
            relPosHeading = data[8]
            accHeading = data[18]
            relPosHeading = relPosHeading / 100000
            accHeading = accHeading / 100000

            if(relPosHeading < 0):
                relPosHeading = 360 + relPosHeading

            data[8] = relPosHeading
            data[26] = binaryFlags
            data[21] = accHeading
            #returnData = [relPosHeading, accHeading]
            return (data)
        else:
            return None


def ValidateLine(currentLine):
    loadsOfHexData = []
    # check if line is valid using checksum
    loadsOfHex = list(bytearray(currentLine).hex())
    # Organise the hex data into the correct pairs.
    for index in range(0, len(loadsOfHex), 2):
        val = loadsOfHex[index] + loadsOfHex[index+1]
        if len(val) == 2:
            loadsOfHexData.append(val)
    base16Data = [int(x, 16) for x in loadsOfHexData]
    currentByteLine = bytearray(base16Data)
    checkSumA, checkSumB = generateFletcherChecksum(currentByteLine[2:-2])
    return (currentByteLine, checkSumA, checkSumB)


class PYUBX2(object):
    """
    Main GPS manager when using the PYUBX2 protocol
    """
    def __init__(self):
        self.serial_ports = []
        self.stop_gps = False
        self.watchdog = None
        self.started = False
        self.threads = []

        # UBX-NAV-PVT message data
        self.iTOW = None
        self.year = None
        self.month = None
        self.day = None
        self.hour = None
        self.minute = None
        self.second = None
        self.tAcc = None
        self.nano = None
        self.fixType = 0
        self.satellite_number = 0
        self.lon = None
        self.lat = None
        self.height = None
        self.hMSL = None
        self.hAcc = None
        self.vAcc = None
        self.velN = None
        self.velE = None
        self.velD = None
        self.gspeed = None
        self.headMot = None
        self.sAcc = None
        self.headAcc = None
        self.pDOP = None
        self.headVeh = None
        self.magDec = None
        self.magAcc = None

        # flag data from PVT message
        self.flags_carrSoln = None
        self.flags_headVehValid = None
        self.flags_psmState = None
        self.flags_diffSolN = None
        self.flags_gnssFixOK = None

        self.flags2_confirmedTime = None
        self.flags2_confirmedDate = None
        self.flags2_confirmedAvai = None

        self.valid_validMag = None
        self.valid_fullyResolved = None
        self.valid_validTime = None
        self.valid_validDate = None

        # standadising data to nmea format
        self.alt = None
        self.datetime = None
        self.heading = None
        self.speed = None
        self.fix = 0

        # relposned message data
        self.version = None
        self.reserved1 = None
        self.refStationId = None
        self.relPosNed_iTOW = None
        self.relPosN = None
        self.relPosE = None
        self.relPosD = None
        self.relPosLength = None

        # Heading
        self.relPosHeading = None
        self.relPosHPN = None
        self.relPosHPE = None
        self.relPosHPD = None
        self.relPosHPLength = None
        self.accN = None
        self.accE = None
        self.accD = None
        self.accLength = None

        # Heading Accuracy
        self.accHeading = None

        # flags data for relposned message
        self.flag_relPosNormalized = None
        self.flag_relPosHeadingValid = None
        self.flag_refObsMiss = None
        self.flag_refPosMiss = None
        self.flag_isMoving = None
        self.flag_carrSoln = None
        self.flag_relPosValid = None
        self.flag_diffSolN = None
        self.flag_gnssFixOK = None

        # data for classes to manage threading + misc
        self.update_rate = 0
        self.gps_lock = threading.Lock()
        self.gps_observers = []
        self.watchdog_callbacks = []
        self.last_update = datetime.datetime.now()
        self.update_counter = 0

    def __del__(self):
        #self.disable_watchdog()
        self.stop()

    def add_serial_port(self, serial_port):
        """
        Add a serial port to the list of ports to read from.

        The serial port must be an instance of serial.Serial, and the open() method must have been called.

        :param serial_port: Serial object
        :type serial_port: serial.Serial
        """
        if not serial_port in self.serial_ports:
            self.serial_ports.append(serial_port)

    def remove_serial_port(self, serial_port):
        """
        Remove serial port from the list of ports to remove.

        This wont kill any threads reading serial ports. Run stop then remove then start again.
        :param serial_port: Serial object
        :type serial_port: serial.Serial
        """
        if serial_port in self.serial_ports:
            self.serial_ports.remove(serial_port)

    def start(self):
        """
        Starts serial reading threads.
        """
        if not self.started:
            self.started = True
            for port in self.serial_ports:

                new_thread = GPSSerialReader(port, self)
                new_thread.register_observer(self)
                self.threads.append(new_thread)

            for thread in self.threads:
                thread.start()

            log.info("Started PYUBX2 GPS manager")
        else:
            log.warn("PYUBX2 GPS manager already started")

    def stop(self):
        """
        Tells the serial threads to stop.
        """
        log.info("Stopping BYUBX2 GPS manager")
        self.stop_gps = True
        time.sleep(2)
        log.info(self.threads)
        for thread in self.threads:
            thread.join(0.1)
            # log.info("gps alive? = {0}".format(thread.is_alive()))
        self.threads = []
        self.started = False
        log.info("Stopped PYUBX2 GPS manager")

    def update(self, gps_dict):
        """
        Updates the gps info held by this class, a lock is used to prevent corruption.

        :param gps_dict: GPS Dictionary passed.
        :type gps_dict: dict
        """

        #self.gps_lock.acquire(True)
        if gps_dict is not None:
            self.old = False
            if self.watchdog is not None:
                self.watchdog.reset()

            # data for message UBX-NAV-PVT
            self.iTOW = gps_dict['iTOW']
            self.year = gps_dict['year']
            self.month = gps_dict['month']
            self.day = gps_dict['day']
            self.hour = gps_dict['hour']
            self.minute = gps_dict['min']
            self.second = gps_dict['sec']
            self.tAcc = gps_dict['tAcc']
            self.nano = gps_dict['nano']
            self.fixType = gps_dict['fixType']
            self.satellite_number = gps_dict['numSV']
            self.lon = gps_dict['lon']
            self.lat = gps_dict['lat']
            self.height = gps_dict['height']
            self.hMSL = gps_dict['hMSL']

            self.datetime = datetime.datetime(int(gps_dict['year']),int(gps_dict['month']),int(gps_dict['day']),int(gps_dict['hour']),int(gps_dict['min']),int(gps_dict['sec']),abs(int(gps_dict['nano'])))
            self.hAcc = gps_dict['hAcc']
            self.vAcc = gps_dict['vAcc']
            self.velN = gps_dict['velN']
            self.velE = gps_dict['velE']
            self.velD = gps_dict['velD']
            self.gSpeed = gps_dict['gSpeed']
            self.headMot = gps_dict['headMot']/100000.0
            self.sAcc = gps_dict['sAcc']
            self.headAcc = gps_dict['headAcc']/100000.0
            self.pDOP = gps_dict['pDOP']
            self.headVeh = gps_dict['headVeh']/100000.0
            self.magDec = gps_dict['magDec']
            self.magAcc = gps_dict['magAcc']

            # align the following fields with NMEA 0183
            self.heading = self.relPosHeading
            self.speed = self.gSpeed * 0.00194384
            self.fix = self.fixType
            self.alt = self.hMSL
            #self.flags = gps_dict['flags']
            #self.valid = gps_dict['valid']

            # Flag data from message PVT
            self.flags_carrSoln = gps_dict['carrSoln']
            self.flags_headVehValid = int(gps_dict['headVehValid'])
            self.flags_psmState = gps_dict['psmState']
            self.flags_diffSolN = int(gps_dict['diffSolN'])
            self.flags_gnssFixOK = int(gps_dict['gnssFixOK'])

            self.flags2_confirmedTime = gps_dict['confirmedTime']
            self.flags2_confirmedDate = gps_dict['confirmedDate']
            self.flags2_confirmedAvai = gps_dict['confirmedAvai']

            self.valid_validMag = int(gps_dict['validMag'])
            self.valid_fullyResolved = int(gps_dict['fullyResolved'])
            self.valid_validTime = int(gps_dict['validTime'])
            self.valid_validDate = int(gps_dict['validDate'])

            # relposned message data
            self.version = gps_dict['version']
            self.refStationId = gps_dict['refStationId']
            self.relPosNed_iTOW = gps_dict['relPosNed_iTOW']
            self.relPosN = gps_dict['relPosN']
            self.relPosE = gps_dict['relPosE']
            self.relPosD = gps_dict['relPosD']
            self.relPosLength = gps_dict['relPosLength']

            # Heading
            self.relPosHeading = gps_dict['relPosHeading']
            self.relPosHPN = gps_dict['relPosHPN']
            self.relPosHPE = gps_dict['relPosHPE']
            self.relPosHPD = gps_dict['relPosHPD']
            self.relPosHPLength = gps_dict['relPosHPLength']
            self.accN = gps_dict['accN']
            self.accE = gps_dict['accE']
            self.accD = gps_dict['accD']
            self.accLength = gps_dict['accLength']

            # Heading Accuracy
            self.accHeading = gps_dict['accHeading']

            # flags data for relposned message
            self.flag_relPosNormalized = gps_dict['relPosNormalized']
            self.flag_relPosHeadingValid = gps_dict['relPosHeadingValid']
            self.flag_refObsMiss = gps_dict['refObsMiss']
            self.flag_refPosMiss = gps_dict['refPosMiss']
            self.flag_isMoving = gps_dict['isMoving']
            self.flag_carrSoln = gps_dict['carrSoln']
            self.flag_relPosValid = gps_dict['relPosValid']
            self.flag_diffSolN = gps_dict['diffSolN']
            self.flag_gnssFixOK = gps_dict['gnssFixOK']

            self.last_update = datetime.datetime.now()
            self.update_counter += 1

            if self.update_counter % 10 == 0:
                log.debug("GPS update: PC time: {0}, GPS time: {1}".format(self.last_update.isoformat(), self.datetime.isoformat()))

        #self.gps_lock.release()

    def flushbuffer(self):
        self.serial_ports[0].reset_input_buffer()

    def reset_comports(self):
        """Reset the comports so that the data are fresh and the GPS sensors are in sync"""
        self.gps_lock.acquire(True)
        self.serial_ports[0].close()
        time.sleep(0.05)
        self.serial_ports[0].open()
        log.info("Reset PYUBX2 GPS port: {0}".format(datetime.datetime.now()))
        self.gps_lock.release()


class RTKUBX(object):
    """
    Main GPS manager when using the homebrew RTKUBX protocol
    """
    def __init__(self):
        self.serial_ports = []
        self.stop_gps = False
        self.watchdog = None
        self.started = False
        self.threads = []

        # UBX-NAV-PVT message data
        self.iTOW = None
        self.year = None
        self.month = None
        self.day = None
        self.hour = None
        self.minute = None
        self.second = None
        self.tAcc = None
        self.nano = None
        self.fixType = 0
        self.satellite_number = 0
        self.lon = None
        self.lat = None
        self.height = None
        self.hMSL = None
        self.hAcc = None
        self.vAcc = None
        self.velN = None
        self.velE = None
        self.velD = None
        self.gspeed = None
        self.headMot = None
        self.sAcc = None
        self.headAcc = None
        self.pDOP = None
        self.reserved1_1 = None
        self.reserved1_2 = None
        self.reserved1_3 = None
        self.reserved1_4 = None
        self.reserved1_5 = None
        self.reserved1_6 = None
        self.headVeh = None
        self.magDec = None
        self.magAcc = None

        # flag data from PVT message
        self.flags_carrSoln = None
        self.flags_headVehValid = None
        self.flags_psmState = None
        self.flags_diffSolN = None
        self.flags_gnssFixOK = None

        self.flags2_confirmedTime = None
        self.flags2_confirmedDate = None
        self.flags2_confirmedAvai = None

        self.valid_validMag = None
        self.valid_fullyResolved = None
        self.valid_validTime = None
        self.valid_validDate = None

        # standadising data to nmea format
        self.alt = None
        self.datetime = None
        self.heading = None
        self.speed = None
        self.fix = 0
        self.valid = None
        self.flags = None
        self.flags2 = None


        # relposned message data
        self.version = None
        self.reserved1 = None
        self.refStationId = None
        self.relPosNed_iTOW = None
        self.relPosN = None
        self.relPosE = None
        self.relPosD = None
        self.relPosLength = None

        # Heading
        self.relPosHeading = None
        self.reserved2_1 = None
        self.reserved2_2 = None
        self.reserved2_3 = None
        self.reserved2_4 = None
        self.relPosHPN = None
        self.relPosHPE = None
        self.relPosHPD = None
        self.relPosHPLength = None
        self.accN = None
        self.accE = None
        self.accD = None
        self.accLength = None

        # Heading Accuracy
        self.accHeading = None
        self.reserved3_1 = None
        self.reserved3_2 = None
        self.reserved3_3 = None
        self.reserved3_4 = None
        self.relPosNed_flags = None

        # flags data for relposned message
        self.flag_relPosNormalized = None
        self.flag_relPosHeadingValid = None
        self.flag_refObsMiss = None
        self.flag_refPosMiss = None
        self.flag_isMoving = None
        self.flag_carrSoln = None
        self.flag_relPosValid = None
        self.flag_diffSolN = None
        self.flag_gnssFixOK = None

        # data for classes to manage threading + misc
        self.update_rate = 0
        self.gps_lock = threading.Lock()
        self.gps_observers = []
        self.watchdog_callbacks = []
        self.last_update = datetime.datetime.now()
        self.update_counter = 0

    def __del__(self):
        #self.disable_watchdog()
        self.stop()

    def add_serial_port(self, serial_port):
        """
        Add a serial port to the list of ports to read from.

        The serial port must be an instance of serial.Serial, and the open() method must have been called.

        :param serial_port: Serial object
        :type serial_port: serial.Serial
        """
        if not serial_port in self.serial_ports:
            self.serial_ports.append(serial_port)

    def remove_serial_port(self, serial_port):
        """
        Remove serial port from the list of ports to remove.

        This wont kill any threads reading serial ports. Run stop then remove then start again.
        :param serial_port: Serial object
        :type serial_port: serial.Serial
        """
        if serial_port in self.serial_ports:
            self.serial_ports.remove(serial_port)

    def start(self):
        """
        Starts serial reading threads.
        """
        if not self.started:
            self.started = True
            for port in self.serial_ports:

                new_thread = GPSSerialReader(port, self)
                new_thread.register_observer(self)
                self.threads.append(new_thread)

            for thread in self.threads:
                thread.start()

            log.info("Started RTK GPS manager")
        else:
            log.warn("RTK GPS manager already started")

    def stop(self):
        """
        Tells the serial threads to stop.
        """
        log.info("Stopping RTK GPS manager")
        self.stop_gps = True
        time.sleep(2)
        log.info(self.threads)
        for thread in self.threads:
            thread.join(0.1)
            # log.info("gps alive? = {0}".format(thread.is_alive()))
        self.threads = []
        self.started = False
        log.info("Stopped RTK GPS manager")

    def update(self, gps_dict):
        """
        Updates the gps info held by this class, a lock is used to prevent corruption.

        :param gps_dict: GPS Dictionary passed.
        :type gps_dict: dict
        """

        #self.gps_lock.acquire(True)
        if gps_dict is not None:
            self.old = False
            if self.watchdog is not None:
                self.watchdog.reset()

            # data for message UBX-NAV-PVT
            self.iTOW = gps_dict['iTOW']
            self.year = gps_dict['year']
            self.month = gps_dict['month']
            self.day = gps_dict['day']
            self.hour = gps_dict['hour']
            self.minute = gps_dict['min']
            self.second = gps_dict['sec']
            self.tAcc = gps_dict['tAcc']
            self.nano = gps_dict['nano']
            self.fixType = gps_dict['fixType']
            self.satellite_number = gps_dict['numSV']
            self.lon = gps_dict['lon']/10000000.0
            self.lat = gps_dict['lat']/10000000.0
            self.height = gps_dict['height']
            self.hMSL = gps_dict['hMSL']

            self.datetime = datetime.datetime(int(gps_dict['year']),int(gps_dict['month']),int(gps_dict['day']),int(gps_dict['hour']),int(gps_dict['min']),int(gps_dict['sec']),abs(int(gps_dict['nano'])))
            self.hAcc = gps_dict['hAcc']
            self.vAcc = gps_dict['vAcc']
            self.velN = gps_dict['velN']
            self.velE = gps_dict['velE']
            self.velD = gps_dict['velD']
            self.gSpeed = gps_dict['gSpeed']
            self.headMot = gps_dict['headMot']/100000.0
            self.sAcc = gps_dict['sAcc']
            self.headAcc = gps_dict['headAcc']/100000.0
            self.pDOP = gps_dict['pDOP']
            self.reserved1_1 = gps_dict['reserved1_1']
            self.reserved1_2 = gps_dict['reserved1_2']
            self.reserved1_3 = gps_dict['reserved1_3']
            self.reserved1_4 = gps_dict['reserved1_4']
            self.reserved1_5 = gps_dict['reserved1_5']
            self.reserved1_6 = gps_dict['reserved1_6']
            self.headVeh = gps_dict['headVeh']/100000.0
            self.magDec = gps_dict['magDec']
            self.magAcc = gps_dict['magAcc']

            # align the following fields with NMEA 0183
            self.heading = self.relPosHeading
            self.speed = self.gSpeed * 0.00194384
            self.fix = self.fixType
            self.alt = self.hMSL
            self.flags = gps_dict['flags']
            self.valid = gps_dict['valid']

            # Flag data from message PVT
            self.flags_carrSoln = gps_dict['flags'][0:2]
            self.flags_headVehValid = int(gps_dict['flags'][2])
            self.flags_psmState = gps_dict['flags'][3:6]
            self.flags_diffSolN = int(gps_dict['flags'][6])
            self.flags_gnssFixOK = int(gps_dict['flags'][7])

            self.flags2_confirmedTime = int(gps_dict['flags2'][0])
            self.flags2_confirmedDate = int(gps_dict['flags2'][1])
            self.flags2_confirmedAvai = int(gps_dict['flags2'][2])

            self.valid_validMag = int(gps_dict['valid'][4])
            self.valid_fullyResolved = int(gps_dict['valid'][5])
            self.valid_validTime = int(gps_dict['valid'][6])
            self.valid_validDate = int(gps_dict['valid'][7])

            # relposned message data
            self.version = gps_dict['version']
            self.reserved1 = gps_dict['reserved1']
            self.refStationId = gps_dict['refStationId']
            self.relPosNed_iTOW = gps_dict['relPosNed_iTOW']
            self.relPosN = gps_dict['relPosN']
            self.relPosE = gps_dict['relPosE']
            self.relPosD = gps_dict['relPosD']
            self.relPosLength = gps_dict['relPosLength']

            # Heading
            self.relPosHeading = gps_dict['relPosHeading']

            self.reserved2_1 = gps_dict['reserved2_1']
            self.reserved2_2 = gps_dict['reserved2_2']
            self.reserved2_3 = gps_dict['reserved2_3']
            self.reserved2_4 = gps_dict['reserved2_4']
            self.relPosHPN = gps_dict['relPosHPN']
            self.relPosHPE = gps_dict['relPosHPE']
            self.relPosHPD = gps_dict['relPosHPD']
            self.relPosHPLength = gps_dict['relPosHPLength']
            self.accN = gps_dict['accN']
            self.accE = gps_dict['accE']
            self.accD = gps_dict['accD']
            self.accLength = gps_dict['accLength']

            # Heading Accuracy
            self.accHeading = gps_dict['accHeading']

            self.reserved3_1 = gps_dict['reserved3_1']
            self.reserved3_2 = gps_dict['reserved3_2']
            self.reserved3_3 = gps_dict['reserved3_3']
            self.reserved3_4 = gps_dict['reserved3_4']
            self.relPosNed_flags = gps_dict['relPosNed_flags']

            # flags data for relposned message
            self.flag_relPosNormalized = gps_dict['flag_relPosNormalized']
            self.flag_relPosHeadingValid = gps_dict['flag_relPosHeadingValid']
            self.flag_refObsMiss = gps_dict['flag_refObsMiss']
            self.flag_refPosMiss = gps_dict['flag_refPosMiss']
            self.flag_isMoving = gps_dict['flag_isMoving']
            self.flag_carrSoln = gps_dict['flag_carrSoln']
            self.flag_relPosValid = gps_dict['flag_relPosValid']
            self.flag_diffSolN = gps_dict['flag_diffSolN']
            self.flag_gnssFixOK = gps_dict['flag_gnssFixOK']

            self.last_update = datetime.datetime.now()
            self.update_counter += 1

            if self.update_counter % 10 == 0:
                log.debug("GPS update: PC time: {0}, GPS time: {1}".format(self.last_update.isoformat(), self.datetime.isoformat()))
            else:
                log.debug("GPS update: PC time: {0}, GPS time: {1}".format(self.last_update.isoformat(), self.datetime.isoformat()))

        #self.gps_lock.release()

    def flushbuffer(self):
        self.serial_ports[0].reset_input_buffer()

    def reset_comports(self):
        """Reset the comports so that the data are fresh and the GPS sensors are in sync"""
        self.gps_lock.acquire(True)
        self.serial_ports[0].close()
        time.sleep(0.05)
        self.serial_ports[0].open()
        log.info("Reset RTK GPS ports: {0}".format(datetime.datetime.now()))
        self.gps_lock.release()


class NMEA0183(object):
    """
    Main GPS manager when using the NMEA protocol
    """
    def __init__(self):
        self.serial_ports = []
        self.stop_gps = False
        self.watchdog = None
        self.started = False
        self.threads = []
        self.heading = None
        self.lat = None
        self.lon = None
        self.alt = None
        self.speed = None
        self.fix = 0
        self.datetime = None
        self.old = False
        self.proper_compass = False
        self.satellite_number = 0
        self.update_rate = 0
        self.gps_lock = threading.Lock()
        self.gps_observers = []
        self.watchdog_callbacks = []
        self.last_update = datetime.datetime.now()

    def __del__(self):
        #self.disable_watchdog()
        self.stop()

    def add_serial_port(self, serial_port):
        """
        Add a serial port to the list of ports to read from.

        The serial port must be an instance of serial.Serial, and the open() method must have been called.

        :param serial_port: Serial object
        :type serial_port: serial.Serial
        """
        if not serial_port in self.serial_ports:
            self.serial_ports.append(serial_port)

    def remove_serial_port(self, serial_port):
        """
        Remove serial port from the list of ports to remove.

        This wont kill any threads reading serial ports. Run stop then remove then start again.
        :param serial_port: Serial object
        :type serial_port: serial.Serial
        """
        if serial_port in self.serial_ports:
            self.serial_ports.remove(serial_port)

    def start(self):
        """
        Starts serial reading threads.
        """
        if not self.started:
            self.started = True
            for port in self.serial_ports:
                new_thread = GPSSerialReader(port, self)
                new_thread.register_observer(self)
                self.threads.append(new_thread)

            for thread in self.threads:
                thread.start()

            log.info("Started GPS managers")
        else:
            log.warn("GPS manager already started")

    def stop(self):
        """
        Tells the serial threads to stop.
        """
        log.info("Stopping GPS manager")
        self.stop_gps = True
        time.sleep(2)
        log.info(self.threads)
        for thread in self.threads:
            thread.join(0.1)
        self.threads = []
        self.started = False
        log.info("Stopped GPS manager")

    def update(self, gps_dict):
        """
        Updates the gps info held by this class, a lock is used to prevent corruption.

        :param gps_dict: GPS Dictionary passed.
        :type gps_dict: dict
        """
        self.gps_lock.acquire(True)
        if gps_dict is not None:
            self.old = False
            if self.watchdog is not None:
                self.watchdog.reset()
            if gps_dict['type'] == 'hchdg':
                self.proper_compass = True
                self.heading = gps_dict['heading']
            elif gps_dict['type'] == 'gpvtg':
                # Use track made good? for heading if no proper compass
                self.speed = gps_dict['speed']

                if not self.proper_compass:
                    self.heading = gps_dict['heading']
            elif gps_dict['type'] == 'gpgga':
                self.lat = gps_dict['lat']
                self.lon = gps_dict['lon']
                self.alt = gps_dict['alt']
                #self.fix = gps_dict['fix']
                self.satellite_number = gps_dict['satellite_number']
                #if self.datetime is not None: # Doesnt get day only time so update if we have proper day (GPRMC should set that eventually)
                #    self.datetime.replace(hour=gps_dict['hour'], minute=gps_dict['min'], second=gps_dict['seconds'])
                #else:
                #    self.datetime = gps_dict['date']
            elif gps_dict['type'] == 'gprmc':
                self.lat = gps_dict['lat']
                self.lon = gps_dict['lon']
                self.datetime = gps_dict['date']
                self.speed = gps_dict['speed']
                # Use track made good? for heading if no proper compass
                if not self.proper_compass:
                    self.heading = gps_dict['heading']
            elif gps_dict['type'] == 'pmtk500':
                self.update_rate = gps_dict['update_rate']
            elif gps_dict['type'] == 'gpgsa':
                self.fix = gps_dict['fix']
            #self.notify_observers()
            self.last_update = datetime.datetime.now()
        self.gps_lock.release()

    def flushbuffer(self):
        self.serial_ports[0].reset_input_buffer()

    def reset_comports(self):
        """Reset the comports so that the data is fresh and the GPS sensors are in sync"""
        self.gps_lock.acquire(True)
        self.serial_ports[0].close()
        time.sleep(0.05)
        self.serial_ports[0].open()
        log.info("Reset GPS ports: {0}".format(datetime.datetime.now()))
        self.gps_lock.release()

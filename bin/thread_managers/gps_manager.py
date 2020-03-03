
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

log = logging.getLogger()   # report to root logger

# GPGGA $GPGGA,113657.32,5021.9979,N,00407.9635,W,1,9,0.9,8.1,M,53.6,M,,*43
#  GPS Fix Data:
#    Time, Lat, Lon, Fix Quality, No. Satellites, HDOP, Altitude, HELIP, DGPS, DGPS Ref
# GPGSV
#  Satellites in view:
#    Total messages, Message number, No. Satellites, SV PRN, Elevation, Azimuth, SNR, 4-7, 4-7, 4-7
# GPRMC $GPRMC,113745.12,A,5021.9979,N,00407.9635,W,0.0,358.1,310315,2.2,W,A*3B
#  Minimum GPS Data:
#    Time, Valid, Lat, Lon, Speed, Course, Date, Variation
# GPVTG $GPVTG,232.7,T,234.9,M,1.3,N,2.4,K,A*2F
#  Track Made Good and Ground Speed
#    True Track, Magnetic Track, Ground Speed (knots), Ground Speed (Km/h)
# HCHDG $HCHDG,359.6,0.0,E,2.2,W*59
#  Compass Data:
#    Heading, deviation, variation
# PAMTR
# PAMTT
# WIMDA
# WIMWD
# WIMWV

class GPSParser(object):
    """
    Class which contains a parse and checksum method.

    Will parse GPGGA and HCHDG NMEA sentence.
    """
    @staticmethod
    def checksum(sentence):
        """
        Check the GPS NMEA sentence and validate its checksum.

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
        Parses a HCHDG sentance.

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
        Parses a GPGSA sentance.

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
    
    from thread_managers import ublox8Dictionary
    Class = str(hex(Class).lstrip("0x")).zfill(2)
    ID = str(hex(ID).lstrip("0x")).zfill(2)
    identifier = str(Class) + str(ID) #+ str(length)

    if identifier in ublox8Dictionary.ClassIDs.keys():
        if(identifier == "0107"):
            data = UnpackMessage(ublox8Dictionary.ClassIDs[identifier][0], payload)
            return (data)
            # UnpackMessage(ClassIDs[identifier][0], payload)
        else:
            pass #MAKE THE LOGGER to say this message hasn't been implemented yet.  
        
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

class GPSSerialReader(threading.Thread):
    """
    Thread to read from a serial port
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

        # Variables to manager a reader timer
        numberOfChecksToMake = 10
        timeToSleep = 1
        targetChecksPerLine = 1.3
        targetLinesPerCheck = 1/targetChecksPerLine   
        serialReader = self.serial_port
        LotOfData = []
        from pymemcache.client import base


        while not self.parent.stop_gps:
           # print("port {}".format(self.serial_port.inwaiting()))
           # print("Length of data in gps buffer: {}".format(len(self.serial_port.inwaiting())))
            
            if(protocol == "RTKUBX"):
                pass
            elif(protocol == "NMEA0183"):
                old_gps_time = self.parent.datetime
 
            if self.serial_port.inWaiting() > 1000:
                # if too much data in buffer, throw it away
                log.warning(">1kb in gps buffer on port {0}. Clearing input buffer.".format(self.serial_port.port))
                self.serial_port.reset_input_buffer()
                time.sleep(0.001)
                continue

            if(protocol == "NMEA0183"):
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
            elif(protocol == "RTKUBX"):
                try:
                    # Keep a record of number of lines read this pass, to calculate timer
                    lineCount = 0

                    for i in range(numberOfChecksToMake):
                        # Sleep so the program isn't spamming buffer with read requests
                        time.sleep(timeToSleep)

                        if serialReader.in_waiting != 0:
                            bitOfData = serialReader.read(serialReader.in_waiting)
                            bitOfDataInAList = list(bitOfData)           
                            LotOfData =  LotOfData + bitOfDataInAList
                            
                            bitOfDataInAList = []
                            listOfLines = []
                            bitOfData = b''
                            if len(LotOfData) > 600:
                                raise IOError("Port Failed")
                            
                            startIndices = [ i for i in range(len(LotOfData)-1) if (LotOfData[i] == 181 and LotOfData[i+1] == 98) ]
                            if(len(startIndices) >= 2):
                                for currentStartIndex in range(len(startIndices)-1):
                                    # For all indexes that are start points, check if each is a full line.
                                    currentLine = LotOfData[startIndices[currentStartIndex]:startIndices[currentStartIndex+1]]                               
                                    currentHexLine, checkSumA, checkSumB = ValidateLine(currentLine)

                                    assert (len(currentHexLine)>1),"{} shorter then 2".format(currentHexLine)
                                    # If the line is complete and correct then append it to a list of lines.
                                    if(checkSumA == currentHexLine[-2] and checkSumB == currentHexLine[-1]):
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
                                # For all the lines collected, get the payload out and send it to get sorted... eventually... it's a work in progress..    
                                for line in listOfLines:
                                    lineCount += 1
                                    payload = (line[6:-2]) 
                                    ID = line[3]                         
                                    CLASS = line[2]  
                                    data = PayloadIdentifier(payload, ID, CLASS)

                                    dataDictionary = {
                                        'iTOW' : data[0], 
                                        'year' : data[1], 
                                        'month' : data[2], 
                                        'day' : data[3], 
                                        'hour' : data[4], 
                                        'min' : data[5], 
                                        'sec' : data[6], 
                                        'valid' : data[7], 
                                        'tAcc' : data[8], 
                                        'nano' : data[9], 
                                        'fixType' : data[10], 
                                        'flags' : data[11], 
                                        'flags2' : data[12], 
                                        'numSV' : data[13], 
                                        'lon' : data[14], 
                                        'lat' : data[15], 
                                        'height' : data[16], 
                                        'hMSL' : data[17], 
                                        'hAcc' : data[18], 
                                        'vAcc' : data[19], 
                                        'velN' : data[20], 
                                        'velE' : data[21], 
                                        'velD' : data[22], 
                                        'gSpeed' : data[23], 
                                        'headMot' : data[24], 
                                        'sAcc' : data[25], 
                                        'headAcc' : data[26], 
                                        'pDOP' : data[27], 
                                        'reserved1_1' : data[28], 
                                        'reserved1_2' : data[29], 
                                        'reserved1_3' : data[30], 
                                        'reserved1_4' : data[31], 
                                        'reserved1_5' : data[32], 
                                        'reserved1_6' : data[33], 
                                        'headVeh' : data[34], 
                                        'magDec' : data[35], 
                                        'magAcc' :data[36]
                                    }
                                    # Set up memcache
                                    client = base.Client(('localhost', 11211))
                                    # Set key and value for memcache, with the line data as the value, and constantly update to be latest data.
                                    client.set('GPS_UBLOX8', dataDictionary)
                                    print("the dictionary {}".format(dataDictionary))
                                    try:
                                        self.current_gps_dict = dataDictionary
                                        print("the self dictionary {}".format(self.current_gps_dict))
                                        self.notify_observers()
                                        print("did the second one")
                                    except Exception:
                                        log.warning("Error on GPS string: {0}".format(dataDictionary))
                                
                                # Any data that was not a complete line, and is in fact a part of the next line to be read in
                                # is kept in the organised hex data list so the rest of the line can be appended. 
                                LotOfData = LotOfData[startIndices[len(startIndices)-1]:]           
                    
                    # Re-calculate the amount of time needed to sleep, with the goal of checking buffer at the speed of 1.3 times that of data being available
                    linesPerCheck = lineCount / numberOfChecksToMake
                    newTimeToSleep = timeToSleep * ( targetLinesPerCheck / linesPerCheck ) 
                    timeToSleep = newTimeToSleep
                    # Slowly increase the number of checks before re-adjusting the timer
                    if(numberOfChecksToMake < 100):
                        numberOfChecksToMake += 10
                except Exception as error:
                    print("Error when trying to read from ublox 8: {}".format(error))

####################################################################################################

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
        print("what is this {}".format(self.current_gps_dict))
        print("We have observers {}".format(self.observers))
        if self.current_gps_dict is not None:
            for observer in self.observers:
                observer.update(self.current_gps_dict)
                print("the update failed")

class RTKUBX(object):
    """
    Main GPS class which oversees the management and reading of GPS ports.
    """
    def __init__(self):
        self.serial_ports = []
        self.stop_gps = False
        self.watchdog = None
        self.started = False
        self.threads = []
        
        self.iTOW = None
        self.year = None
        self.month = None
        self.day = None
        self.hour = None
        self.minute = None
        self.second = None
        self.valid = None
        self.tAcc = None
        self.nano = None
        self.flags = None
        self.flags2 = None
        self.satellite_number = 0
        self.lon = None
        self.lat = None
        self.height = None
        self.hMSL = None

        self.alt = self.hMSL

        self.hAcc = None
        self.vAcc = None
        self.velN = None
        self.velE = None
        self.velD = None
        self.speed = None
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

            log.info("Started RTK GPS managers")
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
        self.gps_lock.acquire(True)
        if gps_dict is not None:
            self.old = False
            if self.watchdog is not None:
                self.watchdog.reset()
            

            self.iTOW = gps_dict['iTOW']
            self.year = gps_dict['year']
            self.month = gps_dict['month']
            self.day = gps_dict['day']
            self.hour = gps_dict['hour']
            self.minute = gps_dict['minute']
            self.second = gps_dict['second']
            self.valid = gps_dict['valid']
            self.tAcc = gps_dict['tAcc']
            self.nano = gps_dict['nano']
            self.flags = gps_dict['flags']
            self.flags2 = gps_dict['flags2']
            self.satellite_number = gps_dict['numSV']
            self.lon = gps_dict['lon']
            self.lat = gps_dict['lat']
            self.height = gps_dict['height']
            self.hMSL = gps_dict['hMSL']

            self.alt = self.hMSL

            self.hAcc = gps_dict['hAcc']
            self.vAcc = gps_dict['vAcc']
            self.velN = gps_dict['velN']
            self.velE = gps_dict['velE']
            self.velD = gps_dict['velD']
            self.speed = gps_dict['speed']
            self.headMot = gps_dict['headMot']
            self.sAcc = gps_dict['sAcc']
            self.headAcc = gps_dict['headAcc']
            self.pDOP = gps_dict['pDOP']
            self.reserved1_1 = gps_dict['reserved1_1']
            self.reserved1_2 = gps_dict['reserved1_2']
            self.reserved1_3 = gps_dict['reserved1_3']
            self.reserved1_4 = gps_dict['reserved1_4']
            self.reserved1_5 = gps_dict['reserved1_5']
            self.reserved1_6 = gps_dict['reserved1_6']
            self.headVeh = gps_dict['headVeh']
            self.magDec = gps_dict['magDec']
            self.magAcc = gps_dict['magAcc']
            
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
        log.info("Reset RTK GPS ports: {0}".format(datetime.datetime.now()))
        self.gps_lock.release()

class NMEA0183(object):
    """
    Main GPS class which oversees the management and reading of GPS ports.
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
            # log.info("gps alive? = {0}".format(thread.is_alive()))
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

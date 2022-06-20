#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TriOS G2 connector using modbus interface

"""

import time
import serial
import serial.tools.list_ports as list_ports
import libscrc as crc
import os
import sys
import codecs
import struct
#import threading
import datetime
import logging
#import inspect
#sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(inspect.getfile(inspect.currentframe())))))
#import matplotlib.pyplot as plt


def test(plot=False):
    """
    Reads config file to set up environment then
    - check sensor lan state (switch off to save power)
    - record one sample with the sensor
    - plot the spectrum (optional)
    """
    ports = list_ports.comports()
    for port, desc, hwid in ports:
        log.info(f"port: {port} | description: {desc} | hwid: {hwid}")

    mod = find_modbus(ports, autodetect_string="SER=FT5TZXD9")
    open_modbus(mod)

    log.info("checking for trios sensor")
    result = report_slave_id(mod)

    log.info("reading serial number")
    devserial = read_one_register(mod, 'device_serial_number')
    log.info(f"Serial number: {devserial}")

    log.info("checking lan state")
    lanstate = get_lan_state(mod)
    log.info(f"Lan state: {lanstate}")

    if lanstate:
        log.info("setting land state OFF")
        set_lan_state(mod, False)
        log.info("checking lan state (2)")
        lanstate = get_lan_state(mod)

    log.info("Sampling one spectrum")
    result = sample_one(mod)
    log.info(f"Integration time: {result.integration_time['value']} ({type(result.integration_time['value'])})")
    log.info(f"Inclination (pre/post): {result.pre_inclination['value']} ({type(result.pre_inclination['value'])})/ {result.post_inclination['value']} ({type(result.post_inclination['value'])})")
    log.info(f"Uncalibrated spectrum ({type(result.spectrum)}): {result.spectrum}")

    mod['serial'].close()

    if plot:
        plt.ion()
        plt.figure(1)
        plt.clf()
        plt.plot(result.spectrum)
        log.info("Close plot window to exit")
        try:
            plt.pause(0)
        except: pass  # suppress noise


class G2registers():
    """All G2 registers and how to read them"""
    def __init__(self):
        self.slave_address =          {'name': 'slave_address',           'start': 0,   'len': 1,  'datatype': '>H',  'timeout':0.15, 'value': None}
        self.measurement_timeout =    {'name': 'measurement_timeout',     'start': 1,   'len': 1,  'datatype': '>H',  'timeout':0.15, 'value': None}
        self.deep_sleep_timeout  =    {'name': 'deep_sleep_timeout',      'start': 2,   'len': 1,  'datatype': '>H',  'timeout':0.15, 'value': None}
        self.device_serial_number =   {'name': 'device_serial_number',    'start': 10,  'len': 5,  'datatype': 'str', 'timeout':0.15, 'value': None}
        self.firmware_version =       {'name': 'firmware_version',        'start': 15,  'len': 5,  'datatype': 'str', 'timeout':0.15, 'value': None}
        self.self_trigger_activated = {'name': 'self_trigger_activated',  'start': 102, 'len': 1,  'datatype': '>H',  'timeout':0.15, 'value': None}
        self.self_trigger_interval =  {'name': 'self_trigger_interval',   'start': 103, 'len': 2,  'datatype': '>L',  'timeout':0.15, 'value': None}
        self.integration_time_cfg =   {'name': 'integration_time_cfg',    'start': 107, 'len': 1,  'datatype': '>H',  'timeout':0.15, 'value': None}
        self.data_comment_1 =         {'name': 'data_comment_1'  ,        'start': 109, 'len': 32, 'datatype': 'str', 'timeout':0.15, 'value': None}
        self.data_comment_2 =         {'name': 'data_comment_2',          'start': 141, 'len': 32, 'datatype': 'str', 'timeout':0.15, 'value': None}
        self.data_comment_3 =         {'name': 'data_comment_3',          'start': 173, 'len': 32, 'datatype': 'str', 'timeout':0.15, 'value': None}
        self.data_comment_4 =         {'name': 'data_comment_4',          'start': 205, 'len': 32, 'datatype': 'str', 'timeout':0.15, 'value': None}
        self.system_date_and_time =   {'name': 'system_date_and_time',    'start': 237, 'len': 2,  'datatype': 'seconds',  'timeout':0.15, 'value': None}
        self.device_description =     {'name': 'device_description',      'start': 239, 'len': 32, 'datatype': 'str', 'timeout':0.15, 'value': None}
        self.lan_enable_state =       {'name': 'lan_enable_state',        'start': 273, 'len': 1,  'datatype': '>H',  'timeout':0.15, 'value': None}
        self.dark_pixel_start =       {'name': 'dark_pixel_start',        'start': 274, 'len': 1,  'datatype': '>H',  'timeout':0.15, 'value': None}
        self.dark_pixel_stop =        {'name': 'dark_pixel_stop',         'start': 275, 'len': 1,  'datatype': '>H',  'timeout':0.15, 'value': None}
        self.light_pixel_start =      {'name': 'light_pixel_start',       'start': 276, 'len': 1,  'datatype': '>H',  'timeout':0.15, 'value': None}
        self.light_pixel_stop =       {'name': 'light_pixel_stop',        'start': 277, 'len': 1,  'datatype': '>H',  'timeout':0.15, 'value': None}

        # on unused sensors, many of these registers are not yet initiated and won't be read correctly.
        # After the first measurement has been triggered this should work
        self.par =                    {'name': 'par',                     'start':1000, 'len': 2,  'datatype': '>f', 'timeout':0.15, 'value': None}
        self.spectrum_type =          {'name': 'spectrum_type',           'start':2000, 'len': 1,  'datatype': '>H', 'timeout':0.15, 'value': None}
        self.integration_time =       {'name': 'integration_time',        'start':2005, 'len': 1,  'datatype': '>H', 'timeout':0.15, 'value': None}
        self.temperature =            {'name': 'temperature',             'start':2007, 'len': 2,  'datatype': '>f', 'timeout':0.15, 'value': None}
        self.length =                 {'name': 'length',                  'start':2009, 'len': 1,  'datatype': '>H', 'timeout':0.15, 'value': None}
        self.pressure =               {'name': 'pressure',                'start':2011, 'len': 2,  'datatype': '>f', 'timeout':0.15, 'value': None}
        self.pre_inclination =        {'name': 'pre_inclination',         'start':2013, 'len': 2,  'datatype': '>f', 'timeout':0.15, 'value': None}
        self.post_inclination =       {'name': 'post_inclination',        'start':2015, 'len': 2,  'datatype': '>f', 'timeout':0.15, 'value': None}
        self.temp_inclination_sensor= {'name': 'temp_inclination_sensor', 'start':2030, 'len': 2,  'datatype': '>f', 'timeout':0.15, 'value': None}
        self.temp_pressure_sensor =   {'name': 'temp_pressure_sensor',    'start':2032, 'len': 2,  'datatype': '>f', 'timeout':0.15, 'value': None}
        self.pre_inclination_X =      {'name': 'pre_inclination_X',       'start':2034, 'len': 2,  'datatype': '>f', 'timeout':0.15, 'value': None}
        self.pre_inclination_Y =      {'name': 'pre_inclination_Y',       'start':2036, 'len': 2,  'datatype': '>f', 'timeout':0.15, 'value': None}
        self.pre_inclination_Z =      {'name': 'pre_inclination_Z',       'start':2038, 'len': 2,  'datatype': '>f', 'timeout':0.15, 'value': None}
        self.post_inclination_X =     {'name': 'post_inclination_X',      'start':2040, 'len': 2,  'datatype': '>f', 'timeout':0.15, 'value': None}
        self.post_inclination_Y =     {'name': 'post_inclination_Y',      'start':2042, 'len': 2,  'datatype': '>f', 'timeout':0.15, 'value': None}
        self.post_inclination_Z =     {'name': 'post_inclination_Z',      'start':2044, 'len': 2,  'datatype': '>f', 'timeout':0.15, 'value': None}
        self.pre_pressure =           {'name': 'pre_pressure',            'start':2046, 'len': 2,  'datatype': '>f', 'timeout':0.15, 'value': None}
        self.post_pressure =          {'name': 'post_pressure',           'start':2048, 'len': 2,  'datatype': '>f', 'timeout':0.15, 'value': None}
        self.dark_pixel_avg =         {'name': 'dark_pixel_avg',          'start':2050, 'len': 1,  'datatype': '>H', 'timeout':0.15, 'value': None}

        # RAMSES G2 has the 'Raw Light' method. The other registers (for calibrated wavelength and intensity) are commented out here because they are not tested.
        # Note that the data is stored in blocks of 125 coils, so two requests are needed to receive the complete length.
        self.raw_ordinate0 =          {'name': 'raw_ordinate0',           'start':3124, 'len': 125,  'datatype': '>125H', 'timeout':0.5, 'value': None}
        self.raw_ordinate1 =          {'name': 'raw_ordinate1',           'start':3249, 'len': 125,  'datatype': '>125H', 'timeout':0.5, 'value': None}
        #self.abscissa =              {'name': 'abscissa',                'start':2100, 'len': 125,  'datatype': '250e', 'timeout':0.3, 'value': None}
        #self.ordinate =              {'name': 'ordinate',                'start':2612, 'len': 125,  'datatype': '250e', 'timeout':0.3, 'value': None}


def sample_one(mod):
    """Trigger a measurement, then monitor sensor idle state and read and return (meta)data when ready"""
    meastimer = read_one_register(mod, register_name='measurement_timeout')
    if meastimer > 0:
        log.info("Sensor busy, try again")
        return None

    result = trigger_measurement(mod)

    timeout = 20
    t0 = time.perf_counter()
    meastimer = 200
    while (meastimer > 0) and ((time.perf_counter() - t0) < timeout):
        log.debug("Waiting for data..")
        time.sleep(0.1)
        meastimer = read_one_register(mod, register_name='measurement_timeout')
        if meastimer is None:
            meastimer = 0.1
            log.info("No data received while polling for measurement_timeout register")

    if meastimer > 0:
        log.warning("Sensor timed out")
        return None

    # data should now be available
    result = read_last_meas(mod)
    log.debug(result)
    return result


def set_lan_state(mod, state=False):
    """Enable or Disable the LAN interface. Saved across restarts. After enabling the device should be power cycled."""
    lanreg = G2registers().lan_enable_state
    response = write_single_command(mod['serial'], 1, 6, lanreg['start'], {True:65535, False:0}[state], timeout=1.0)
    log.debug(crc_check_incoming(response))


def trigger_measurement(mod):
    """Write register 0x06 with value 0x0400 (1024) to trigger a single measurement"""
    response = write_single_command(mod['serial'], 1, 6, 1, 1024, timeout=1)
    log.debug(response)


def get_lan_state(mod):
    """Read the state of the LAN interface."""
    g2 = G2registers()
    response = read_command(mod['serial'], 1, 3, g2.lan_enable_state['start'], g2.lan_enable_state['len'], timeout=g2.lan_enable_state['timeout'])
    datatype = g2.lan_enable_state['datatype']
    try:
        crc_check_incoming(response)
        lanstate = unpack_response(response, datatype)
        if lanstate == 65535:
            lanstate = True
        elif lanstate == 0:
            lanstate = False
        else:
            lanstate = None
        log.debug(f"LAN interface state: {lanstate}")
    except CrcError as err:
        log.exception(err)
        log.warning(f"LAN interface state - Checksum failed: {response}")

    return lanstate


def read_last_meas(mod):
    """
    Populate a dictionary with all instrument data from all trios G2 registers. The length attribute can then be used to read spectral data.
    """
    g2 = G2registers()
    for g2var in [g2.integration_time,
                  g2.system_date_and_time,
                  g2.pre_inclination,
                  g2.post_inclination,
                  g2.temp_inclination_sensor,
                  g2.raw_ordinate0, g2.raw_ordinate1]:

        response = read_command(mod['serial'], 1, 3, g2var['start'], g2var['len'], timeout=g2var['timeout'])
        datatype = g2var['datatype']
        try:
            crc_check_incoming(response)
            g2var['value'] = unpack_response(response, datatype)
            log.debug(f"{g2var['name']}: {g2var['value']}")
        except CrcError as err:
            log.exception(err)
            log.warning(f"{g2var['name']} Checksum failed: {response}")

    try:
        g2.spectrum = list(g2.raw_ordinate0['value'] + g2.raw_ordinate1['value'])
    except:
        log.warning(f"Failed to construct spectrum")

    return g2


def write_single_command(mod_serial, slave_id, function_code, register_address, value, timeout=0.2):
    """
    Write a command using function 0x06 (6, single coil) or 0x10 (11, multiple coils)

    The general structure of a single modbus command is
    Slave address 8 bits
    Function code 8 bits
    --03h (3) read from holding register
    --06h (6) write to a holding register - only used on address 1, to trigger a single light measurement. Write value 0x0400.
    --10h (16) write multiple registers
    --11h (17) write special register, should return sensor information
    Data          nx8 bits
    Error check   16 bits
    --error checks use CRC-16 method
    The response code follows the slave_id, function code, data length, data, checksum pattern
    """

    id = hex(slave_id)[2:].zfill(2)
    fun_code = hex(function_code)[2:].zfill(2)
    reg_address = hex(register_address)[2:].zfill(4)
    value = hex(value)[2:].zfill(4)

    initial_command = "".join([id, fun_code, reg_address, value])
    # update crc16
    crc16_modbus = hex(int(crc.modbus(codecs.decode(initial_command, 'hex'))))[2:].zfill(4)
    crc16_check = ''.join([crc16_modbus[2:4], crc16_modbus[0:2]])

    command = "".join([id, fun_code, reg_address, value, crc16_check])

    # Send the command to the controller
    mod_serial.flushInput()
    mod_serial.flushOutput()
    mod_serial.write(codecs.decode(command, 'hex'))

    # Read the response
    time.sleep(timeout)
    a = mod_serial.in_waiting
    # read response of location
    response = mod_serial.read(size=a)

    return response


def read_one_register(mod, register_name='system_date_and_time'):
    """perform request and read operation by register name"""

    g2 = G2registers()
    reg = g2.__dict__[register_name]
    response = read_command(mod['serial'], 1, 3, reg['start'], reg['len'], timeout=reg['timeout'])

    if response == b'':  # nothing received, try once more.
        log.debug("No response, trying again.. ")
        response = read_command(mod['serial'], 1, 3, reg['start'], reg['len'], timeout=reg['timeout'])

    datatype = reg['datatype']
    try:
        crc_check_incoming(response)
    except CrcError as err:
        log.warning(f"Failed to read register {register_name}: {response}")
        return None

    result = unpack_response(response, datatype)

    return result


def read_all_system_registers(mod):
    """
    Populate a dictionary with all instrument data from all trios G2 registers. The length attribute can then be used to read spectral data.
    """
    g2 = G2registers()
    for g2var in [g2.slave_address,
                  g2.measurement_timeout,
                  g2.deep_sleep_timeout,
                  g2.device_serial_number,
                  g2.firmware_version,
                  g2.self_trigger_activated,
                  g2.self_trigger_interval,
                  g2.integration_time_cfg,
                  g2.data_comment_1,
                  g2.data_comment_2,
                  g2.data_comment_3,
                  g2.data_comment_4,
                  g2.system_date_and_time,
                  g2.device_description,
                  g2.lan_enable_state,
                  g2.dark_pixel_start,
                  g2.dark_pixel_stop,
                  g2.light_pixel_start,
                  g2.light_pixel_stop,
                  # on new sensors, many of these registers are not yet initiated and won't be read correctly.
                  # After the first measurement has been triggered this should work
                  g2.par,
                  g2.spectrum_type,
                  g2.integration_time,
                  g2.temperature,
                  g2.length,
                  g2.pressure,
                  g2.pre_inclination,
                  g2.post_inclination,
                  g2.temp_inclination_sensor,
                  g2.temp_pressure_sensor,
                  g2.pre_inclination_X,
                  g2.pre_inclination_Y,
                  g2.pre_inclination_Z,
                  g2.post_inclination_X,
                  g2.post_inclination_Y,
                  g2.post_inclination_Z,
                  g2.pre_pressure,
                  g2.post_pressure,
                  g2.dark_pixel_avg]:

        response = read_command(mod['serial'], 1, 3, g2var['start'], g2var['len'], timeout=g2var['timeout'])
        datatype = g2var['datatype']
        try:
            crc_check_incoming(response)
            g2var['value'] = unpack_response(response, datatype)
            log.info(f"{g2var['name']}: {g2var['value']}")
        except CrcError as err:
            log.exception(err)
            log.warning(f"{g2var['name']} Checksum failed: {response}")

    return g2


def parse_data_types(datablock, datatype):
    """deal with different data types"""
    data_hex = codecs.encode(datablock, 'hex')
    try:
        if datatype == 'str':
            data = datablock.decode('ascii')
        elif datatype == 'seconds':
            data = struct.unpack('>L', datablock)[0]
            # convert system date/time to datetime
            data = datetime.datetime(1970,1,1,0,0,0) + datetime.timedelta(seconds=data)
        else:
            data = struct.unpack(datatype, datablock)
            if len(data) == 1:
                data = data[0]
    except:
        log.warning(f"Could not parse {datablock}, {data_hex}, {len(datablock)} as {datatype}")
        data = None
        pass

    log.debug(f"data hex/int: {data_hex} / {data}")
    return data


def unpack_response(response, datatype='int', ):
    """unpack the hex response"""
    slave_id = int(response[0])  # 1 register
    function_code = int(response[1])  # 1 register
    data_length = int(response[2])  # 1 register
    datablock = response[3: 3+data_length]  # n registers
    #datablock = response[3: -2]  # n registers
    log.debug(f"data block length={data_length}, value={datablock}")
    data = parse_data_types(datablock, datatype)

    return data


def crc_check_incoming(response):
    """crc check on incoming packet"""
    crc_message = response[0:-2]

    crc_hex = response[-2:].hex() # string representation of bytes object code in hex

    crc_value = codecs.encode(response[0:-2], 'hex')
    crc16_modbus = hex(int(crc.modbus(codecs.decode(crc_value, 'hex'))))[2:].zfill(4)
    crc16_check = ''.join([crc16_modbus[2:4], crc16_modbus[0:2]])

    check_value = crc_hex == crc16_check
    log.debug(f"CRC check: {check_value}")
    log.debug(f"{crc_hex} {type(crc_hex)}")

    if not check_value:
        raise CrcError("Response failed checksum")
    else:
        return

class CrcError(Exception):
    pass


def report_slave_id(mod):
    """
    Special function reporting back sensor informationin ascii coding: sensor name, serial number and firmware version.
    """
    slave_id = 1
    function_code = 17
    register_address = 0
    no_of_registers = 0
    id = hex(slave_id)[2:].zfill(2)
    fun_code = hex(function_code)[2:].zfill(2)
    reg_address = hex(register_address)[2:].zfill(4)
    n_regs = hex(no_of_registers)[2:].zfill(4)

    #initial_command = "".join([id, fun_code, reg_address, n_regs])
    initial_command = "".join([id, fun_code, reg_address, n_regs])

    #update crc16
    crc16_modbus = hex(int(crc.modbus(codecs.decode(initial_command, 'hex'))))[2:].zfill(4)
    crc16_check = ''.join([crc16_modbus[2:4], crc16_modbus[0:2]])

    #command = "".join([id, fun_code, reg_address, n_regs, crc16_check])
    command = "".join([id, fun_code, reg_address, n_regs, crc16_check])

    # Send the command to the controller
    mod['serial'].flushInput()
    mod['serial'].flushOutput()
    mod['serial'].write(codecs.decode(command, 'hex'))
    # Read the response
    time.sleep(0.5)
    a = mod['serial'].in_waiting
    # read response of location
    response = mod['serial'].read(size=a)
    try:
        make = response[3:-2].split(b'\x00')[0].decode('ascii')
        model = response[3:-2].split(b'\x00')[1].decode('ascii')
        serialn = response[3:-2].split(b'\x00')[2].decode('ascii')
        version = response[3:-2].split(b'\x00')[3].decode('ascii')
        log.info(f"{mod['serial'].port}: {make} | {model} | {serialn} | {version}")
        return serialn
    except:
        log.info(f"No TriOS G2 response on {mod['serial']}")
        return None


def init_logger():
    """Initialises the root logger for the program

    :param conf_log_dict: dictionary containing the logger config information
    :type conf_log_dict: dictionary
    :return: log
    :rtype: logger
    """
    myFormat = '%(asctime)s | %(name)s | %(levelname)s | %(message)s'
    formatter = logging.Formatter(myFormat)
    console_log_level = 'INFO'
    logging.basicConfig(level=console_log_level, format=myFormat, stream=sys.stdout)
    log = logging.getLogger()
    return log


def find_modbus(ports, autodetect_string=None, port_default=None):
    """Connect a single sensor via modbus. For testing purposes, not used in So-Rad scope"""
    mod = {'port': None, 'serial': None}

    match = False
    if autodetect_string is not None:
        for port, desc, hwid in sorted(ports):
            log.info("port info: {0} {1} {2}".format(port, desc, hwid))
            if autodetect_string in hwid:
                mod['port'] = port
            elif autodetect_string in desc:
                mod['port'] = port
        if mod['port'] is None:
            log.warning(f"Radiometer identifier {autodetect_string} not found on any port")

    elif port_default is not None:
        log.info(f"Use port default: {port_default}")
        mod['port'] = port_default

    else:
        log.error("No suitable ports configured")

    # Return the object containing serial ports found
    return mod


def open_modbus(mod, baud=9600, db=8, sb=1, parity=serial.PARITY_NONE):
    """Initiate modbus interface given a dictionary with port info"""
    # Create a serial object for the motor port
    if mod['port'] is not None:
        try:
            mod['serial'] = serial.Serial(port=mod['port'],
                                      baudrate=baud,
                                      timeout=1.0, bytesize=db, parity=parity,
                                      stopbits=sb, xonxoff=0)
            mod['serial'].reset_input_buffer()
            mod['serial'].reset_output_buffer()
        except OSError as ose:
             log.error(mod)
             log.exception(ose)
        finally:
             return None
    else:
        raise serial.SerialException('Modbus port not specified')


def close_modbus(mod):
    """check sensor is idle, then close"""
    mod['port'].close()


def read_command(mod_serial, slave_id, function_code, register_address, no_of_registers, timeout=0.2):
    """
    Read multiple registers
    e.g. read temperature of driver and motor = read_command(1, 3, 248, 4)
    """
    id = hex(slave_id)[2:].zfill(2)
    fun_code = hex(function_code)[2:].zfill(2)
    reg_address = hex(register_address)[2:].zfill(4)
    n_regs = hex(no_of_registers)[2:].zfill(4)

    initial_command = "".join([id, fun_code, reg_address, n_regs])
    # update crc16
    crc16_modbus = hex(int(crc.modbus(codecs.decode(initial_command, 'hex'))))[2:].zfill(4)
    crc16_check = ''.join([crc16_modbus[2:4], crc16_modbus[0:2]])

    command = "".join([id, fun_code, reg_address, n_regs, crc16_check])
    # Send the command to the controller
    mod_serial.flushInput()
    mod_serial.flushOutput()
    mod_serial.write(codecs.decode(command, 'hex'))
    # Read the response
    time.sleep(timeout)
    a = mod_serial.in_waiting
    # read response of location
    response = mod_serial.read(size=a)
    return response


def calc_crc16(inputcommand):
    """
    Calculates the CRC16 error check for the command provided as an argument

    :param inputcommand: Motor controller command string without any error checking bytes
    :type inputcommand: string

    :returns: The CRC16 bytes to append to the end of the command string
    :rtype: str
    """
    # Uses the libscrc.modbus function to calculate the CRC16 string for input command
    crc16_modbus = hex(int(crc.modbus(codecs.decode(inputcommand, 'hex'))))[2:].zfill(4)
    # Strips the hex string of the 0x and reverses the pair order
    converted_crc16_modbus = ''.join([crc16_modbus[2:4], crc16_modbus[0:2]])

    return converted_crc16_modbus


if __name__ == '__main__':
    # start logging here
    log = init_logger()
    test(plot=True)
else:
    log = logging.getLogger('pt2')

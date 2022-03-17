#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TriOS G2 connector class

The general structure of a single modbus command is

Slave address 8 bits
Function code 8 bits
--03h (3) read from holding register
--06h (6) write to a holding register - only used on address 1, to trigger a single light measurement. Write value 0x0400.
--10h (16) write multiple registers
Data          nx8 bits
Error check   16 bits
--error checks are based on the CRC-16 method


    Read multiple registers: 0x03
    Read the serial number and firmware version, configuration and calibration data, and of course measurement data

    0 - modbus slave address returns uint16
    1 - measurement timeout returns uint16
    2 - deep sleep timeout return uint16
    10 - device serial number returns char10
"

The response code follows the slave_id, function code, data length, data, checksum pattern
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
#import sqlite3
#import traceback
import logging
import inspect
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(inspect.getfile(inspect.currentframe())))))
#import functions.azimuth_functions as azi_func
#import functions.gps_functions as gps_func

def run():
    """ main program loop.
    Reads config file to set up environment then starts various threads to monitor inputs.
    Monitors for a keyboard interrupt to provide a clean exit where possible.
    """
    ports = list_ports.comports()
    for port, desc, hwid in ports:
        log.info(f"port: {port} | description: {desc} | hwid: {hwid}")

    mod = connect_modbus(ports, port_autodetect_string="USB-RS485 Cable", hwid_autodetect_string='SER=FT5TZXD9')
    # result = report_slave_id(mod)  # does not work yet
    # result = test_for_triosg2(mod)
    #result = trigger_measurement(mod)
    #log.info(result)
    #time.sleep(12)

    read_all_system_registers(mod)


def read_all_system_registers(mod):
    """
    Populate a dictionary with all instrument data from all trios G2 registers. The length attribute can then be used to read spectral data.
    """
    system = {
              'slave_address':          {'start': 0,   'len': 1,  'datatype': 'int',  'value': None},
              'measurement_timeout':    {'start': 1,   'len': 1,  'datatype': 'int',  'value': None},
              'deep_sleep_timeout':     {'start': 2,   'len': 1,  'datatype': 'int',  'value': None},
              'device_serial_number':   {'start': 10,  'len': 5,  'datatype': 'str',  'value': None},
              'firmware_version':       {'start': 15,  'len': 5,  'datatype': 'str',  'value': None},
              'self-trigger_activated': {'start': 102, 'len': 1,  'datatype': 'bool', 'value': None},
              'self-trigger_interval':  {'start': 103, 'len': 2,  'datatype': 'int',  'value': None},
              'integration_time':       {'start': 107, 'len': 1,  'datatype': 'int',  'value': None},
              'data_comment_1':         {'start': 109, 'len': 32, 'datatype': 'str',  'value': None},
              'data_comment_2':         {'start': 141, 'len': 32, 'datatype': 'str',  'value': None},
              'data_comment_3':         {'start': 173, 'len': 32, 'datatype': 'str',  'value': None},
              'data_comment_4':         {'start': 205, 'len': 32, 'datatype': 'str',  'value': None},
              'system_date_and_time':   {'start': 237, 'len': 2,  'datatype': 'int',  'value': None},
              'device_description':     {'start': 239, 'len': 32, 'datatype': 'str',  'value': None},
              'lan_enable_state':       {'start': 273, 'len': 1,  'datatype': 'int',  'value': None},
              'dark_pixel_start':       {'start': 274, 'len': 1,  'datatype': 'int',  'value': None},
              'dark_pixel_stop':        {'start': 275, 'len': 1,  'datatype': 'int',  'value': None},
              'light_pixel_start':      {'start': 276, 'len': 1,  'datatype': 'int',  'value': None},
              'light_pixel_stop':       {'start': 277, 'len': 1,  'datatype': 'int',  'value': None}
             }

    # on new sensors, many of these registers are not yet initiated and won't be read correctly. 
    # After the first measurement has been triggered this should work

    meas =   {
              'par':                    {'start':1000, 'len': 2,  'datatype': 'float', 'value': None},
              'spectrum_type':          {'start':2000, 'len': 1,  'datatype': 'int',   'value': None},
              'integration_time':       {'start':2005, 'len': 1,  'datatype': 'int',   'value': None},
              'temperature':            {'start':2007, 'len': 2,  'datatype': 'float', 'value': None},
              'length':                 {'start':2009, 'len': 1,  'datatype': 'int',   'value': None},
              'pressure':               {'start':2011, 'len': 2,  'datatype': 'float', 'value': None},
              'pre_inclination':        {'start':2013, 'len': 2,  'datatype': 'float', 'value': None},
              'post_inclination':       {'start':2015, 'len': 2,  'datatype': 'float', 'value': None},
              'temp_inclination_sensor':{'start':2030, 'len': 2,  'datatype': 'float', 'value': None},
              'temp_pressure_sensor':   {'start':2032, 'len': 2,  'datatype': 'float', 'value': None},
              'pre_inclination_X':      {'start':2034, 'len': 2,  'datatype': 'float', 'value': None},
              'pre_inclination_Y':      {'start':2036, 'len': 2,  'datatype': 'float', 'value': None},
              'pre_inclination_Z':      {'start':2038, 'len': 2,  'datatype': 'float', 'value': None},
              'post_inclination_X':     {'start':2040, 'len': 2,  'datatype': 'float', 'value': None},
              'post_inclination_Y':     {'start':2042, 'len': 2,  'datatype': 'float', 'value': None},
              'post_inclination_Z':     {'start':2044, 'len': 2,  'datatype': 'float', 'value': None},
              'pre_pressure':           {'start':2046, 'len': 2,  'datatype': 'float', 'value': None},
              'post_pressure':          {'start':2048, 'len': 2,  'datatype': 'float', 'value': None},
              'dark_pixel_avg':         {'start':2050, 'len': 1,  'datatype': 'int',   'value': None}
             }

    spec =   {
              'abscissa':               {'start':2100, 'len': 2,  'datatype': 'float', 'value': None},  # x length from meas
              'ordinate':               {'start':2612, 'len': 2,  'datatype': 'float', 'value': None},  # x length from meas
              'raw_ordinate':           {'start':3124, 'len': 1,  'datatype': 'int',   'value': None}   # x length from meas
             }

    # read system registers
    #for key, value in system.items():
    #    start =  system[key]['start']
    #    length = system[key]['len']
    #    datatype = system[key]['datatype']
    #    response = read_command(mod['serial'], 1, 3, start, length, timeout=0.15)
    #    try:
    #        crc_check_incoming(response)
    #        system[key]['value'] = unpack_response(response, datatype)
    #        log.info(f"{key}: {system[key]['value']}")
    #    except CrcError as err:
    #        log.exception(err)
    #        log.warning(f"{key}: Failed to read")


    # convert system date/time to datetime
    #systime = system['system_date_and_time']['value']  # The date and time in seconds since 1970/01/01.
    #system['system_date_and_time']['value'] = datetime.datetime(1970,1,1,0,0,0) + datetime.timedelta(seconds=systime)
    #log.info(f"system_date_and_time: {system['system_date_and_time']['value']}")

    # read 'last-measurement' registers
    for key, value in meas.items():
        start =  meas[key]['start']
        length = meas[key]['len']
        datatype = meas[key]['datatype']
        response = read_command(mod['serial'], 1, 3, start, length, timeout=0.2)
        try:
            crc_check_incoming(response)
            meas[key]['value'] = unpack_response(response, datatype)
            log.info(f"{key}: {meas[key]['value']}")
        except CrcError as err:
            log.exception(err)
            log.warning(f"{key}: Failed to read")

    # read meas['length'] + spec registers

    start, length, datatype = meas['length']['start'], meas['length']['len'], meas['length']['datatype']
    response = read_command(mod['serial'], 1, 3, start, length, timeout=0.2)
    try:
        crc_check_incoming(response)
        arraylen = unpack_response(response, datatype)
    except CrcError as err:
        log.exception(err)
        log.warning(f"Failed to read length of last measurement")
        return

    response = read_command(mod['serial'], 1, 3, 2612, 2*255, timeout=0.5)
    try:
        crc_check_incoming(response)
        specarray = unpack_response(response, datatype)
        log.info(len(response))
        log.info(specarray)
    except CrcError as err:
        log.exception(err)
        log.warning(f"Failed to read length of last measurement")
        return

    #for key, value in spec.items():
    #    start =  spec[key]['start']
    #    length = spec[key]['len'] * arraylen
    #    log.info(f"Reading {length} registers as array")
    #    datatype = spec[key]['datatype']
    #    response = read_command(mod['serial'], 1, 3, start, length, timeout=0.5)
    #    try:
    #        crc_check_incoming(response)
    #        spec[key]['value'] = unpack_response(response, datatype)
    #        log.info(f"{key}: {spec[key]['value']}")
    #     except CrcError as err:
    #        log.exception(err)
    #        log.warning(f"{key}: Failed to read")

    return


def trigger_measurement(mod):
    """Write register 0x06 with value 0x0400 (1024) to trigger a single measurement"""
    write_single_command(mod['serial'], 1, 6, 1, 1024)


def test_for_triosg2(mod):
    """
    Test whether a trios g2 sensor responds on this port
    specify slave_id, function_code, register_address, no_of_registers (to read)
    """
    slave_address = read_command(mod['serial'], 1, 3, 0, 1)
    measurement_timeout = read_command(mod['serial'], 1, 3, 1, 1)
    deep_sleep = read_command(mod['serial'], 1, 3, 2, 1)
    serial_number = read_command(mod['serial'], 1, 3, 10, 5)

    try:
        crc_check_incoming(slave_address)
        crc_check_incoming(measurement_timeout)
        crc_check_incoming(deep_sleep)
        crc_check_incoming(serial_number)
    except CrcError as err:
        log.exception(err)
        return False

    slave_address = unpack_response(slave_address, datatype='int')
    measurement_timeout = unpack_response(measurement_timeout, datatype='int')
    deep_sleep = unpack_response(deep_sleep, datatype='int')
    serial_number = unpack_response(serial_number, datatype='str')
    log.info(f"slave address: {slave_address} | measurement_timeout: {measurement_timeout} | deep_sleep: {deep_sleep} | serial_nr: {serial_number}")

    return True


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


def parse_data_types(datablock, datatype):
    """deal with different data types"""
    data_hex = codecs.encode(datablock, 'hex')
    try:
        if datatype in ['int', 'bool']:
            data = int.from_bytes(datablock, byteorder='big')
        elif datatype == 'str':
            data = datablock.decode('ascii')
        elif datatype in ['float']:
            if len(datablock)>4:
                log.info(datablock)
            lf = int(len(datablock)/4)
            data = struct.unpack(lf*'>f', datablock)
            if len(data) == 1:
                data = data[0]
        else:
            log.info(f"data type {datatype} not implemented")
            data = None
    except:
        log.warning(f"Could not parse {datablock}, {data_hex}, {data_length} as {datatype}")
        data = None
        pass

    log.debug(f"data hex/int: {data_hex} / {data}")
    return data


def unpack_response(response, datatype='int', ):
    """unpack the hex response"""
    slave_id = int(response[0])  # 1 register
    function_code = int(response[1])  # 1 register
    data_length = int(response[2])  # 1 register
    #datablock = response[3: 3+data_length]  # n registers
    datablock = response[3: -2]  # n registers
    log.debug(f"data block length={data_length}, value={datablock}")
    data = parse_data_types(datablock, datatype)

    return data


def report_slave_id(mod):
    """
    # FIXME: this does not work yet, asked TriOS for clarification on the command to send.

    Special function reporting back sensor informationin ascii coding: sensor name, serial number and firmware version.
    """
    slave_id = 1
    function_code = 11
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

    log.info(response)
    try:
        log.info(response.decode('ascii'))
    except UnicodeDecodeError:
        log.error("Could not decode as ascii response")
        return False

    return True


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


def connect_modbus(ports, port_autodetect_string=None, hwid_autodetect_string=None,
                   port_default=None, baud=9600, db=8, sb=1, parity=serial.PARITY_NONE):
    """connect via modbus"""
    mod = {}

    match = False
    if port_autodetect_string is not None:
        for port, desc, hwid in sorted(ports):
            log.info("port info: {0} {1} {2}".format(port, desc, hwid))
            if port_autodetect_string in desc:
                if hwid_autodetect_string is not None:
                    if hwid_autodetect_string in hwid:
                        # also check hwid if there is more than one interface of this type.
                        mod['port'] = port
                        log.info("Device interface auto-detected on port: {0}".format(port))
                else:
                    mod['port'] = port
                    log.info("Device interface auto-detected on port: {0}".format(port))

    elif port_default is not None:
        log.info(f"Use port default: {port_default}")
        mod['port'] = port_default

    else:
        # test connection on any matching port?
        log.error("No suitable port")

    # Create a serial object for the motor port
    if mod['port'] is not None:
        mod['serial'] = serial.Serial(port=mod['port'],
                                      baudrate=baud,
                                      timeout=1.0, bytesize=db, parity=parity,
                                      stopbits=sb, xonxoff=0)
        mod['serial'].reset_input_buffer()
        mod['serial'].reset_output_buffer()
    else:
        raise serial.SerialException('Could not open motor port')

    # Return the motor dict
    return mod


class command_elements():
    """
    Contains all the components of a motor controller command
    """
    def __init__(self, slave_id, function_code, register_address, operation_type, no_of_registers, value, crc16_check = 0000):
        self.slave_id = hex(slave_id)[2:].zfill(2)
        self.function_code = hex(function_code)[2:].zfill(2)
        self.register_address = hex(register_address + operation_type)[2:].zfill(4)
        self.no_of_registers = hex(no_of_registers)[2:].zfill(4)
        self.no_of_bytes = hex(2 * no_of_registers)[2:].zfill(2)
        self.value = hex(value)[2:].zfill(8)
        self.crc16_check = hex(crc16_check).zfill(4)


def write_single_command(mod_serial, slave_id, function_code, register_address, value):
    """
    Read multiple registers
    e.g. read temperature of driver and motor = read_command(1, 3, 248, 4)
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
    return


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


def execute_commands(commands_list, motor_serial_port):
    """
    Splices together the component parts of a motor controller command using the class variables and then sends over a serial connection

    :param commands_list: Array of each command class to splice into command strings
    :type commands_list: array
    """

    # Iterate through the commands list
    for key, command_class in commands_list.items():
        # Generate the command string for each command
        command_string = generate_command(command_class)

        # Try to convert the command string to hex and send it to the motor controller
        try:
            com_string = codecs.decode(command_string, 'hex')
            motor_serial_port.write(com_string)
            # time.sleep(0.1)
            a = motor_serial_port.read(size=8)

            # Check to see if the motor controller sent any response back
            #if len(a) > 0:
                #print("Received")

        # If an error occurred during the 'try' check for exception
        except KeyboardInterrupt:
            log.warning("Interrupting motor communication...")
            time.sleep(0.3)
        except serial.SerialTimeoutException:
            log.warning("Motor serial timeout exception..")
            time.sleep(0.3)
        except serial.SerialException:
            log.warning("Motor serial exception..")
            time.sleep(0.3)
        finally:
            #serial_port.close()
            #print("Done")
            pass


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


def change_crc16_for_command(command_class):
    """
    Splices together the command string in order to calculate the CRC16 error checking bytes

    :param command_class: Command class to calculate the CRC16 error checking bytes for
    :type command_class: class
    """
    # Generate the command without CRC16 in order to calculate it
    inputcommand = "".join([command_class.slave_id,
                            command_class.function_code,
                            command_class.register_address,
                            command_class.no_of_registers,
                            command_class.no_of_bytes,
                            command_class.value])
    crc16 = calc_crc16(inputcommand)

    # Overwrite the CRC16 value for the command
    command_class.crc16_check = crc16


def generate_command(command_class):
    """Splices together the full motor controller command string using its component variables

    :param command_class: Command class to splice into a command string
    :type command_class: class
    :return: The full command string for the command class
    :rtype: str
    """
    # Calculate an update the CRC16 value for the command
    change_crc16_for_command(command_class)
    # Splice together the elements of the command
    combined_command = "".join([command_class.slave_id,
                                command_class.function_code,
                                command_class.register_address,
                                command_class.no_of_registers,
                                command_class.no_of_bytes,
                                command_class.value,
                                command_class.crc16_check])

    return combined_command


if __name__ == '__main__':
    # start logging here
    log = init_logger()
    run()

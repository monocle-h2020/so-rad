#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Motor Controller Functions

For Oriental Motor stepper motor controller.

Contains a class for the structure of the commands to send to the motor controller
and instances of each type of command that are needed.

As well as these, there are functions to send commands to move the motor, get its
current position and calculate the next position it needs to move to.

The general structure of a single command is
Slave address 8 bits
Function code 8 bits
--03h (3) read from holding register
--06h (6) write to a holding register
--08h (8) diagnosis
--10h (16) write multiple registers
--17h (23) read/write multiple registers
Data          nx8 bits
Error check   16 bits
--error checks are based on the CRC-16 method

The response code follows the same pattern

"""

import time
import serial
import serial.tools.list_ports as list_ports
import libscrc as crc
import os
import sys
import codecs
import threading
import datetime
import sqlite3
import traceback
import logging
import functions.azimuth_functions as azi_func
import functions.gps_functions as gps_func

log = logging.getLogger('motor') #gets the root logger

try:
    import RPi.GPIO as GPIO
except:
    log.warning("GPIO functions not imported. Not running on a Raspberry Pi?")


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

def read_command(motor_serial_port, slave_id, function_code, register_address, no_of_registers):
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
    motor_serial_port.flushInput()
    motor_serial_port.flushOutput()
    motor_serial_port.write(codecs.decode(command, 'hex'))
    # Read the response
    time.sleep(0.2)
    a = motor_serial_port.in_waiting

    # read response of location
    response = motor_serial_port.read(size=a)

    # convert the response into step num
    #motor_pos = codecs.encode(motor_pos, 'hex')
    #motor_pos = motor_pos[6:14]
    #if motor_pos[0:4] == b'ffff':
    #    motor_pos = -1 * (65535 - int(motor_pos[4:], 16))
    #else:
    #    try:
    #        motor_pos = int(motor_pos, 16)
    #    except ValueError:
    #        log.info("No response from motor")
    #        motor_pos = None
    return response


# global command set for Oriental motor
commands = {}
#------ DEFAULT motor SETTINGS ------
op_type_command = command_elements(1,16,6144,0,2,1) # operation type = absolute positioning
commands['op_type_command'] = op_type_command

step_num_command = command_elements(1,16,6144,2,2,0) #number of steps (initially set to 0)
commands['step_num_command'] = step_num_command

speed_command = command_elements(1,16,6144,4,2,2000) #speed = 2 kHz
commands['speed_command'] = speed_command

accel_command = command_elements(1,16,6144,6,2,1500) #acceleration = 1.5 kHz/s
commands['accel_command'] = accel_command

decel_command = command_elements(1,16,6144,8,2,1500) #deceleration = 1.5 kHz/s
commands['decel_command'] = decel_command

start_command = command_elements(1,16,124,0,2,8) #start
commands['start_command'] = start_command

stop_command = command_elements(1,16,124,0,2,0) #stop
commands['stop_command'] = stop_command
#------------------------------


# Interates through the commands in command_list and sends them to the motor controller
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


def return_home(motor_serial_port):
    """
    Sends a pre-programmed command to the motor controller to return to its HOME position (FAST). This disregards any user configuration.
    """
    # Return to home operation (fast)
    home_command_start = "0106007D0010181E"
    home_command_stop = "0106007D000019D2"

    # Sends the commands to the motor controller
    motor_serial_port.write(codecs.decode(home_command_start, 'hex'))
    time.sleep(0.1)
    motor_serial_port.read(size=8)
    motor_serial_port.write(codecs.decode(home_command_stop, 'hex'))
    time.sleep(0.1)
    motor_serial_port.read(size=8)

    log.info("Motor homing command finished")


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


def rotate_motor(command_list, steps_to_rotate, motor_serial_port):
    """Rotate motor to desired _relative_ position from current position

    :param steps_to_rotate: The step number to rotate to
    :type steps_to_rotate: int
    """
    # If steps is negative, generate the correct string
    if steps_to_rotate < 0:
        negative_steps_num = 65535 - abs(steps_to_rotate)
        hex_steps_to_rotate = "".join([hex(65535)[2:], hex(negative_steps_num)[2:]])
    # Otherwise, just convert steps num into hex and zfill
    else:
        hex_steps_to_rotate = hex(int(steps_to_rotate))[2:].zfill(8)

    # substitute the new step num value in the commands dictionary
    command_list['step_num_command'].value = hex_steps_to_rotate

    execute_commands(command_list, motor_serial_port)


def motor_moving(motor_serial_port, final_pos, tolerance=0, timeout=1.0):
    """Checks the motor position until it has reached its destination

    :param motor_serial_port: Serial port that the motor is connected to
    :type motor_serial_port: str

    :param final_pos: The position the motor was given to move to
    :type final pos: int

    :param tolerance: Tolerance in motor step units to determine that destination was reached
    :type tolerance: int

    :param timeout: Timeout in seconds before giving up retrieving motor position
    :type float
    """

    moving = True
    t0 = time.perf_counter()  # timeout reference
    while moving and time.perf_counter()-t0 < timeout:
        # Get motor position
        motor_pos = None
        motor_pos = get_motor_pos(motor_serial_port)
        while motor_pos is None and time.perf_counter()-t0 < timeout:
            motor_pos = get_motor_pos(motor_serial_port)
            time.sleep(0.05)

        if motor_pos is None:
            return False, None

    # If the difference in current pos and new pos is less than the tolerance moving is done.
    if abs(motor_pos - final_pos) <= tolerance:
        is_moving = False
    else:
        is_moving = True

    return is_moving, motor_pos


def get_motor_pos(motor_serial_port):
    """Sends a command to the motor controller to request the current step position and returns it

    :param motor_serial_port: serial object for the motor controller port
    :type motor_serial_port: pyserial object
    :return: motor_pos
    :rtype: int
    """
    # Get motor position command
    get_motor_pos_com = "010300C600022436"  # address ID is assumed to be 01

    # Send the command to the motor to fetch its current position
    motor_serial_port.flushInput()
    motor_serial_port.flushOutput()
    motor_serial_port.write(codecs.decode(get_motor_pos_com, 'hex'))
    # Read the response
    time.sleep(0.2)
    a = motor_serial_port.in_waiting

    # read response of location
    motor_pos = motor_serial_port.read(size=a)

    # convert the response into step num
    motor_pos = codecs.encode(motor_pos, 'hex')
    motor_pos = motor_pos[6:14]
    if motor_pos[0:4] == b'ffff':
        motor_pos = -1 * (65535 - int(motor_pos[4:], 16))
    else:
        try:
            motor_pos = int(motor_pos, 16)
        except ValueError:
            log.info("No response from motor")
            motor_pos = None
    return motor_pos

def motor_temp_read(motor_conf):
    """
    Read driver and motor temperature
    :motor_conf: the MOTOR part of the config dictionary
    """
    # read temperature of motor driver and motor
    num_reg = 4
    try:
        response = read_command(motor_conf['serial'], 1, 3, 248, num_reg)
        slave_id = int(response[0])
        function_code = int(response[1])
        length = int(response[2])
        driver_temp = int.from_bytes(response[3:7], byteorder='big')/10.0
        motor_temp = int.from_bytes(response[7:11], byteorder='big')/10.0
    except:
        return None, None
    return driver_temp, motor_temp

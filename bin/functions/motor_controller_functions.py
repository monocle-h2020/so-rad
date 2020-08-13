#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Motor Controller Functions

Contains a class for the structure of the commands to send to the motor controller
and instances of each type of command that are needed.
As well as these, there are functions to send commands to move the motor, get its
current position and calculate the next position it needs to move to.
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
from configparser import ConfigParser as cp
#from pynput import keyboard
from argparse import Namespace

import functions.azimuth_functions as azi_func
import functions.gps_functions as gps_func

log = logging.getLogger() #gets the root logger

if not sys.platform.startswith('win'):
    if os.uname()[1] == 'raspberrypi' and os.uname()[4].startswith('arm'):
        import RPi.GPIO as GPIO
else:
    log.info("OS detected: {0}".format(sys.platform))
    log.warning("Not running on a Raspberry Pi. Functionality may be limited to system tests.")



#Class to provide the different elements of a motor controller command and the format they have to be in
class command_elements():
    """
    The class that contains all the components of a motor controller command
    """

    def __init__(self, slave_id, function_code, register_address, operation_type, no_of_registers, value, crc16_check = 0000):
        self.slave_id = hex(slave_id)[2:].zfill(2)
        self.function_code = hex(function_code)[2:].zfill(2)
        self.register_address = hex(register_address + operation_type)[2:].zfill(4)
        self.no_of_registers = hex(no_of_registers)[2:].zfill(4)
        self.no_of_bytes = hex(2 * no_of_registers)[2:].zfill(2)
        self.value = hex(value)[2:].zfill(8)
        self.crc16_check = hex(crc16_check).zfill(4)


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


# Clears the terminal based on the OS
def clear_terminal():
    os.system('cls' if os.name == 'nt' else 'clear')

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
            print("Closing...")
            time.sleep(0.3)
        except serial.SerialTimeoutException:
            print("serial timeout exception")
            time.sleep(0.3)
        except serial.SerialException:
            print("serial exception")
            time.sleep(0.3)
        finally:
            #serial_port.close()
            #print("Done")
            pass

# Sends a return to home command to the motor controller
def return_home(motor_serial_port):
    """
    Sends a pre-programmed command to the motor controller to return to its HOME position. This disregards any user configuration.
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

    print("\nHome")

# Calculates the CRC16 error check to be attached to the end of the input command
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

# Replaces the default value for the CRC16 value (0000) to the actual one for that command
def change_crc16_for_command(command_class):
    """
    Splices together the command string in order to calculate the CRC16 error checking bytes

    :param command_class: Command class to calculate the CRC16 error checking bytes for
    :type command_class: class
    """

    # Generate the command without CRC16 in order to calculate it
    inputcommand = "".join([command_class.slave_id, command_class.function_code, command_class.register_address, command_class.no_of_registers, command_class.no_of_bytes, command_class.value])
    crc16 = calc_crc16(inputcommand)

    # Overwrite the CRC16 value for the command
    command_class.crc16_check = crc16

# Generate the full command for the command class and return it
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
    combined_command = "".join([command_class.slave_id, command_class.function_code, command_class.register_address, command_class.no_of_registers, command_class.no_of_bytes, command_class.value, command_class.crc16_check])

    return combined_command

# Calculate the relative heading of the sun in relation to the position of the motor
# using data from the gps sensors
def calc_motor_heading(motor_home_pos, motor_step_limit, motor_position,
                       mot_pos_1, mot_pos_2, cw_limit_deg, ccw_limit_deg):
    """Calculates the relative heading of the sun to the position of the motor using data from the gps sensors

    :return: The relative heading of the sun to the motor position normalised to 360 degrees
    :rtype: int
    """
    # Convert motor_position into degrees and work out the difference in possible positions
    # for where the motor needs to be
    diff_pos_1 = abs(mot_pos_1 - (motor_position / 100)) #100 = steps per degree  TODO: get from config 
    diff_pos_2 = abs(mot_pos_2 - (motor_position / 100))

    if mot_pos_1 >= 0:
        achieve_pos_1 = min([mot_pos_1, cw_limit_deg])
    else:
        achieve_pos_1 = max([mot_pos_1, ccw_limit_deg])

    if mot_pos_2 >= 0:
        achieve_pos_2 = min([mot_pos_2, cw_limit_deg])
    else:
        achieve_pos_2 = max([mot_pos_2, ccw_limit_deg])

    ach_diff_pos_1 = abs(mot_pos_1 - achieve_pos_1)
    ach_diff_pos_2 = abs(mot_pos_2 - achieve_pos_2)

    #if ach_diff_pos_1 == ach_diff_pos_2:

        # Returns the number closest to 0
        #print(sas_pos_1, sas_pos_2, file=sys.stdout)
        #print(new_sas_pos_1, new_sas_pos_2, file=sys.stdout)
    #    new_mot_pos = min([mot_pos_1, mot_pos_2], key=abs)
        # print(new_sas_pos)

    if ach_diff_pos_1 <= ach_diff_pos_2:

        final_mot_pos = achieve_pos_1

    else:

        final_mot_pos = achieve_pos_2

    #print(final_sas_pos, file=sys.stdout)

    # Work out the motor's current actual bearing (not relative to ship).
    # If the motor's home position is in line with the direction the ship
    # is travelling, then the motor's actual bearing will be equal to the
    # ship's heading. TODO: document that the motor should be installed this way,
    # or use the config file setting (motor_home_pos) here.

    # Work out the heading the motor needs to rotate to in order to be facing the sun : FIXME: ? motor should be facing 135 deg away from sun!?
    relative_heading = azi_func.weird_mod(final_mot_pos - motor_home_pos)
    #print("relative_heading", relative_heading, file=sys.stdout)
    return relative_heading, achieve_pos_1, achieve_pos_2


def rotate_motor(command_list, steps_to_rotate, motor_serial_port):
    """Set the value for the step number the motor has to rotate to

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

    #print(hex_steps_to_rotate)
    command_list['step_num_command'].value = hex_steps_to_rotate

    execute_commands(command_list, motor_serial_port)


def motor_moving(motor_serial_port, final_pos, tolerance=0):
    """Checks the motor's position until it has reached its destination

    :param motor_serial_port: Serial port that the motor is connected to
    :type motor_serial_port: str

    :param final_pos: The position the motor was given to move to
    :type final pos: int
    """

    # Get motor position
    motor_pos = get_motor_pos(motor_serial_port)

    if motor_pos is None:
        return False, None  # FIXME: what to return when motor position is unknown? Need to return None and handle this in calling function

    # If the difference in current pos and new pos is less than the tolerance, don't move, otherwise move
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
    #get_motor_pos_com = "010300CC000085F5"
    get_motor_pos_com = "010300C600022436"

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


def motor_calc_and_get_sas(motor_manager, gps_managers):
    """Fetch values from the GPS managers and use them to calculate the ship bearing and target positions"""
    lat0 = gps_managers[0].lat
    lat1 = gps_managers[1].lat
    lon0 = gps_managers[0].lon
    lon1 = gps_managers[1].lon
    alt0 = gps_managers[0].alt
    dt = gps_managers[0].datetime
    ship_bearing = gps_func.calc_ship_bearing(lat0, lon0, lat1, lon1)
    motor_pos_1, motor_pos_2, solar_azi, solar_elev = azi_func.calc_sas_pos(lat0, lon0, alt0, dt, ship_bearing)
    motor_manager.get_sas_pos(motor_pos_1, motor_pos_2)  # update motor target positions in motor_manager instance

    return ship_bearing, solar_azi, solar_elev

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
GPS Functions

Update the polling rate of the connected GPS sensors, create coordinate pairs to calculate
ship bearing and create a dictionary of useful variables.
"""

#import time
#import serial
#import libscrc as crc
#import codecs

from .compass_bearing import calculate_initial_compass_bearing


def change_gps_rate(update_rate):
    """Generate the PMTK string to change the gps sensor's update rate

    :param update_rate: The polling frequency of the gps sensor
    :type update_rate: int
    :return: The PMTK string as a byte string
    :rtype: str
    """

    # Create the start of the PMTK string to update the update rate
    rate_string = 'PMTK220,' + str(int(1000/update_rate))

    crc = 0
    # For each character in the PMTK string
    for char in rate_string:
        # Get the unicode code for that character
        ascii_value = ord(char)
        # Calculate XOR for crc and ascii value and set to crc
        crc ^= ascii_value
    #Get the hex value of crc
    hex_crc = hex(crc)
    # Makes sure the crc value has two digits and strips the 0x from the beginning
    if crc <= 0xF:
        crc_byte = '0' + hex_crc[2]
    else:
        crc_byte = hex_crc[2:4]

    # Construct the completed string and convert to bytes object
    rate_string_full = '$' + rate_string + '*' + str(crc_byte) + '\r\n'
    rate_byte_string = bytes(rate_string_full, 'utf-8')

    return rate_byte_string


def update_gps_rate(gps_ser, rate_value):
    """Send the generated PMTK update rate string to each gps sensor and receive confirmation back of the change

    :param rate_value: The update rate to change the gps sensors to
    :type rate_value: int
    """
    # Set the GPS sensor update rates
    gps_ser.write(change_gps_rate(rate_value))

    # Ask the sensors to return their new update rates
    gps_ser.write(b'$PMTK400*36\r\n')


def calc_ship_bearing(lat1, lon1, lat2, lon2):
    """Create the GPS coordinate tuples before passing into the calculate bearing function
    
    :param lat1: latitude of GPS 1
    :type lat1: float
    :param lon1: longitude of GPS 1
    :type lon1: float
    :param lat2: latitude of GPS 2
    :type lat2: float
    :param lon2: longitude of GPS 2
    :type lon2: float
    :return: ship_bearing
    :rtype: float
    """

    # Creates two coordinate pairs for the two current GPS locations
    point1 = (lat1, lon1)
    point2 = (lat2, lon2)

    # Calculate the ships heading from the two GPS coordinates
    ship_bearing = calculate_initial_compass_bearing(point1, point2)

    return ship_bearing


def create_gps_dict(gps_manager):
    """Create a dictionary containing useful gps manager data"""
    gps_dict = {}
    gps_dict['datetime'] = gps_manager.datetime
    gps_dict['fix'] = gps_manager.fix
    gps_dict['latitude'] = gps_manager.lat
    gps_dict['longitude'] = gps_manager.lon
    gps_dict['poll_rate'] = gps_manager.update_rate
    gps_dict['speed'] = gps_manager.speed
    gps_dict['bearing_accuracy'] = gps_manager.relPosHeading

    return gps_dict

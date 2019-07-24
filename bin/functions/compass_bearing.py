#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Compass Bearing Calculation

Using Vincenty's Formula, calculates the bearing between two GPS coordinate pairs.
"""

import os
import datetime
import time
import math
from decimal import *

# Set the number of decimal points to 8 in calculations
getcontext().prec = 8

fix = 0

# Function for calculating the compass bearing between two coordinates
def calculate_initial_compass_bearing(rear, front):
    """
    Calculates the bearing between a pair of latitude and
                  longitude coordinates.

    The formulae used is Vincenty's Formulae and has the form:
        θ = arctan(sin(Δlon).cos(lat2) /
                  cos(lat1).sin(lat2) − sin(lat1).cos(lat2).cos(Δlon))

    :Parameters:
      - `front: A tuple of the latitude and longitude for the
        first gps sensor (in decimal degrees)
      - `rear: A tuple of the latitude and longitude for the
        second gps sensor (in decimal degrees)

    :Returns:
      The bearing in degrees

    :Returns Type:
      float
    """

    # If either of the coordinates is not in the format of a tuple raise a TypeError
    if (type(front) != tuple) or (type(rear) != tuple):
        raise TypeError("Only tuples are supported as arguments")

    # Try to carry out the calculations
    try:
        # Extract the latitudes from the two coordinates
        lat1 = math.radians(float(rear[0]))
        lat2 = math.radians(float(front[0]))

        # Work out the difference in the longitudes of the two coordinates
        lon_diff = math.radians(float(front[1]) - float(rear[1]))

        # Plug the values into the numerator and denominator of Vincenty's formulae
        x = math.sin(lon_diff) * math.cos(lat2)
        y = math.cos(lat1) * math.sin(lat2) - (math.sin(lat1)
                * math.cos(lat2) * math.cos(lon_diff))
        #x = math.cos(lat1) * math.sin(lon_diff)
        #y = (-1 * math.sin(lat1) * math.cos(lat2)) + (math.cos(lat1) * math.sin(lat2) * math.cos(lon_diff))

        # Divide numerator by denominator and find the arctan of it
        bearing = math.atan2(x, y)

        # math.atan2 returns values between -180° to + 180° which is not
        # correct for compass bearings so the bearing has to be normalised
        bearing = math.degrees(bearing)
        compass_bearing = (bearing + 360) % 360

    # If the calculations fail
    except:
        print('\n- calc bearing error -\n')
        compass_bearing = 0
    
    # Return the value
    return compass_bearing

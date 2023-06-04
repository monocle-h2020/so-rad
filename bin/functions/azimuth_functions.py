#!/usr/bin/env python3
"""
Azimuth Calculations

Using PyEphem and GPS latitude and longitude coordinates, calculate the position of the Sun relative to the observer.
Using the position of the Sun and the motor, calculate the ideal and achievable positions for the motor controller
and radiometers.
"""
import ephem
import math
from numpy import argsort


def wrap180(value):
    """
    This performs modulo operation with 180 and preserves the sign
    :param value: Value to modulo
    :type value: float

    :return: Value MOD 180
    :rtype: float
    """
    if value > 180.0:
        value -= 360
    elif value < -180.0:
        value += 360

    if value > 180.0 or value < -180.0:
        wrap180(value)

    return value

def solar_az_el(lat, lon, altitude, datetime_):
    """
    Return solar azimuth and elevation angles using ephem
    """
    observer = ephem.Observer()
    sun = ephem.Sun()

    # Update the observer to our current location
    observer.lat = str(lat)
    observer.lon = str(lon)
    observer.elevation = altitude
    observer.date = datetime_

    sun.compute(observer)

    # Get solar angles
    solar_az_deg = math.degrees(sun.az)
    solar_el_deg = math.degrees(sun.alt)

    return solar_az_deg, solar_el_deg


def sun_relative_azimuth(lat, lon, altitude, datetime_, ship_bearing, motor_deg, motor_dict):
    """
    Return the current azimuth of sensors with respect to the sun
    """
    try:
        assert lat is not None
        assert lon is not None
        assert datetime_ is not None
        assert ship_bearing is not None
        assert motor_dict is not None
        assert motor_deg is not None
    except AssertionError:
        return None, None

    # Get solar angles
    solar_az_deg, solar_el_deg = solar_az_el(lat, lon, altitude, datetime_)

    # Viewing positions relative to compass (range 0 - 359, 0 = North)
    view_comp_cw = (solar_az_deg + 135.0) % 360.0
    view_comp_ccw = (solar_az_deg - 135.0) % 360.0

    # positions relative to motor home (offset corrected)  position (0 = motor home)
    motor_home_offset = motor_dict['home_pos']
    # motor_to_sun_deg  = (solar_az_deg - ship_bearing) - motor_home_offset + motor_dict['motor_deg'] % 360.0
    motor_to_ship_rel = motor_deg + motor_home_offset  # the motor offset is accounted for here, and only here. This gives the angle between radiometers and ship heading
    motor_to_compass = (motor_to_ship_rel + ship_bearing)  % 360.0   # compass angle of the radiometers

    motor_to_sun = wrap180(motor_to_compass - solar_az_deg)           # difference between motor and solar compass angles

    # Check that the positions are -180 -> 180
    assert 180.0 >= motor_to_sun >= -180.0

    return motor_to_sun, solar_az_deg


def calculate_positions(lat, lon, altitude, datetime_, ship_bearing, motor_dict, motor_pos_steps):
    """
    Do solar and motor angle calculations
    : floats lat, lon, altitude, datetime_ from gps
    : float ship_bearing from gps heading
    : motor_dict has limit settings
    : float motor_pos_steps is current motor position in steps
    """

    try:
        assert lat is not None
        assert lon is not None
        assert altitude is not None
        assert datetime_ is not None
        assert ship_bearing is not None
        assert motor_dict is not None
        assert motor_pos_steps is not None

    except AssertionError:
        return None, None, None

    # Get solar angles
    solar_az_deg, solar_el_deg = solar_az_el(lat, lon, altitude, datetime_)

    # Viewing positions relative to compass (range 0 - 359, 0 = North)
    view_comp_cw = (solar_az_deg + 135.0) % 360.0
    view_comp_ccw = (solar_az_deg - 135.0) % 360.0

    # positions relative to motor home (offset corrected)  position (0 = motor home)
    motor_home_offset = motor_dict['home_pos']
    sol_az_motor_deg = (solar_az_deg - ship_bearing) - motor_home_offset
    view_motor_cw =  (sol_az_motor_deg + 135.0) % 360.0
    view_motor_ccw = (sol_az_motor_deg - 135.0) % 360.0
    # wrap angles to [-180,180]
    sol_az_motor_deg = wrap180(sol_az_motor_deg)
    view_motor_cw_deg = wrap180(view_motor_cw)
    view_motor_ccw_deg = wrap180(view_motor_ccw)

    # Check that the positions are -180 -> 180
    assert 180.0 >= view_motor_cw_deg >= -180.0
    assert 180.0 >= view_motor_ccw_deg >= -180.0

    # Adjust for motor turning limits, still in degrees
    cw_limit_deg = motor_dict['cw_limit']
    ccw_limit_deg = motor_dict['ccw_limit']
    if view_motor_cw_deg > cw_limit_deg:
       achieved_view_motor_cw_deg = cw_limit_deg
    elif view_motor_cw_deg < ccw_limit_deg:
       achieved_view_motor_cw_deg = ccw_limit_deg
    else:
       achieved_view_motor_cw_deg = view_motor_cw_deg

    if view_motor_ccw_deg > cw_limit_deg:
       achieved_view_motor_ccw_deg = cw_limit_deg
    elif view_motor_ccw_deg < ccw_limit_deg:
       achieved_view_motor_ccw_deg = ccw_limit_deg
    else:
       achieved_view_motor_ccw_deg = view_motor_ccw_deg

    # the four options are (some of these will be duplicate solutions)
    angle_options = [achieved_view_motor_cw_deg, achieved_view_motor_ccw_deg, cw_limit_deg, ccw_limit_deg]

    # compare achievable angles to sun (still in motor plane with 0 = home)
    ach_rel_cw =  abs(achieved_view_motor_cw_deg - sol_az_motor_deg)
    ach_rel_ccw = abs(achieved_view_motor_ccw_deg - sol_az_motor_deg)
    ach_at_cw_limit = abs(cw_limit_deg - sol_az_motor_deg)
    ach_at_ccw_limit = abs(ccw_limit_deg - sol_az_motor_deg)

    # how well do these achievable angles correspond to the optimum positions?
    angle_options_diff = [abs(achieved_view_motor_cw_deg - view_motor_cw_deg),
                          abs(achieved_view_motor_ccw_deg - view_motor_ccw_deg)]
    best_ach_angle_index = argsort(angle_options_diff)[0]

    ach_rel_angles_are_similar = abs(angle_options_diff[0]- angle_options_diff[1]) <= 5.0  # if similar also consider the travel distance

    # compare to current motor position
    motor_pos_deg = float(motor_pos_steps) / motor_dict['steps_per_degree']
    travel_distance_cw =  abs(motor_pos_deg - achieved_view_motor_cw_deg)
    travel_distance_ccw = abs(motor_pos_deg - achieved_view_motor_ccw_deg)

    travel_distances = [travel_distance_cw, travel_distance_ccw]

    #if ach_rel_angles_are_similar and (travel_distances[argsort(d135)[1]] <= travel_distances[argsort(d135)[0]]):
    if ach_rel_angles_are_similar and (travel_distances[argsort(angle_options_diff)[1]] <= travel_distances[argsort(angle_options_diff)[0]]):
        # stay with second-best for now
        target_motor_pos_deg = angle_options[argsort(angle_options_diff)[1]]
    else:
        target_motor_pos_deg = angle_options[argsort(angle_options_diff)[0]]  # move to optimal position

    target_motor_pos_step = int(round(target_motor_pos_deg * motor_dict['steps_per_degree']))

    motor_angles = {'target_motor_pos_deg': target_motor_pos_deg,
                    'target_motor_pos_step': target_motor_pos_step,
                    'view_comp_cw': view_comp_cw,
                    'view_comp_ccw': view_comp_ccw,
                    'ach_rel_cw': ach_rel_cw,
                    'ach_rel_ccw': ach_rel_ccw,
                    'ach_mot_cw': achieved_view_motor_cw_deg,
                    'ach_mot_ccw': achieved_view_motor_ccw_deg,
                    'sol_az_to_motor_deg_abs': abs(sol_az_motor_deg),
                    'target_motor_pos_rel_az_deg': wrap180(abs(target_motor_pos_deg - sol_az_motor_deg))}

    # 1 - sol_az_to_motor_deg_abs is the current angle (before adjustments are made) between motor home and sun
    # 2 - target_motor_pos_rel_az_deg is the achievable angle, which will be true after motor has moved (respecting angle limits)

    return solar_az_deg, solar_el_deg, motor_angles

if __name__ == '__main__':
    """Test to check behaviour or relative viewing angle calculations."""
    import datetime
    motor_dict = {}
    motor_dict['home_pos'] = 10
    lat = 50.0
    lon = -4.0
    altitude = 40
    datetime_ = datetime.datetime.now()
    print(f"motor\tship\tsun\trel_az")
    for mdeg in range(0,360,30):
        for sdeg in range(0,360,60):
            motor_dict['motor_deg'] = mdeg
            rel_az, solar_az = sun_relative_azimuth(lat, lon, altitude, datetime_, sdeg, motor_dict)
            print(f"{mdeg}\t{sdeg}\t{int(solar_az)}\t{int(rel_az)}")

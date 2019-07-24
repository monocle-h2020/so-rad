#!/usr/bin/env python3
# -*- coding: utf-8 -*-

#import minimalmodbus
#import __future__
import time
import serial
import libscrc as crc
import json
import os
import sys
import codecs
from pprint import pprint
#from hypersas.motor_controller_new.azimuth_calc import azimuthcalc

#sys.path.append('/users/rsg/oco/Repos/MONOCLE/Rrs_azimuth/hypersas/motor_controller_new/azimuth_calc')

from azimuth_calc.azimuth_calc import AzimuthWindow#, SolarDegrees

from functions.gps_functions import calculate_initial_compass_bearing

#------------------
#serial_port = serial.Serial(port='COM4', baudrate=115200, timeout=None, bytesize=8, parity='E', stopbits=1, xonxoff=0)
serial_port = serial.Serial(port='/dev/ttyUSB3', baudrate=115200, timeout=None, bytesize=8, parity='E', stopbits=1, xonxoff=0)
serial_port.flushInput()
serial_port.flushOutput()
#serial_port.open()
#------------------


class command_elements():
    def __init__(self, slave_id, function_code, register_address, operation_type, no_of_registers, value, crc16_check = 0000):
        self.slave_id = hex(slave_id)[2:].zfill(2)
        self.function_code = hex(function_code)[2:].zfill(2)
        self.register_address = hex(register_address + operation_type)[2:].zfill(4)
        self.no_of_registers = hex(no_of_registers)[2:].zfill(4)
        self.no_of_bytes = hex(2 * no_of_registers)[2:].zfill(2)
        self.value = hex(value)[2:].zfill(8)
        self.crc16_check = hex(crc16_check).zfill(4)



def open_config():
    with open("motor_settings_config.json") as config_file:
        config = json.load(config_file)
        pprint(config)

        print(config["FUNCTION_CODE"])


def menu():

    print("-"*100)
    print("Motor Controller Menu")
    print("-"*100)
    print("1) Rotate Motor")
    print("2) Check a sensor")
    print("3) Change settings")
    print("4) Sun info")
    print("")
    print("0) Quit")
    print("")

    while True:
        print("\nPlease select an option: (1,2,...)")
        option = int(input())
        if option < 0 or option > 4:
            print("\nInvalid option")
        else:
            return option


def sensor_menu():

    print("-"*100)
    print("Sensor Menu")
    print("-"*100)
    print("1) Driver/Motor Temperature")
    print("2) Odometer")
    print("3) Tripmeter")
    print("4) GPS sensor locations")
    print("5) Motor position")
    print("")
    print("0) Return to menu")
    print("")

    while True:
        print("\nPlease select an option: (1,2,...)")
        option = int(input())
        if option < 0 or option > 5:
            print("\nInvalid option")
        else:
            return option


def settings_menu():

    print("-"*100)
    print("Settings Menu")
    print("-"*100)
    print("1) Operation Type")
    print("2) Speed")
    print("3) Acceleration/Deceleration")
    print("")

    while True:
        print("\nPlease select an option: (1,2,...)")
        option = int(input())
        if option < 1 or option > 3:
            print("\nInvalid option")
        else:
            return option


def sun_menu():

    print("-"*100)
    print("Sun Menu")
    print("-"*100)
    print("1) Altitude")
    print("2) Azimuth")
    print("3) Ship bearing")
    print("")

    while True:
        print("\nPlease select an option: (1,2,...)")
        option = int(input())
        if option < 1 or option > 3:
            print("\nInvalid option")
        else:
            return option


def clear_terminal():
    os.system('cls' if os.name == 'nt' else 'clear')


def execute_commands(commands_list):
    
    for command_class in commands_list:
        command_string = generate_command(command_class)
    
        try:
            com_string = codecs.decode(command_string, 'hex')
            print("\ntransmit", com_string)
            serial_port.write(com_string)
            time.sleep(0.1)
            a = serial_port.read(size=8)
            print("receive", str(a))

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
            print("Done")


def return_home():
    #return to home operation (fast)
    home_command_start = "0106007D0010181E"
    home_command_stop = "0106007D000019D2"

    serial_port.write(codecs.decode(home_command_start, 'hex'))
    time.sleep(0.1)
    serial_port.read(size=8)
    serial_port.write(codecs.decode(home_command_stop, 'hex'))
    time.sleep(0.1)
    serial_port.read(size=8)

    print("\nHome")


def calc_crc16(inputcommand):
    print(inputcommand)

    crc16_modbus = hex(int(crc.modbus(codecs.decode(inputcommand, 'hex'))))
    converted_crc16_modbus = ''.join([crc16_modbus[4:6], crc16_modbus[2:4]])
    print(converted_crc16_modbus)
    #converted_crc16_modbus = crc16_modbus

    return converted_crc16_modbus


def change_crc16_for_command(command_class):
    
    inputcommand = "".join([command_class.slave_id, command_class.function_code, command_class.register_address, command_class.no_of_registers, command_class.no_of_bytes, command_class.value])
    crc16 = calc_crc16(inputcommand)
    
    #inputcommand_with_crc16 = '{}{}'.format(inputcommand, crc16_hex)
    #commands_with_crc16.append(command)

    command_class.crc16_check = crc16


def generate_command(command_class):
    change_crc16_for_command(command_class)
    combined_command = "".join([command_class.slave_id, command_class.function_code, command_class.register_address, command_class.no_of_registers, command_class.no_of_bytes, command_class.value, command_class.crc16_check])
    #combined_command_with_crc16 = append_crc16_to_command(combined_command)

    return combined_command


def rotate_motor():

    # while True:
    #     print "How many steps do you want to rotate by? (36000 steps = 360 degrees)"
    #     steps = int(input())
    #     if steps < 1 or steps > 36000:
    #         print "Invalid input. Please enter between 1 and 36000.\n"
    #     else:
    #         break
    #
    # step_num_command.value = str(hex(steps))[2:].zfill

    motor_relative_heading = 0.0
    print("motor relative heading to ship =", motor_relative_heading)
    
    #gps_fix = sun_test.gps_manager.fix
    #print("gps fix =", gps_fix)

    # point1 = (sun_test.latitude,sun_test.longitude)
    # time.sleep(5)
    # point2 = (sun_test.latitude,sun_test.longitude)
    point1 = (sun_test.gps_managers[0].lat,sun_test.gps_managers[0].lon)
    #time.sleep(0.5)
    point2 = (sun_test.gps_managers[1].lat,sun_test.gps_managers[1].lon)

    ship_bearing = calculate_initial_compass_bearing(point1, point2)
    print("TEST ship bearing =", ship_bearing)

    motor_actual_heading = ship_bearing + motor_relative_heading
    print("motor actual heading =", motor_actual_heading)

    sun_azi = sun_test.solar_azimuth
    print("sun azimuth =", sun_azi)

    relative_heading = ((sun_azi - motor_actual_heading) + 360) % 360 #prevents giving a negative value
    print("motor needs to rotate =", relative_heading)

    steps_to_rotate = (relative_heading / 360) * 36000
    print("steps to rotate =", round(steps_to_rotate))

    step_num_command.value = hex(int(steps_to_rotate))[2:].zfill(8)

    execute_commands(commands)


def get_motor_pos(motor_serial_port):

    # Get motor position command
    #get_motor_pos_com = "010300CC000085F5"
    get_motor_pos_com = "010300C600022436"

    print(get_motor_pos_com)
    # Send the command to the motor to fetch its current position
    motor_serial_port.write(codecs.decode(get_motor_pos_com, 'hex'))
    # Read the response
    time.sleep(0.1)
    a = motor_serial_port.in_waiting
    print(a)
    motor_pos = motor_serial_port.read(size=a)

    motor_pos = codecs.encode(motor_pos, 'hex')
    motor_pos = int(motor_pos[6:14], 16)

    print('motor_pos {}'.format(motor_pos))

    #return motor_pos


# operation_no_change_to_1 = "\x01\x10\x00\x7A\x00\x02\x04\x00\x00\x00\x08\x75\x32"
# serial_port.write(operation_no_change_to_1)
# time.sleep(0.1)
# serial_port.read(size=8)
# print "\nop no change to 1\n"


commands = []


#------ DEFAULT SETTINGS ------
op_type_command = command_elements(1,16,6144,0,2,2) # operation type
commands.append(op_type_command)

step_num_command = command_elements(1,16,6144,2,2,8500) #number of steps
commands.append(step_num_command)

speed_command = command_elements(1,16,6144,4,2,2000) #speed
commands.append(speed_command)

accel_command = command_elements(1,16,6144,6,2,1500) #acceleration
commands.append(accel_command)

decel_command = command_elements(1,16,6144,8,2,1500) #deceleration
commands.append(decel_command)

start_command = command_elements(1,16,124,0,2,8) #start
commands.append(start_command)

stop_command = command_elements(1,16,124,0,2,0) #stop
commands.append(stop_command)
#------------------------------

gps_list = ['/dev/ttyUSB8', '/dev/ttyUSB5']

sun_test = AzimuthWindow(gps_list)
time.sleep(0.5)
sun_test.log_activated(True)
time.sleep(0.5)
sun_test.gps_activated(True)
time.sleep(0.5)
sun_test.sas_activated(True)

time.sleep(4)


while True:

    clear_terminal()

    print("\n")
    menu_option = menu()
    if menu_option == 1:
        #rotate motor
        rotate_motor()

        time.sleep(20)

        return_home()

    elif menu_option == 2:
        #check sensor

        clear_terminal()

        print("\n")
        sensor_option = sensor_menu()

        if sensor_option == 1:
            #Temperatures
            
            temp_commands = ["010300F8000245FA", "010300FA0002E43A"]
            #temp_command_ = calc_crc16(temp_command)
            #print temp_command_
            #new_temp_command = temp_command #+ temp_command_
            
            motor_temp = False
            for temp_command in temp_commands:
                serial_port.write(codecs.decode(temp_command, 'hex'))
                print("\ntransmit", temp_command)
                time.sleep(0.1)
                a = serial_port.read(size=9)
                temp_receive = hex(int(codecs.encode(a, 'hex')))
                print("receive", temp_receive)

                if not motor_temp:
                    print("driver temperature =", float(int(temp_receive[10:15], 16))/10, "Celsius")
                    motor_temp = True
                else:
                    print("motor temperature =", float(int(temp_receive[10:15], 16))/10, "Celsius")

        elif sensor_option == 2:
            #Odometer
            
            odom_command ="010300FC0002043B"
            #temp_command_ = calc_crc16(temp_command)
            #print temp_command_
            #new_temp_command = temp_command #+ temp_command_

            serial_port.write(codecs.decode(odom_command, 'hex'))
            print("\ntransmit", odom_command)
            time.sleep(0.1)
            a = serial_port.read(size=9)
            odom_receive = hex(int(codecs.encode(a, 'hex')))
            print("receive", odom_receive)

            print("odometer value =", float(int(odom_receive[10:15], 16))/10, "kRev")

        elif sensor_option == 3:
            #Tripmeter
            
            trip_command = "010300FE0002A5FB"
            #temp_command_ = calc_crc16(temp_command)
            #print temp_command_
            #new_temp_command = temp_command #+ temp_command_

            serial_port.write(codecs.decode(trip_command, 'hex'))
            print("\ntransmit", trip_command)
            time.sleep(0.1)
            a = serial_port.read(size=9)
            trip_receive = hex(int(codecs.encode(a, 'hex')))
            print("receive", trip_receive)

            print("tripmeter value =", float(int(trip_receive[10:15], 16))/10, "kRev")

        elif sensor_option == 4:
            print("gps1 lat lon =", sun_test.gps_manager.lat, sun_test.gps_manager.lon)
            #time.sleep(0.1)
            print("gps2 lat lon =", sun_test.gps_manager2.lat, sun_test.gps_manager2.lon)
        
        elif sensor_option == 5:
            #Motor position
            
            motor_pos = get_motor_pos(serial_port)

            #print("Motor position =", motor_pos)

        elif sensor_option == 0:
            #pass
            print("\n")

        #print "\n\n"

    elif menu_option == 3:
        #settings_menu

        clear_terminal()

        print("\n")
        settings_option = settings_menu()

        if settings_option == 1:
            print("change_op_type()")
        
        elif settings_option == 2:
            print("change_speed()")
        
        elif settings_option == 3:
            print("change_accel_decel()")

        #print "\n\n"
        #open_config()

    elif menu_option == 4:
        #sun location into menu

        clear_terminal()

        print("\n")
        sun_option = sun_menu()

        if sun_option == 1:
            print("\nAltitude =", sun_test.gps_manager.alt)
        
        if sun_option == 2:
            print("\nAzimuth =", sun_test.solar_azimuth)

        if sun_option == 3:
            print("\nsun_test heading =", sun_test.heading)
            point1 = (sun_test.latitude,sun_test.longitude)
            print(point1)
            time.sleep(5)
            point2 = (sun_test.latitude,sun_test.longitude)
            print(point2)
            ship_bearing = calculate_initial_compass_bearing(point1, point2)
            print("\nShip bearing =", ship_bearing)
            print("\nSolar azimuth =", sun_test.solar_azimuth)

    elif menu_option == 0:
        #close program
        break

    time.sleep(5)
    print("\nPress Enter to return to the menu")
    try:
        raw_input()
    except:
        pass
    


sun_test.log_activated(False)
sun_test.gps_activated(False)
sun_test.sas_activated(False)
#sun_test.__del__

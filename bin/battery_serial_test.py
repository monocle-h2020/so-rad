#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import serial
import os
import serial.tools.list_ports as list_ports
import codecs
import re

battery_connected = True
battery_baud = 19200
battery_port = ""


# Clears the terminal based on the OS
def clear_terminal():
    os.system('cls' if os.name == 'nt' else 'clear')


ports = list_ports.comports()
for port, desc, hwid in sorted(ports):
    if desc == 'TTL232R' and battery_connected:
        battery_port = port
        print("Battery using port:", battery_port)


serial_port = serial.Serial(port=battery_port, baudrate=battery_baud, timeout=None, bytesize=8, parity='N', stopbits=1, xonxoff=0)
serial_port.reset_input_buffer()
serial_port.reset_output_buffer()

while True:
    a = serial_port.readline()
    #print(a)
    b = [str(b, 'utf-8') for b in a.split()]
    #print(b)
    try:
        if b[0] == 'Checksum':
            clear_terminal()
            print("Battery using port:", battery_port)
    except:
        pass
    print(" ".join(b))


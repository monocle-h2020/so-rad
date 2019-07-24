.. _Motor Controller Manager:

Motor Controller Manager
========================

This is the main script for running the motor controller program and initialise all of the other threads. This script:

* Automatically detects ports motor controller and gps sensors are connected to using device descriptions
* Calculates the relative bearing of the sun to the direction the ship is heading
* Logs relevant data to a database to be sent to the SOS proxy
* Generates commands to send to the motor controller and gps sensors based on user input
* Sends commands to the motor controller and gps sensors using PySerial



The USB device detection is determined using Pyserial's list_ports() function.

.. code-block:: python

    ports = list_ports.comports()
    for port, desc, hwid in sorted(ports):
        if desc == 'USB-RS485 Cable' and motor_connected:
            motor_port = port
            print("Motor using port:", motor_port)
        elif desc == 'CP2102 USB to UART Bridge Controller' and gps_count > 0:
            if not gps1_found:
                gps_ports.append(port)
                print("GPS1 using port:", gps_ports[0])
                gps1_found = True
            elif gps1_found and gps_count == 2:
                gps_ports.append(port)
                print("GPS2 using port:", gps_ports[1])


#!/usr/bin/env python3
"""
Attempt to control digital pins and I2C together
"""

import board
import digitalio
import busio
import time

print("Test start")

# Try to great a Digital input
pin = digitalio.DigitalInOut(board.D27)
print("Digital IO ok!")

# Try to create an I2C device
i2c = busio.I2C(board.SCL, board.SDA)
print("I2C ok!")

# Blink the GPIO controlled relay (don't do this with sensors attached)

relay = digitalio.DigitalInOut(board.D27)
relay.direction = digitalio.Direction.OUTPUT

while True:
    relay.value = True
    time.sleep(1.0)
    relay.value = False
    time.sleep(1.0)



print("done!")

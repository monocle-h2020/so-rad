#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Motor Manager
"""
import time
import threading
import logging
#from pysolar.solar import *
import functions.motor_controller_functions as motor_func

log = logging.getLogger()   # report to root logger


class MotorThread(threading.Thread):
    """
    Thread to read the motor's serial port
    """
    def __init__(self, parent, serial_port):
        threading.Thread.__init__(self)
        self.serial_port = serial_port
        self._parent = parent

        self.observers = []

        self.stop_motor_thread = False
        self.prev_steps = 0
        self.motor_pos = 0
        self.achieve_pos_1 = 0
        self.achieve_pos_2 = 0
        log.info("Starting Motor thread")

    def run(self):
        log.info("motor thread running")

        while not self.stop_motor_thread:
            try:
                # Calculate the relative heading of the motor
                relative_heading, self.achieve_pos_1, self.achieve_pos_2 = motor_func.calc_motor_heading(self._parent.home_pos, self._parent.step_limit, self.motor_pos, self._parent.motor_pos_1, self._parent.motor_pos_2, self._parent.cw_limit, self._parent.ccw_limit)

                # Convert it to step number
                relative_heading_step_num = int(relative_heading * (self._parent.step_limit/360))

                self.motor_pos = motor_func.get_motor_pos(self._parent.port)

                if int(abs(abs(self.motor_pos) - abs(relative_heading_step_num))) >= self._parent.step_thresh: #if difference < 5 degrees

                    log.info("move to {0}".format(relative_heading_step_num))
                    # Rotate the motor to the new position
                    motor_func.rotate_motor(motor_func.commands, relative_heading_step_num, self._parent.port)
                    # execute_commands(commands)

                    self.prev_steps = relative_heading_step_num

                self._parent.update_pos(self.prev_steps, self.motor_pos, self.achieve_pos_1, self.achieve_pos_2)

            except Exception as m:
                log.warning("Exception ignored in motor thread: \n{0}".format(m))
                pass

            time.sleep(self._parent.check_angle_every_sec)


class MotorManager(object):
    """Object to manage the motor controller"""
    def __init__(self, motor_dict):
        self.motor_position = 0
        self.moved = False
        self.prev_steps = 0
        self.motor_pos_1 = 0
        self.motor_pos_2 = 0
        self.achieve_pos_1 = 0
        self.achieve_pos_2 = 0
        self.started = False

        self.motor_thread = None
        self.motor_lock = threading.Lock()

        self.motor_observers = []
        self.check_angle_every_sec = motor_dict['check_angle_every_sec']
        self.port = motor_dict['serial']
        self.home_pos = motor_dict['home_pos']
        self.step_limit = motor_dict['step_limit']
        self.cw_limit = motor_dict['cw_limit']
        self.ccw_limit = motor_dict['ccw_limit']
        self.step_thresh = motor_dict['step_thresh']

    def __del__(self):
        self.stop()

    def start(self):
        """Start the Motor manager thread if not already running"""
        if not self.started:
            self.started = True
            self.motor_thread = MotorThread(self, self.port)
            time.sleep(0.2)
            self.motor_observers.append(self.motor_thread)
        else:
            log.warn("Motor manager alread started")

        self.motor_thread.start()
        log.info("Started Motor manager")

    def stop(self):
        """Stop the Motor manager thread"""
        log.info("Stopping Motor manager")
        self.motor_thread.stop_motor_thread = True
        time.sleep(1)
        self.motor_thread.join()
        log.info("motor alive? = {}".format(self.motor_thread.is_alive()))
        self.started = False

    def update_pos(self, prev_steps_num, motor_pos_num, achieve_pos_1, achieve_pos_2):
        """Update the Motor manager variables using the values passed in as arguments"""
        self.motor_lock.acquire(True)
        self.prev_steps = prev_steps_num
        self.motor_position = motor_pos_num
        self.achieve_pos_1 = achieve_pos_1
        self.achieve_pos_2 = achieve_pos_2
        self.motor_lock.release()

    def get_sas_pos(self, motor_pos_1, motor_pos_2):
        """Fetch the motor position variables"""
        self.motor_pos_1 = motor_pos_1
        self.motor_pos_2 = motor_pos_2

    def within_step_thresh(self):
        """Check if the newly calculated position is within the threshold from the current motor position"""
        if abs(self.motor_position - self.prev_steps) <= self.step_thresh:
            return True
        else:
            return False
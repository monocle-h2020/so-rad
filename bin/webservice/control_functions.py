#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Set of functions used to control So-Rad via web interface
"""

import os
import subprocess


def restart_service(service):
    "restart a systemd service"
    assert ' ' not in service  # 1 word allowed
    status = os.system(f"/usr/bin/sudo systemctl restart {service}")
    print(status)
    if status == 0:
        return True
    elif status == 1:
        return False
    else:
        return status

def stop_service(service):
    "stop a systemd service"
    assert ' ' not in service  # 1 word allowed
    status = os.system(f"/usr/bin/sudo systemctl stop {service}")
    print(status)
    return status

def service_status(service):
    "display system service status"
    assert ' ' not in service  # 1 word allowed
    command = ["/usr/bin/systemctl", "is-active", f"{service}"]
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    status = process.wait()
    message = process.stdout.read().decode('utf-8').strip()
    if status == 0:
        return True, message
    else:
        return False, message

def run_motor_home_test():
    "Run a system test: motor to home location"
    command = ["/usr/bin/python", "../tests/test_motor_home.py"]
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    status = process.wait()
    message = process.stdout.read().decode('utf-8')
    messages = message.split('\n')
    if status == 0:
        return True, messages
    else:
        return False, messages

def run_gps_test():
    "Run a system test: show GPS status"
    command = ["/usr/bin/python", "../tests/test_gps.py", "--terse"]
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    status = process.wait()
    message = process.stdout.read().decode('utf-8')
    messages = message.split('\n')
    if status == 0:
        return True, messages
    else:
        return False, messages

def set_shellhub_access(access='always'):
    """Update the shellhub docker status and restart configuration
    param str access: set to always [default], session [until next reboot or failure], or disable'
    """
    if access == 'always':
        status1 = os.system("/usr/bin/sudo docker update --restart on-failure shellhub")
        status2 = os.system("/usr/bin/sudo docker start shellhub")
    elif access == 'session':
        status1 = os.system(f"/usr/bin/sudo docker start shellhub")
        status2 = 0
    elif access == 'disable':
        status1 = os.system(f"/usr/bin/sudo docker update --restart no shellhub")
        status2 = os.system(f"/usr/bin/sudo docker stop shellhub")
    if (status1 == 0) and (status2 ==0):
        return True, ["Remote assistance access updated"]
    else:
        return False, ["Failed to update remote assistance access"]

def run_export_test(force=False):
    "Show data upload status and optionally force bulk upload"
    if force:
        command = ["/usr/bin/python", "../tests/test_export.py", "--terse", "--force_upload", "-1"]
    else:
        command = ["/usr/bin/python", "../tests/test_export.py", "--terse"]
    print(command)
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    status = process.wait()
    print(status)
    message = process.stdout.read().decode('utf-8')
    print(message)
    messages = message.split('\n')
    if status == 0:
        return True, messages
    else:
        return False, messages

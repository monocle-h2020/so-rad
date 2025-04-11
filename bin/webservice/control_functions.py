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

def run_gps_test():
    "Run a system test: show GPS status"
    command = ["/usr/bin/python", "../tests/test_gps.py", "--terse"]
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    status = process.wait()
    message = process.stdout.read().decode('utf-8')
    messages = message.split('\n')
    if status == '0':
        return True, messages
    else:
        return False, messages

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
    if status == '0':
        return True, messages
    else:
        return False, messages

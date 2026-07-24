#!/usr/bin/python
"""
Interface with DJI drone via their payload SDK. Requires a pre-built c++ binary based on the PSDK sample library (for now, at least).
The PSDK interface logs to console, those expressions are captured here.

We may anticipate PSDK support to change without much notice, so no effort is made here to refine the messaging from the sample library.
Regular expressions may be edited to capture changed or additional messages.

The PSDK interface handles the following options when connected only over serial UART:
- flight controller subscription (read coordinates and tilt/pitch/roll, as well as x/y/z velocities) - this is what we need as metadata. Assume that with RTK connected, the information is more precise
- RTK message subscription. Not currently used, this is dumped to file and the RTK corrections are likely already passed to the flight controller. 
- Widget on Pilot app. This could be used to pass signals from/to the payload, such as start/stop data collection. Not yet used, but in the cards. 

author: stsi
June 2026
"""


import os
import sys
import subprocess
import time
import re
import json
from math import pi, sqrt, cos, sin, atan2, degrees
from numpy import deg2rad, rad2deg, arccos
import threading
import datetime
import logging
import selectors

# exe when called directly
defaultexe = '/home/sorad/dji-psdk-builds/current-build'
#defaultexe = '/home/sorad/dji-psdk-builds/demo-rtkfc-gps5hz-widget'
log = logging.getLogger('djigps')


class DJI_PSDK():
    """
    Parse communication over DJI PSDK connected over UART.
    Requires the PML serial hat for Hy-Fly payload, DJI e-port SDK, and pre-compiled PSDK library
    """

    def __init__(self, exe):
        # set executable location
        self.exe = ["stdbuf", "-oL", exe]

        # log updates to stdout
        self.display = False
        self.display_step = 1  # show every update by default

        # sdk checks
        self.policyok =   False
        self.appstarted = False
        self.gpssuccess = False

        # automatically refreshed from json inputs (strings)
        self.gps_date = None
        self.gps_time = None
        self.home_altitude = None
        self.quaternion_0 = None
        self.quaternion_1 = None
        self.quaternion_2 = None
        self.quaternion_3 = None
        self.velocity_x = None
        self.velocity_y = None
        self.velocity_z = None
        self.gps_x = None
        self.gps_y = None
        self.gps_z = None
        self.gps_fix = None
        self.nsat = None
        self.battery1_capacity = None
        self.battery1_voltage = None
        self.battery1_temperature = None
        self.battery2_capacity = None
        self.battery2_voltage = None
        self.battery2_temperature = None
        self.healthFlag = None
        self.pitch = None
        self.roll = None
        self.yaw = None
        self.timestamp_ms = None
        self.timestamp_us = None
        self.rtk_hfsl = None
        self.rtk_lat = None
        self.rtk_lon = None
        self.compass_x = None
        self.compass_y = None
        self.compass_z = None
        self.fused_lat = None
        self.fused_lon = None
        self.fused_alt = None
        self.altitude_barometer = None

        # interpreted fields
        # self.gps_time
        self.lat = None
        self.lon = None
        self.alt = None
        self.speed = None
        self.fix = None
        self.satellite_number = None
        self.alt_gps = None
        self.lat_gps = None
        self.lon_gps = None
        self.alt_rtk = None
        self.lat_rtk = None
        self.lon_rtk = None
        self.rtk_solution_code = None
        self.rtk_solution = None
        self.alt_from_home = None
        self.pos_mode = None
        self.heading = None
        self.tilt = None    # TODO calculate from pitch/roll/yaw
        self.datetime = None
        # still being read from regex
          # system messages and errors

        #widgets
        self.widgets = {}  # stores the state of each widget by widgetindex
        # map each widget index to a function (or use dummy function widgetdonothing
        self.widget1callback = self.set_do_radiometry  # mapped to radiometry start/stop switch
        self.widget2callback = self.widgetdonothing    # mapped to test button
        self.widget3callback = self.widgetdonothing    # not used
        self.widget4callback = self.widgetdonothing    # not used

        # switches to remember current state
        # parent process should call do_radiometry() in this class to receive the state
        self._do_radiometry = False

        # when to update everything
        self.positionupdateevent = False
        self.last_update = datetime.datetime.now()

        # threading
        self.read_interval = 0.05
        self.sleep_interval = 0.1
        self.started = False
        self.stop_monitor = False
        self.thread = None

    def __repr__(self):
        if self.datetime is None:
            msg =  f"DJI-GPS {self.last_update.isoformat()}\n"
        else:
            td = self.last_update - self.datetime
            tds = td.total_seconds()
            msg =  f"DJI-GPS {self.last_update.isoformat()} Aircraft time: {self.datetime.isoformat()} Diff = {tds}\n"

        msg += f"\t\t\t\t\t\tGPS   lat: {self.lat_gps} lon: {self.lon_gps} speed: {self.speed} Alt: {self.alt_gps} nsat: {self.satellite_number} fix: {self.fix}\n"
        msg += f"\t\t\t\t\t\tRTK   lat: {self.lat_rtk} lon: {self.lon_rtk} Alt: {self.alt_rtk} | Solution: {self.rtk_solution_code}\n"
        msg += f"\t\t\t\t\t\tTilt     : {self.tilt}  pitch: {self.pitch}  roll: {self.roll} yaw: {self.yaw}\n"
        msg += f"\t\t\t\t\t\tAltitude {self.alt}, {self.alt_from_home} m from home altitude\n"
        msg += f"\t\t\t\t\t\tHeading {self.heading} \n"

        return msg


    def start(self):
        """
        Starts serial reading threads.
        """
        if not self.started:
            self.stop_monitor = False
            self.started = True
            self.thread = threading.Thread(target=self.run)
            #self.thread.daemon = True
            self.thread.start()
            log.info(f"Started DJIGPS manager")
        else:
            log.warn("Could not start DJIGPS manager")

    def stop(self):
        """
        Tells the serial threads to stop.
        """
        log.info("Stopping DJIGPS manager")
        self.stop_monitor = True
        time.sleep(2*self.sleep_interval)
        log.info(self.thread)
        self.thread.join(2*self.sleep_interval)
        log.info(f"DJIGPS manager running = {self.thread.is_alive()}")
        self.started = False

    def __del__(self):
        self.stop()

    def run(self):
        """
        Call dji code to connect to drone and start piping output.
        First outputs will include system and connectivitiy information.
        SIGTERM will give graceful exit.
        Drone Pilot app will be able to see the payload connected. In future we can define a widget to pass information (e.g. start/stop)
        """

        #popen = subprocess.Popen(self.exe, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
        #while not self.stop_monitor:
        #    line = popen.stdout.readline()

        # use selector to poll the subprocess for output without locking in - prevent high CPU usage
        popen = subprocess.Popen(self.exe, stdout=subprocess.PIPE, text=True)
        sel = selectors.DefaultSelector()
        sel.register(popen.stdout, selectors.EVENT_READ)

        try:
            step = 0
            while (popen.poll() is None) and (not self.stop_monitor):
                events = sel.select(timeout=self.read_interval) # Blocks until data is ready or timeout passes
                for key, _ in events:
                    line = key.fileobj.readline()
                    log.debug(line)
                    self.parse_line(line)

                    # control the frequency of console logging
                    if (self.display) and step == 0:
                        log.info(self)
                        step += 1
                    elif step == self.display_step:
                        step = 0
                    else:
                        log.debug(f"Waiting for data: app started {self.appstarted}, gps subscription {self.gpssuccess}, policy updated {self.policyok}")


        except KeyboardInterrupt:
            log.info(f"Stopping")
            self.stop()

        popen.stdout.close()
        return_code = popen.wait()
        if return_code:
            raise subprocess.CalledProcessError(return_code, cmd=self.exe)

    def parse_line(self, line):
        # parse line, looking for json otherwise try regex library
        pattern = r"\s*(?P<stamp>\d*.\d*)\s*(?P<process>\w*)\s*(?P<loglevel>.\w*.)\s*(?P<function>\w*.[cp]*:\d*)\s*(?P<message>[\x00-\x7F]+)"
        m = re.search(pattern, line)
        if m:
            message = m.group("message")
            func = m.group("function")
            log.debug(message)
            if ("{" in message) and ("}" in message):
                log.debug(f"Might be json: {message}")
                self.parse_json(func, message)
            else:
                self.parse_regex(line)  # this will parse the whole line not just the extracted message
        else:
            if len(line.strip())>2:
                log.info(f"Line not matched for parsing: {line}")

    def parse_json(self, func, message):
        """
        parse lines formatted as json
        e.g.   65.220                    user        [Info]  test_widget_interaction.c:572  {"widgetType":"Button","widgetIndex":4,"widgetValue":1}
        """
        startind = message.find("{")
        endind = message.find("}")
        try:
            d = json.loads(message[startind:endind+1])
        except json.decoder.JSONDecodeError:
            log.warning(f"Could not decode: {message}")
            return
        except Exception as err:
            log.exception("Unhandled json error")
            return

        if 'widget' in func:
            # special case: button press on controller means we need to call something
            index = d['widgetIndex']
            value = d['widgetValue']
            self.widgets[index] = value
            self.do_widget_action(index, value)
            return

        # if the symbol is a part of this class we'll update its value
        positionupdate = False
        for key, value in d.items():
            if key in self.__dict__.keys() and not callable(getattr(self, key)):
                setattr(self, key, value)
                log.debug(f"{key} was updated to {getattr(self,key)} by {func}")
                if key in ['gps_x', 'rtk_lon']:
                    log.debug("Received gps/rtk position data")
                    positionupdate = True
            else:
                log.warning(f"received {key} from {func} but this attribute is not known")

        if 'rtk_solution' in d.keys():
            self.rtk_solution_code = d['rtk_solution']
            self.rtk_solution = {
                              0: "DJI_FC_SUBSCRIPTION_POSITION_SOLUTION_PROPERTY_NOT_AVAILABLE",
                              1: "DJI_FC_SUBSCRIPTION_POSITION_SOLUTION_PROPERTY_FIX_POSITION (Position has been fixed by the FIX POSITION command.)",
                              2: "DJI_FC_SUBSCRIPTION_POSITION_SOLUTION_PROPERTY_FIX_HEIGHT_AUTO (Position has been fixed by the FIX HEIGHT/AUTO command)",
                              8: "DJI_FC_SUBSCRIPTION_POSITION_SOLUTION_PROPERTY_INSTANTANEOUS_DOPPLER_COMPUTE_VELOCITY (Velocity computed using instantaneous Doppler)",
                             16: "DJI_FC_SUBSCRIPTION_POSITION_SOLUTION_PROPERTY_SINGLE_PNT_SOLUTION (Single point position solution)",
                             17: "DJI_FC_SUBSCRIPTION_POSITION_SOLUTION_PROPERTY_PSEUDORANGE_DIFFERENTIAL_SOLUTION (Pseudorange differential solution)",
                             18: "DJI_FC_SUBSCRIPTION_POSITION_SOLUTION_PROPERTY_SBAS_CORRECTION_CALCULATED (Solution calculated using corrections from an SBAS)",
                             19: "DJI_FC_SUBSCRIPTION_POSITION_SOLUTION_PROPERTY_KALMAN_FILTER_WITHOUT_OBSERVATION_PROPAGATED (Propagated by a Kalman filter without new observations)",
                             20: "DJI_FC_SUBSCRIPTION_POSITION_SOLUTION_PROPERTY_OMNISTAR_VBS_POSITION (OmniSTAR VBS position (L1 sub-metre)",
                             32: "DJI_FC_SUBSCRIPTION_POSITION_SOLUTION_PROPERTY_FLOAT_L1_AMBIGUITY (Floating L1 ambiguity solution)",
                             33: "DJI_FC_SUBSCRIPTION_POSITION_SOLUTION_PROPERTY_FLOAT_IONOSPHERIC_FREE_AMBIGUITY (Floating ionospheric-free ambiguity solution)",
                             34: "DJI_FC_SUBSCRIPTION_POSITION_SOLUTION_PROPERTY_FLOAT_SOLUTION (Float position solution)",
                             48: "DJI_FC_SUBSCRIPTION_POSITION_SOLUTION_PROPERTY_L1_AMBIGUITY_INT (Integer L1 ambiguity solution)",
                             49: "DJI_FC_SUBSCRIPTION_POSITION_SOLUTION_PROPERTY_WIDE_LANE_AMBIGUITY_INT (Integer wide-lane ambiguity solution)",
                             50: "DJI_FC_SUBSCRIPTION_POSITION_SOLUTION_PROPERTY_NARROW_INT (Narrow fixed point position solution)"
                         }[int(self.rtk_solution_code)]

        if positionupdate:
            if self.appstarted and self.gpssuccess and self.policyok:
                try:
                    self.update_all()
                except Exception as msg:
                    log.exception(msg)


    def widgetdonothing(self):
        log.info("A widget was used but no action is mapped to it")
        return

    def set_do_radiometry(self):
        # switch state of startradiometry attribute. A parent function may look at this to determine action.
        self._do_radiometry = not self._do_radiometry
        log.info(f"A widget changed the state of do_radiometry to {self.do_radiometry()}")

    def do_radiometry(self):
        "Report state of self._do_radiometry"
        return self._do_radiometry

    def parse_regex(self, line):
        # use regex library
        parsed = False
        m = None
        for key, pattern in regexes.items():
            m = re.search(pattern, line)
            if m:
                try:
                    # system messages
                    if key == 'sdkversion_message':
                        sdkversion = m.group('sdkversion')
                        parsed = True
                    elif key ==  'sdk_policy_updated':
                        self.policyok = True
                        parsed = True
                    elif key ==  'sdk_appstart2':
                        self.appstarted = True
                        parsed = True
                    elif key ==  'sdk_gpsdatasuccess':
                        self.gpssuccess = True
                        parsed = True

                    elif key in ['sdk_chmod_message',
                                 'sdk_port_message',
                                 'sdk_policy_updating',
                                 'sdk_policy_updated',
                                 'sdk_aircraft_message',
                                 'sdk_packetlength',
                                 'sdk_appstart1',
                                 'sdk_appstart2',
                                 'sdk_rtkstart',
                                 'sdk_fcsubscribe',
                                 'sdk_fcsample',
                                 'sdk_fcinit',
                                 'sdk_fcquatvelgps',
                                 'sdk_gpsdatasuccess',
                                 'sdk_gpstimesubscribesuccess'
                                ]:
                        parsed = True

                    elif key == 'aircraft_message':
                        aircraft = m.group('aircraft')
                        parsed = True
                    elif key == 'sdk_baudrate':
                        baudrate = m.group('baudrate')
                        parsed = True
                    elif key == 'sdk_aircraft_message2':
                        aircrafttype = m.group('aircrafttype')
                        mountposition = m.group('mountposition')
                        sdkAptapterType = m.group('sdkadaptertype')
                        parsed = True
                    elif key == 'sdk_alias':
                        appalias = m.group('alias')
                        parsed = True
                    elif key == 'sdk_widgetfile':
                        self.widgetfile = m.group('widgetfile')
                        log.info(self.widgetfile)
                        parsed = True
                    elif key == 'sdk_rtcm_aircraft':
                        # likely spammy
                        log.debug("Received rtcm data")
                        parsed = True

                    else:
                        log.info(f"{key} recognised but not sure what to do")
                        parsed = True

                except Exception as err:
                    log.info(f"Unable to parse {key} information: {err}")

        if not parsed:
            log.info(f"Unparsed message: {line}")

    def update_all(self):
        self.update_position_gps()
        self.update_position_rtk()
        self.update_fused_position()
        self.update_speed()
        self.update_timestamp()
        self.update_compass()

    def update_compass(self):
        """
        """
        if None in [self.pitch, self.roll, self.yaw, self.compass_x, self.compass_y, self.compass_z]:
            self.heading = None
            self.tilt = None
            return

        pitch = self.pitch
        roll = self.roll

        # tilt from pitch/roll
        tilt = arccos(cos(deg2rad(roll)) * cos(deg2rad(pitch)))
        self.tilt = rad2deg(tilt)

        mx = self.compass_x
        my = self.compass_y
        mz = self.compass_z
        declination_deg = 0  # not currently used

        # magnetometer readings -> horizontal plane
        xh = (mx * cos(pitch) + my * sin(roll) * sin(pitch) + mz * cos(roll) * sin(pitch))

        yh = (my * cos(roll) - mz * sin(roll))

        heading_deg = degrees(atan2(yh, xh))
        heading_deg += declination_deg
        self.heading = heading_deg % 360


    def update_timestamp(self):
        """parse gps_time and gps_date fields"""
        if None in [self.gps_time, self.gps_date, self.timestamp_us, self.timestamp_ms]:
            self.datetime = None
            return

        if self.timestamp_us > 0:
            try:
                ts_us = f"{int(str(self.timestamp_us)[0:6]):06d}"
                self.datetime = datetime.datetime.strptime(f"{self.gps_date}{self.gps_time}.{ts_us}",
                                                                   "%Y%m%d%H%M%S.%f")
            except ValueError:
                self.datetime = None
            except Exception:
                raise

    def update_position_gps(self):
        """
        DJI PSDK returns latitude/longitude/altitude in degrees / m
        e.g. -41472367.0, 503663380.0 85925.0
        Latitude in Decimal Degrees = x/10^7  * 180/pi
        Longitude in Decimal Degrees = y/10^7  * 180/pi
        """
        if self.gps_fix is not None:
            self.fix = int(self.gps_fix)

        if None in [self.gps_x, self.gps_y, self.gps_z, self.gps_fix, self.nsat]:
            self.lat_gps, self.lon_gps, self.alt_gps = None, None, None
            return

        self.satellite_number = int(self.nsat)
        self.lat_gps = float(self.gps_x)/10**7
        self.lon_gps = float(self.gps_y)/10**7
        self.alt_gps = float(self.gps_z)/10**3
        self.last_update = datetime.datetime.now()

    def update_position_rtk(self):
        """
        DJI PSDK returns latitude/longitude/altitude in degrees / m
        e.g. -41472367.0, 503663380.0 85925.0
        Latitude in Decimal Degrees = x/10^7  * 180/pi
        Longitude in Decimal Degrees = y/10^7  * 180/pi
        """
        if None in [self.rtk_lat, self.rtk_lon, self.rtk_hfsl]:
            self.lat_rtk, self.lon_rtk, self.alt_rtk = None, None, None
            return

        self.lat_rtk = float(self.rtk_lat)
        self.lon_rtk = float(self.rtk_lon)
        self.alt_rtk = float(self.rtk_hfsl)
        self.last_update = datetime.datetime.now()

    def update_fused_position(self):
        """
        Decide which positioning info to use
        """
        if self.altitude_barometer is not None:
            self.alt = float(self.altitude_barometer)
            self.alt_from_home = self.alt - float(self.home_altitude)
        else:
            self.alt = None
            self.alt_from_home = None

        if (self.rtk_solution_code is not None) and (self.rtk_solution_code >= 16):
            self.lat = self.lat_rtk
            self.lon = self.lon_rtk
            self.pos_mode = 'rtk'
        elif (self.fix is not None) and (self.fix >= 3):
            self.lat = self.lat_gps
            self.lon = self.lon_gps
            self.pos_mode = 'gps'
        else:
            self.lat, self.lon = None, None
            self.pos_mode = None

    def update_speed(self):
        """
        Calculate horizontal speed component from velocity vector
        """
        if None in [self.velocity_x, self.velocity_y, self.velocity_z]:
            return

        vx, vy, vz = self.velocity_x, self.velocity_y, self.velocity_z
        self.speed = sqrt((vx * vx) + (vy * vy))
        self.last_update = datetime.datetime.now()

    def do_widget_action(self, index, value):
        log.info(f"Received widget {index} value {value}")
        if index == 1:
            self.widget1callback()
        elif index == 2:
            self.widget2callback()
        elif index == 3:
            self.widget3callback()
        elif index == 4:
            self.widget4callback()

#
#Unparsed line:    3.327             auth        [Warn]      dji_identity_verify.c:515  request upload policy file failed

regexes = {
          'battery':
            r"\s*(?P<stamp>\d*.\d*)\s*(?P<process>\w*)\s*(?P<loglevel>.\w*.)\s*(?P<function>\w*..:\d*)\s*battery single info index(?P<battery_index>\d): capacity percent = (?P<battery_percent>\d*)% voltage = (?P<battery_voltage>\d*)V temperature = (?P<battery_temperature>\d*.\d*) degree.",
          'quaternion':
            r"\s*(?P<stamp>\d*.\d*)\s*(?P<process>\w*)\s*(?P<loglevel>.\w*.)\s*(?P<function>\w*.c:\d*)\s*quaternion:\s*(?P<quat1>[+-?]\d*.\d*)\s*(?P<quat2>[+-?]\d*.\d*)\s*(?P<quat3>[+-?]\d*.\d*)\s*(?P<quat4>[+-?]\d*.\d*).",
          'euler':
            r"\s*(?P<stamp>\d*.\d*)\s*(?P<process>\w*)\s*(?P<loglevel>.\w*.)\s*(?P<function>\w*.c:\d*)\s*euler angles: pitch =\s*(?P<pitch>[+-?]\d*.\d*)\s*roll =\s*(?P<roll>[+-?]\d*.\d*)\s*yaw =\s*(?P<yaw>[+-?]\d*.\d*).",
          'velocity':
            r"\s*(?P<stamp>\d*.\d*)\s*(?P<process>\w*)\s*(?P<loglevel>.\w*.)\s*(?P<function>\w*.c:\d*)\s*velocity: x =\s*(?P<x>[+-?]\d*.\d*)\s*y =\s*(?P<y>[+-?]\d*.\d*)\s*z =\s*(?P<z>[+-?]\d*.\d*)\s*healthFlag =\s*(?P<healthFlag>\d*), timestamp ms =\s*(?P<timestamp_ms>[+-?]\d*)\s*us =\s*(?P<timestamp_us>[+-?]\d*).",
          'gps':
           r"\s*(?P<stamp>\d*.\d*)\s*(?P<process>\w*)\s*(?P<loglevel>.\w*.)\s*(?P<function>\w*.c:\d*)\s*gps position: x =\s*(?P<x>[+-?]\d*.\d*)\s*y =\s*(?P<y>[+-?]\d*.\d*)\s*z =\s*(?P<z>[+-?]\d*.\d*).",
          'gpshr':
           r"\s*(?P<stamp>\d*.\d*)\s*(?P<process>\w*)\s*(?P<loglevel>.\w*.)\s*(?P<function>\w*.c:\d*)\s*gps time =\s*(?P<gpshr>\d*)",
          'gpsdate':
           r"\s*(?P<stamp>\d*.\d*)\s*(?P<process>\w*)\s*(?P<loglevel>.\w*.)\s*(?P<function>\w*.c:\d*)\s*gps date =\s*(?P<gpsdate>\d*)",
          'gpsmsus':
           r"\s*(?P<stamp>\d*.\d*)\s*(?P<process>\w*)\s*(?P<loglevel>.\w*.)\s*(?P<function>\w*.c:\d*)\s*timestamp: millisecond\s*(?P<gpsms>\d*)\s*microsecond\s*(?P<gpsus>\d*).",
          'gpsdetail':
           r"\s*(?P<stamp>\d*.\d*)\s*(?P<process>\w*)\s*(?P<loglevel>.\w*.)\s*(?P<function>\w*.[cp]*:\d*)\s*gps detail: fix =\s*(?P<gpsfix>\d*),\s*nsat =\s*(?P<nsat>[+-?]\d*)",
          'sdkversion_message':
           r"\s*(?P<stamp>\d*.\d*)\s*(?P<process>\w*)\s*(?P<loglevel>.\w*.)\s*(?P<function>\w*.c:\d*)\s*Payload SDK Version : (?P<sdkversion>c*)",
          'sdk_chmod_message':
           r"chmod: changing permissions of '\/dev\/(?P<serialdevice>[tyUSB0-9]*)':\s*Operation not permitted",
          'sdk_port_message':
           r"\s*(?P<stamp>\d*.\d*)\s*(?P<process>\w*)\s*(?P<loglevel>.\w*.)\s*(?P<function>\w*.c:\d*)\s*Identify mount position type is Extension Port Type",
          'sdk_aircraft_message':
           r"\s*(?P<stamp>\d*.\d*)\s*(?P<process>\w*)\s*(?P<loglevel>.\w*.)\s*(?P<function>\w*.c:\d*)\s*Identify aircraft series is (?P<aircraft>[a-zA-z0-9\s]*)",
          'sdk_baudrate':
           r"\s*(?P<stamp>\d*.\d*)\s*(?P<process>\w*)\s*(?P<loglevel>.\w*.)\s*(?P<function>\w*.c:\d*)\s*Identi[tf]y uart0 baudrate is (?P<baudrate>\d*)\s*bps",
          'sdk_policy_updating':
           r"\s*(?P<stamp>\d*.\d*)\s*(?P<process>\w*)\s*(?P<loglevel>.\w*.)\s*(?P<function>\w*.c:\d*)\s*Updating dji sdk policy file...",
          'sdk_policy_updated':
           r"\s*(?P<stamp>\d*.\d*)\s*(?P<process>\w*)\s*(?P<loglevel>.\w*.)\s*(?P<function>\w*.c:\d*)\s*Update dji sdk policy file successfully",
          'sdk_aircraft_message2':
           r"\s*(?P<stamp>\d*.\d*)\s*(?P<process>\w*)\s*(?P<loglevel>.\w*.)\s*(?P<function>\w*.c:\d*)\s*Identify AircraftType = (?P<aircrafttype>[^,]*), MountPosition = (?P<mountposition>[^,]*), SdkAdapterType = (?P<sdkadaptertype>\w*)",
          'sdk_alias':
           r"\s*(?P<stamp>\d*.\d*)\s*(?P<process>\w*)\s*(?P<loglevel>.\w*.)\s*(?P<function>\w*.c:\d*)\s*Set alias: (?P<alias>[a-zA-Z0-9-_]*)",
          'sdk_packetlength':
           r"\s*(?P<stamp>\d*.\d*)\s*(?P<process>\w*)\s*(?P<loglevel>.\w*.)\s*(?P<function>\w*.c:\d*)\s*s_downloaderPackDataLength using default = (?P<packetlength>\d*)",
          'sdk_widgetfile':
           r"\s*(?P<stamp>\d*.\d*)\s*(?P<process>\w*)\s*(?P<loglevel>.\w*.)\s*(?P<function>\w*.c:\d*)\s*widget file: (?P<widgetfile>[a-zA-Z\\\/_-]*)",
          'sdk_appstart1':
           r"\s*(?P<stamp>\d*.\d*)\s*(?P<process>\w*)\s*(?P<loglevel>.\w*.)\s*(?P<function>\w*.c:\d*)\s*Start dji sdk application",
          'sdk_appstart2':
           r"\s*(?P<stamp>\d*.\d*)\s*(?P<process>\w*)\s*(?P<loglevel>.\w*.)\s*(?P<function>\w*.[cp]*:\d*)\s*Application start.",
          'sdk_rtkstart':
           r"\s*(?P<stamp>\d*.\d*)\s*(?P<process>\w*)\s*(?P<loglevel>.\w*.)\s*(?P<function>\w*.[cp]*:\d*)\s*Start RTK Positioning cycle",
          'sdk_fcsubscribe':
           r"\s*(?P<stamp>\d*.\d*)\s*(?P<process>\w*)\s*(?P<loglevel>.\w*.)\s*(?P<function>\w*.[cp]*:\d*)\s*Start FcSubscription cycle",
          'sdk_fcsample':
           r"\s*(?P<stamp>\d*.\d*)\s*(?P<process>\w*)\s*(?P<loglevel>.\w*.)\s*(?P<function>\w*.c:\d*)\s*Fc subscription sample start",
          'sdk_fcinit':
           r"\s*(?P<stamp>\d*.\d*)\s*(?P<process>\w*)\s*(?P<loglevel>.\w*.)\s*(?P<function>\w*.c:\d*)\s*--> Step 1: Init fc subscription module",
          'sdk_fcquatvelgps':
           r"\s*(?P<stamp>\d*.\d*)\s*(?P<process>\w*)\s*(?P<loglevel>.\w*.)\s*(?P<function>\w*.c:\d*)\s*--> Step 2: Subscribe the topics of quaternion, velocity and gps position",
          'sdk_gpstimesubscribesuccess':
           r"\s*(?P<stamp>\d*.\d*)\s*(?P<process>\w*)\s*(?P<loglevel>.\w*.)\s*(?P<function>\w*.c:\d*)\s*Subscribe topic gpstimes success.",
          'sdk_gpsdatasuccess':
           r"\s*(?P<stamp>\d*.\d*)\s*(?P<process>\w*)\s*(?P<loglevel>.\w*.)\s*(?P<function>\w*.c:\d*)\s*Subscribe topic gpsdata success.",
          'sdk_rtcm_aircraft':
           r"\s*(?P<stamp>\d*.\d*)\s*(?P<process>\w*)\s*(?P<loglevel>.\w*.)\s*(?P<function>\w*.c:\d*)\s*Receive rtcm data from rtk on aircraft, index: \d, len: \d*",
          'rtkpos':
           r"\s*(?P<stamp>\d*.\d*)\s*(?P<process>\w*)\s*(?P<loglevel>.\w*.)\s*(?P<function>\w*.c:\d*)\s*rtk position: x =\s*(?P<x>[+-?]\d*.\d*)\s*y =\s*(?P<y>[+-?]\d*.\d*)\s*z =\s*(?P<z>[+-?]\d*.\d*).",
          'rtksolinfo':
           r"\s*(?P<stamp>\d*.\d*)\s*(?P<process>\w*)\s*(?P<loglevel>.\w*.)\s*(?P<function>\w*.c:\d*)\s*rtk solution:\s*(?P<rtk_solution_code>\d*)",
          'rtkconnection':
           r"\s*(?P<stamp>\d*.\d*)\s*(?P<process>\w*)\s*(?P<loglevel>.\w*.)\s*(?P<function>\w*.c:\d*)\s*rtk connection:\s*(?P<rtk_connection>\d*)",
          'homealtitude':
           r"\s*(?P<stamp>\d*.\d*)\s*(?P<process>\w*)\s*(?P<loglevel>.\w*.)\s*(?P<function>\w*.c:\d*)\s*altitude of homepoint:\s*(?P<home_altitude>[+-?]\d*.\d*)"
          }

# when no ttyUSB is available we get:
#   0.118                 adapter        [Error]      dji_access_adapter.c:302  DjiAccessAdapter_IsUartConnect, returnCode = 236
#   0.118                    core        [Error]                dji_core.c:191  Access adapter init error, stat:236

# more errors we can get
# 0.154                   utils        [Error]                dji_msgq.c:208  lock send mutex failed
#   0.154                  linker        [Error]              dji_linker.c:309  send msg to queue error
# malloc(): unaligned tcache chunk detected


if __name__ == '__main__':
    # set up logger
    myFormat = '%(asctime)s | %(name)s | %(levelname)s | %(message)s'
    formatter = logging.Formatter(myFormat)
    logging.basicConfig(level='INFO', format=myFormat, stream=sys.stdout)
    log = logging.getLogger()
    log.setLevel('INFO')

    dji_gps = DJI_PSDK(exe=defaultexe)
    # display state at every update, default = False
    dji_gps.display = True
    # if display = True, show only every nth update
    dji_gps.display_step = 1
    dji_gps.start()

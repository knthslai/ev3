#!/usr/bin/env pybricks-micropython

#  This file is part of ev3 repository. See <https://github.com/hugbug/ev3>.
#
#  This program is free software; you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation; either version 2 of the License, or
#  (at your option) any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with this program.  If not, see <http://www.gnu.org/licenses/>.

from pybricks.ev3devices import (Motor)
from pybricks.parameters import (Port, SoundFile, Stop)
from pybricks import ev3brick as brick
from pybricks.tools import print
import time
import struct
import sys
import random
import uselect

random.seed(0)

# Defining stick dead zone which is a minimum amount of stick movement
# from the center position to start motors.
stick_deadzone = 5  # deadzone 5%

# Max steering angle for steering motor (in degrees) initialized here for debug purposes,
# it will be computed and adjusted automatically druing motor calibratation process.
max_steering_angle = 300

# One of these can be disabled if you have connected both gamepads and want to use a particular one.
enable_xbox_detection = True
enable_ps_detection = True

# Constants
gamepad_xbox = 1
gamepad_ps = 2

# Initialize variables. 
# Assuming sticks are in the middle and triggers are not pressed when starting
gear = 1
power_pos = 0
bump_factor = 0
steering_pos = 0

gamepad_device = None
gamepad_type = 0 # gamepad_xbox or gamepad_ps
# True if Xbox or False if PlayStation
xbox = None

# Use event polling instead of blocking read (this feature is currently in testing)
use_polls = False

# long int, long int, unsigned short, unsigned short, long int
event_format = 'llHHl'
event_size = struct.calcsize(event_format)

# Clear program title
brick.display.clear()
brick.display.text("Rov3r+", (60, 20))

# Declare motors and check their connections
try:
    first_motor = Motor(Port.A)
    second_motor = Motor(Port.D)
    steering_motor = Motor(Port.B)
    gearbox_motor = Motor(Port.C)
except:
    brick.display.text("Check motor cables", (0, 80))
    brick.sound.file(SoundFile.ERROR_ALARM)
    time.sleep(10)
    sys.exit(1)

def find_gamepad():
    """
    Checks device list by reading content of virtual file "/proc/bus/input/devices"
    looking for gamepad device.
    """
    global gamepad_type
    with open("/proc/bus/input/devices", "r") as fp:
        line = fp.readline()
        while line:
            if enable_xbox_detection and line.startswith("N: Name=") and line.find("Xbox") > -1:
                gamepad_type = gamepad_xbox
            if enable_ps_detection and line.startswith("N: Name=") and line.find("PLAYSTATION") > -1 and line.find("Motion") == -1:
                gamepad_type = gamepad_ps
            if gamepad_type > 0 and line.startswith("H: Handlers="):
                line = line[len("H: Handlers="):]
                pb = line.find("event")
                pe = line.find(" ", pb)
                return line[pb:pe]
            line = fp.readline()
    return None

def transform_stick(value):
    """
    Transform range 0..max to -100..100, remove deadzone from the range
    """
    max = 65535 if xbox else 255
    half = int((max + 1) / 2)
    deadzone = int((max + 1) / 100 * stick_deadzone)
    value -= half
    if abs(value) < deadzone:
        value = 0
    elif value > 0:
        value = (value - deadzone - 1) / (half - deadzone) * 100
    else:
        value = (value + deadzone) / (half - deadzone) * 100
    return value

def play_horn():
    """
    Plays a horn sound randomly selected from two available sounds
    """
    if random.randint(1, 2) == 1:
        brick.sound.file(SoundFile.HORN_1)
    else:
        brick.sound.file(SoundFile.HORN_2)

def play_sound_effect():
    """
    Plays a random sound effect
    """
    effect = random.randint(1, 4)
    if effect == 1:
        brick.sound.file(SoundFile.AIR_RELEASE)
    elif effect == 2:
        brick.sound.file(SoundFile.AIRBRAKE)
    elif effect == 3:
        brick.sound.file(SoundFile.LASER)
    elif effect == 4:
        brick.sound.file(SoundFile.SONAR)

def calibrate_motors():
    """
    Calibrate gearbox motor: switch to first gear.
    Calibrate steering motor: find the range by steering full to the left and full to the right,
    then center the steering.
    """
    global max_steering_angle

    gearbox_motor.run_until_stalled(360, Stop.COAST, 50)
    gearbox_motor.run_angle(100, -20) # unstress the switcher
    gearbox_motor.reset_angle(0)

    steering_motor.run_until_stalled(360, Stop.COAST, 80)
    steering_motor.reset_angle(0)
    steering_motor.run_until_stalled(-360, Stop.COAST, 80)
    max_steering_angle = abs(steering_motor.angle()) / 2
    steering_motor.run_target(360, -max_steering_angle)
    steering_motor.reset_angle(0)
    max_steering_angle *= 0.90  # limit max steering angle a little

def print_help():
    brick.display.text(("Xbox" if xbox else "PS") + " gamepad functions:", (0, 40))
    brick.display.text("Left Stick: movement", (0, 55))
    brick.display.text(("RB/LB" if xbox else "R1/L1") + ": gear up/down", (0, 65))
    brick.display.text(("RT" if xbox else "R2") + ": steer. speed bump", (0, 75))
    brick.display.text(("X" if xbox else "/\\") + ": horn", (0, 85))
    brick.display.text(("Y" if xbox else "[]") + ": sound effect", (0, 95))

def drive(_power_pos, _bump_factor):
    global power_pos, bump_factor
    if _power_pos == None:
        _power_pos = power_pos
    if _bump_factor == None:
        _bump_factor = bump_factor
    if power_pos != _power_pos or bump_factor != _bump_factor:
        power_pos = _power_pos
        bump_factor = _bump_factor
        propulsion_power = power_pos * (1 + bump_factor)    
        first_motor.dc(propulsion_power)
        second_motor.dc(propulsion_power)

def steer(_steering_pos):
    global steering_pos
    if steering_pos != _steering_pos:
        steering_pos = _steering_pos
        steering_angle = - steering_pos * max_steering_angle / 100
        steering_motor.track_target(steering_angle)

def switch_gear(_gear):
    global gear
    if gear != _gear:
        gear = _gear
        gearing_angle = - (gear - 1) * 20 / 12 * 90
        gearbox_motor.track_target(gearing_angle)

def process_gamepad_event(in_file):
    global use_polls

    # Read from the file
    event = in_file.read(event_size)

    (tv_sec, tv_usec, ev_type, code, value) = struct.unpack(event_format, event)

    if ev_type == 3 or ev_type == 1:

        if ev_type == 3 and code == 0: # Left Stick Horz. Axis
            steer(transform_stick(value))

        elif ev_type == 3 and code == 1: # Left Stick Vert. Axis
            drive(transform_stick(value), None)

        elif xbox and ev_type == 3 and code == 9: # Xbox Right Trigger
            drive(None, value / 1024)

        elif not xbox and ev_type == 3 and code == 5: # PS R2 paddle
            drive(None, value / 256)

        elif ev_type == 1 and code == 311 and value == 1: # RB pressed
            switch_gear(min(gear + 1, 4))

        elif ev_type == 1 and code == 310 and value == 1:  # LB pressed
            switch_gear(max(gear - 1, 1))

        elif ev_type == 1 and code == 307 and value == 1:  # X pressed
            play_horn()

        elif ev_type == 1 and code == 308 and value == 1:  # Y pressed
            play_sound_effect()

        elif ev_type == 1 and code == 315 and value == 1:  # menu pressed
            use_polls = not use_polls
            brick.sound.file(SoundFile.GREEN if use_polls else SoundFile.RED)

# Find the gamepad:
# /dev/input/event2 is the usual file handler for the gamepad.
# The contents of /proc/bus/input/devices lists all devices.
gamepad_device = find_gamepad()
xbox = gamepad_type == gamepad_xbox
#print("Gamepad device:", gamepad_device, ", type:", gamepad_type)

if gamepad_device is None:
    brick.display.text("Gamepad not found", (0, 80))
    brick.sound.file(SoundFile.ERROR_ALARM)
    time.sleep(10)
    sys.exit(1)

gamepad_infile_path = "/dev/input/" + gamepad_device
gamepad_infile = open(gamepad_infile_path, "rb")

print_help()

calibrate_motors()

event_selector = uselect.poll()
event_selector.register(gamepad_infile, uselect.POLLIN)

while True:
    if use_polls:
        events = event_selector.poll(0)
    if not use_polls or (len(events) > 0 and events[0][1] & uselect.POLLIN):
        process_gamepad_event(gamepad_infile)
    else:
        # Doing something else here...
        # This code is executed when there are no gamepad events to proceed.
        # Here we can check sensors and/or do some other work.
        # Currently we just sleep for 10ms. That makes the loop body to be executed
        # about 100 times per second. That's enough FPS for the gamepad control.
        # Reducing of the sleep time will increase FPS but also the CPU load
        # and power consumption.
        # When adding code for a useful work keep in mind, that during its
        # execution the gamepad events are not processed. Therefore the code
        # should not run too long or the gamepad becomes laggy.
        # Reduce or remove the sleep time if necessary.
        time.sleep(0.010)
        #brick.sound.beep()
        #print("Doing something else: ", time.time())

gamepad_infile.close() # will never executed actually, due to endless while loop
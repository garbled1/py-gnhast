# py-gnhast
Python module for gnhast

This module allows you to build sensor-only collectors for gnhast,
and script-type collectors for gnhast.  It implements most of the gnhast
protocol.

# Things that are missing:

* mod - Cannot handle a request to modify a device
* chg - Cannot handle a request to change a device
* groups - No device group support.

# Things that work
* Easy to write sensor collectors.
* Easy to write simple automation controls, for example, listen to a sensor, and then issue a command to gnhastd when something happens on that sensor.
* alarms and alarm callbacks

# Examples
* See the https://github.com/garbled1/gnhast-python-collectors repo for collectors written using this module.

# What is gnhast?

Gnhast is an event based home automation suite of tools.
It relies on a central daemon, which handles all the coordination of work,
and collectors which handle all the actual work.
Gnhast is designed to be run from a UNIX/Linux server,
and is designed to be fairly lightweight, so it could easily
be (and is!) deployed on a Raspbery PI to run your whole house.

See the main gnhast repo at: https://github.com/garbled1/gnhast

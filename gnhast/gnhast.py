#!/usr/bin/env python
"""
.. module:: gnhast
Gnhast
"""

import asyncio
from gnhast import confuseparse
from pprint import pprint
import time
from datetime import datetime
from pint import UnitRegistry
from flags import Flags
import shlex
import functools
import signal
import re
import copy
import sys

# Todo:
# This module currently only supports bare sensors, no mod/chg support yet

LOG_INFO = 0
LOG_ERROR = 1
LOG_WARNING = 2
LOG_DEBUG = 3


class AlarmChan(Flags):
    Generic = 1
    Power = 2
    Lights = 4
    Security = 8
    Weather = 16
    AC = 32
    Yard = 64
    Gnhast = 128
    System = 256
    Emergency = 512
    Messaging = 1024
    User1 = 16777216
    User2 = 33554432
    User3 = 67108864
    User4 = 134217728
    User5 = 268435456
    User6 = 536870912
    User7 = 1073741824
    User8 = 2147483648
    ALL = -1


class gnhast:
    """ The main gnhast class.
    """

    def __init__(self, loop, cfgfile):
        self.cfg = cfgfile
        # self.loop = asyncio.get_event_loop()
        self.loop = loop
        self.devices = []
        self.alarms = []
        self.arg_by_subt = ["none", "switch", "switch", "temp", "humid",
                            "count", "pres", "speed", "dir", "ph", "wet",
                            "hub", "lux", "volts", "wsec", "watt", "amps",
                            "rain", "weather", "alarm", "number", "pct",
                            "flow", "distance", "volume", "timer",
                            "thmode", "thstate", "smnum", "blind",
                            "collector", "trigger", "orp", "salinity",
                            "moonph", "tristate"]
        self.DEVICE = {
            'uid': '', 'loc': '', 'name': '', 'rrdname': '',
            'proto': 0, 'type': 0, 'subtype': 0,
            'scale': 0,
            'data': 0, 'last': 0, 'min': 0, 'max': 0, 'avg': 0,
            'lowat': 0, 'hiwat': 0, 'change': 0,
            'handler': 0, 'hargs': dict(),
            'localdata': None,
            'lastupd': 0,
            'spamhandler': 0
        }
        # Config file string translators
        self.cf_spamhandler = ['no', 'yes', 'onchange']
        self.cf_type = ['NONE', 'switch', 'dimmer', 'sensor', 'timer', 'blind']
        self.cf_subt = [
            'NONE', 'switch', 'outlet', 'temp', 'humid', 'counter',
            'pressure', 'windspeed', 'winddir', 'ph', 'wetness',
            'hub', 'lux', 'voltage', 'wattsec', 'watt', 'amps',
            'rainrate', 'weather', 'alarmstatus', 'number',
            'percentage', 'flowrate', 'distance', 'volume',
            'timer', 'thmode', 'thstate', 'smnumber', 'blind',
            'collector', 'trigger', 'orp', 'salinity', 'daylight',
            'moonph', 'tristate', 'bool']
        self.cf_tscale = ['f', 'c', 'k', 'r']
        self.cf_speedscale = ['mph', 'ms', 'kph', 'knots']
        self.cf_lengthscale = ['in', 'mm']
        self.cf_baroscale = ['in', 'mm', 'mb', 'cb']
        self.cf_lightscale = ['wm2', 'lux']
        self.cf_salinescale = ['ppt', 'sg', 'ms']

        self.collector_healthy = True
        self.debug = False
        self.writer = None
        self.reader = None
        self.log = sys.stderr

        self.ALARM = {
            'aluid': '',
            'alsev': 0,
            'alchan': AlarmChan.Generic,
            'altext': ''
        }
        self.coll_alarm_cb = None
        self.coll_upd_cb = None

    def parse_convert_to_int(self, value, ptype):
        """Convert a parsed string to it's correct type

        :param value: string value to convert
        :param ptype: self.cf_XXX type to use in conversion
        :returns: the integer value of the config option
        :rtype: int

        """
        if isinstance(value, int):
            return value
        try:
            nval = ptype.index(value.lower())
            return nval
        except ValueError:
            return -1

    def print_convert(self, key, val, outfile):
        if key == 'type':
            print('  ' + key + ' = ' + self.cf_type[val], file=outfile)
        elif key == 'subtype':
            print('  ' + key + ' = ' + self.cf_subt[val], file=outfile)
        elif key == 'tscale':
            print('  ' + key + ' = ' + self.cf_tscale[val], file=outfile)
        elif key == 'speedscale':
            print('  ' + key + ' = ' + self.cf_speedscale[val], file=outfile)
        elif key == 'lengthscale':
            print('  ' + key + ' = ' + self.cf_lengthscale[val], file=outfile)
        elif key == 'baroscale':
            print('  ' + key + ' = ' + self.cf_baroscale[val], file=outfile)
        elif key == 'lightscale':
            print('  ' + key + ' = ' + self.cf_lightscale[val], file=outfile)
        elif key == 'salinescale':
            print('  ' + key + ' = ' + self.cf_salinescale[val], file=outfile)
        elif isinstance(val, str):
            print('  ' + key + ' = ' + '"' + val + '"', file=outfile)
        else:
            print('  ' + key + ' = ' + str(val), file=outfile)

    def write_conf_file(self, conffile):
        """Write out a config file

        :param conffile: full path to config file to create
        :returns: None
        :rtype: None

        """
        if conffile == '':
            return
        f = open(conffile, 'w')

        # overwrite our config data with current data
        for dev in self.devices:
            self.config['devices'][dev['uid']] = dev

        for toplvl in self.config:
            if toplvl == 'devices':
                for dev in self.config[toplvl]:
                    print('device "' + self.config['devices'][dev]['uid'] + '" {', file=f)
                    for val in self.config['devices'][dev]:
                        if val != 'data' and val != 'avg' and val != 'min' \
                           and val != 'max' and val != 'lastupd' \
                           and val != 'last' and val != 'change':
                            self.print_convert(val, self.config['devices'][dev][val], f)
                    print('}', file=f)
            elif isinstance(self.config[toplvl], dict):
                print(toplvl + ' {', file=f)
                for part in self.config[toplvl]:
                    if isinstance(self.config[toplvl][part], str):
                        print('  ' + part + ' = "' + self.config[toplvl][part] + '"', file=f)
                    else:
                        print('  ' + part + ' = ' + str(self.config[toplvl][part]), file=f)
                print('}', file=f)
            else:
                if isinstance(self.config[toplvl], str):
                    print(toplvl + ' = "' + self.config[toplvl] + '"', file=f)
                else:
                    print(toplvl + ' = ' + str(self.config[toplvl]), file=f)
        f.close()

    def new_device(self, uid, name, type, subtype):
        """Create a new device and insert it to the device table

        :param uid: Device UID
        :param name: Device Name
        :param type: Device type (int)
        :param subtype: Device subtype (int)
        :returns: new device, appended to device list
        :rtype: dict

        """
        dev = copy.deepcopy(self.DEVICE)
        dev['name'] = name
        dev['type'] = type
        dev['uid'] = uid
        dev['subtype'] = subtype
        self.devices.append(dev)
        return dev

    def parse_cfg(self):
        """Parse a config file

        :returns: Configuration dict
        :rtype: dict

        """
        modcfg = ''
        with open(self.cfg, "r") as f:
            for line in f:
                x = line.rstrip()
                if not x.endswith('{') and not x == '':
                    x += ';'
                modcfg += x + '\n'
        try:
            self.config = confuseparse.parse(modcfg)
        except Exception as error:
            self.LOG_ERROR('{0}'.format(error))
            exit(1)

        # Now look for device-* entries and reform them
        self.config.update({'devices': dict()})
        devpat = re.compile("^device-(.*)")
        keylist = []
        for key, value in self.config.items():
            if devpat.match(key):
                m = devpat.match(key)
                self.config['devices'][m.group(1)] = value
                self.config['devices'][m.group(1)]['uid'] = m.group(1)
                # Now convert the entries
                x = self.config['devices'][m.group(1)]
                x['proto'] = 0
                x['type'] = self.parse_convert_to_int(x['type'], self.cf_type)
                if 'subtype' in x:
                    x['subtype'] = self.parse_convert_to_int(x['subtype'],
                                                             self.cf_subt)
                if 'tscale' in x:
                    x['tscale'] = self.parse_convert_to_int(x['tscale'],
                                                            self.cf_tscale)
                if 'speedscale' in x:
                    x['speedscale'] = self.parse_convert_to_int(x['speedscale'],
                                                                self.cf_speedscale)
                if 'lengthscale' in x:
                    x['lengthscale'] = self.parse_convert_to_int(x['lengthscale'],
                                                                 self.cf_lengthscale)
                if 'baroscale' in x:
                    x['baroscale'] = self.parse_convert_to_int(x['baroscale'],
                                                               self.cf_baroscale)
                if 'lightscale' in x:
                    x['lightscale'] = self.parse_convert_to_int(x['lightscale'],
                                                                self.cf_lightscale)
                if 'salinescale' in x:
                    x['salinescale'] = self.parse_convert_to_int(x['salinescale'],
                                                                 self.cf_salinescale)
                keylist.append(key)
                # While we are here, append them to the internal devices list
                self.devices.append(self.config['devices'][m.group(1)])

        for key in keylist:
            del self.config[key]

        # if self.debug:
        #     pprint(self.config)
        return self.config

    def gn_scale_temp(self, temp, curscale, newscale):
        """Rescale a temperature

        :param temp: current temp
        :param curscale: current scale (string or int)
        :param newscale: new scale (string or int)
        :returns: temperature in new scale
        :rtype: float

        """
        ureg = UnitRegistry()
        scaler = [ureg.degF, ureg.degC, ureg.kelvin, ureg.degR]
        scaler_to = ['degF',  'degC', 'kelvin', 'degR']
        Q_ = ureg.Quantity
        cur = self.parse_convert_to_int(curscale, self.cf_tscale)
        new = self.parse_convert_to_int(newscale, self.cf_tscale)

        temp_s = Q_(temp, scaler[cur])
        return temp_s.to(scaler_to[new])

    def word_to_dev(self, device, cmdword):
        """Convert a gnhast protocol command word to data and store in device

        :param device: device to store data in
        :param cmdword: word to parse
        :returns: nothing
        :rtype:

        """
        # take a string like devt:1 and import it to a device
        data = cmdword.split(':')
        vwords = ['uid', 'name', 'rate', 'rrdname', 'devt', 'proto',
                  'subt', 'client', 'scale', 'handler', 'hargs',
                  'glist', 'dlist', 'collector', 'alsev', 'altext',
                  'aluid', 'alchan', 'spamhandler']

        if data[0] in self.arg_by_subt:
            data[0] = 'data'

        if data[0] not in vwords:
            self.LOG_WARNING("Unhandled word: {0}".format(data[0]))
            return

        # Patch the words up a little
        if data[0] == 'subt':
            data[0] = 'subtype'
        if data[0] == 'devt':
            data[0] = 'type'

        # save our previous value
        if data[0] == 'data':
            device['last'] = device['data']

        device[data[0]] = data[1]

    def command_reg(self, cmd_word):
        """Handle a reg command

        :param cmd_word: list of command word pairs
        :returns: nothing
        :rtype:

        """
        if not cmd_word[0] or cmd_word[0] == '':
            return

        if cmd_word[0] != 'reg':
            return

        dev = copy.deepcopy(self.DEVICE)
        for word in cmd_word[1:]:
            self.word_to_dev(dev, word)
        self.devices.append(dev)
        self.LOG_DEBUG("Added device: {0}".format(dev['name']))

    def find_dev_byuid(self, uid):
        """Simple search for a device entry by uid

        :param uid: uid to search for
        :returns: device dict or None
        :rtype: dict

        """
        for dev in self.devices:
            if uid == dev['uid']:
                return dev
        return None

    def command_upd(self, cmd_word):
        """Handle an update command (upd)

        :param cmd_word: list of command word pairs
        :returns: nothing
        :rtype:

        """
        if not cmd_word[0] or cmd_word[0] == '':
            return

        if cmd_word[0] != 'upd':
            return

        dev = None
        for word in cmd_word[1:]:
            parts = word.split(':')
            if parts[0] != 'uid':
                continue
            dev = self.find_dev_byuid(parts[1])

        if dev is None:
            return

        for word in cmd_word[1:]:
            self.word_to_dev(dev, word)
        self.LOG_DEBUG("Updated device: {0}".format(dev['name']))
        self.int_coll_upd_cb(dev)

    def find_alarm_byuid(self, aluid):
        """Simple search for an alarm entry by uid

        :param aluid: aluid to search for
        :returns: device dict or None
        :rtype: dict

        """
        for alarm in self.alarms:
            if aluid == alarm['aluid']:
                return alarm
        return None

    def int_coll_upd_cb(self, dev):
        """Internal device update callback

        Binds to self.coll_upd_cb

        :param dev: the device that was updated
        """

        if self.coll_upd_cb is None:
            return
        else:
            self.coll_upd_cb(dev)
    
    def int_coll_alarm_cb(self, alarm):
        """Internal callback for alarm

        You can bind a function to self.coll_alarm_cb and it will be called
        on all alarm updates.

        :param alarm: the alarm that we got called for
        """

        if self.coll_alarm_cb is None:
            return
        else:
            self.coll_alarm_cb(alarm)

    async def command_setalarm(self, cmd_word):
        """Handle an alarm set command from the server

        :param cmd_word: list of command word pairs
        """
        if not cmd_word[0] or cmd_word[0] == '':
            return

        if cmd_word[0] != 'setalarm':
            return

        alarm = None

        # find the aluid
        for word in cmd_word[1:]:
            parts = word.split(':')
            if parts[0] != 'aluid':
                continue
            alarm = self.find_alarm_byuid(parts[1])

        # loop again and find the sev
        for word in cmd_word[1:]:
            parts = word.split(':')
            if parts[0] != 'alsev':
                continue
            my_sev = int(parts[1])

        if alarm is None and my_sev > 0:
            # we got a new alarm
            alarm = copy.deepcopy(self.ALARM)
        elif alarm is None and my_sev == 0:
            # clearing event for alarm we don't have
            self.LOG_DEBUG('Clearing event for alarm we do not have')
            return

        # now update the internal alarm
        for word in cmd_word[1:]:
            parts = word.split(':')
            alarm[parts[0]] = parts[1]

        # oops, we got a clearing event, delete the alarm
        if alarm['alsev'] == 0:
            self.LOG_DEBUG('Deleting alarm {0}'.format(alarm['aluid']))
            del self.alarms[alarm]
        else:
            self.alarms.append(alarm)

        # Call the internal callback for this alarm
        self.int_coll_alarm_cb(alarm)

    async def gn_register_device(self, dev):
        """Register a new device with gnhast

        :param dev: device to register
        :returns: nothing
        :rtype:

        """
        if dev['name'] == '' or dev['uid'] == '':
            return
        if dev['type'] == 0 or dev['subtype'] == 0:
            return

        cmd = 'reg uid:{0} name:"{1}" '.format(dev['uid'], dev['name'])
        if dev['rrdname'] != '':
            cmd += 'rrdname:"{0}" '.format(dev['rrdname'])
        if dev['scale'] != 0:
            cmd += 'scale:{0} '.format(dev['scale'])
        cmd += 'devt:{0} subt:{1} proto:1\n'.format(dev['type'], dev['subtype'])
        self.writer.write(cmd.encode())
        await self.writer.drain()

    async def gn_update_device(self, dev):
        """Update the data for a device with gnhast

        :param dev: device to update
        :returns:
        :rtype:

        """
        if dev['name'] == '' or dev['uid'] == '':
            return
        if dev['type'] == 0 or dev['subtype'] == 0:
            return

        cmd = 'upd uid:{0} name:"{1}" '.format(dev['uid'], dev['name'])
        if dev['rrdname'] != '':
            cmd += 'rrdname:"{0}" '.format(dev['rrdname'])
        if dev['scale'] != 0:
            cmd += 'scale:{0} '.format(dev['scale'])
        cmd += 'devt:{0} subt:{1} proto:1 '.format(dev['type'], dev['subtype'])
        cmd += '{0}:{1}\n'.format(self.arg_by_subt[dev['subtype']], dev['data'])

        self.writer.write(cmd.encode())
        await self.writer.drain()

    async def gn_change_device(self, dev, newdata):
        """Ask gnhastd to change data about a device

        This is used for example to change a switch's state to on. Gnhastd
        will take your request, and pass it along to the appropriate
        collector which will then modify the state of the device to match
        (if possible).  You should wait a reasonable quantity of time
        (this depends on the actual speed of the device, not gnhastd) and
        then issue an ask. (or issue a feed first)

        :param dev: device to update
        :param newdata: value of new data
        :returns: None
        :rtype: None

        """
        if dev['name'] == '' or dev['uid'] == '':
            return
        if dev['type'] == 0 or dev['subtype'] == 0:
            return

        cmd = 'chg uid:{0}" '.format(dev['uid'])
        cmd += '{0}:{1}\n'.format(self.arg_by_subt[dev['subtype']], dev['data'])

        self.writer.write(cmd.encode())
        await self.writer.drain()

    async def gn_ldevs(self, uid='', type=0, subtype=0):
        """Send an ldevs command to gnhastd, asking for a list of devices

        :param uid: optional uid qualifier
        :param type: optional type qualifier
        :param subtype: optional subtype qualifier
        :returns: nothing
        :rtype: None

        """
        if type == 0 and subtype == 0 and uid == '':
            return

        cmd = 'ldevs '
        if type > 0:
            cmd += 'devt:{0} '.format(type)
        if subtype > 0:
            cmd += 'subt:{0} '.format(subtype)
        if uid != '':
            cmd += 'subt:"{0}" '.format(uid)
        cmd += '\n'

        self.writer.write(cmd.encode())
        await self.writer.drain()

    async def gn_feed_device(self, dev, rate):
        """Ask gnhastd for a continous feed of updates for a device

        :param dev: device to ask for a feed about
        :param rate: rate in seconds for feed
        :returns: None
        :rtype: None

        """
        if dev['name'] == '' or dev['uid'] == '':
            return
        if dev['type'] == 0 or dev['subtype'] == 0:
            return

        cmd = 'feed uid:{0} rate:{1}\n'.format(dev['uid'], rate)

        self.writer.write(cmd.encode())
        await self.writer.drain()

    async def gn_setalarm(self, aluid, altext, alsev, alchan):
        """Set or modify an alarm in gnhast

        use an alsev of 0 to unset an alarm

        :param aluid: unique ID of alarm
        :param altext: Text of alarm
        :param alsev: severity of alarm
        :param alchan: alarm channel bitflag
        """

        if altext is None:
            cmd = 'setalarm aluid:{0} alsev:{1} alchan:{2}\n' \
                  .format(aluid, alsev, int(alchan))
        else:
            cmd = 'setalarm aluid:{0} altext:"{1}" alsev:{2} alchan:{3}\n' \
                  .format(aluid, altext, alsev, int(alchan))

        self.writer.write(cmd.encode())
        await self.writer.drain()

    async def gn_listenalarms(self, alsev, alchan):
        """Tell gnhastd we want to listen to a set of alarms

        :param alsev: minimum severity of alarm to listen to (0 is ok)
        :param alchan: channel to listen. use AlarmChan.ALL to listen to all
        """
        cmd = 'listenalarms alchan:{0} alsev:{1}\n' \
              .format(int(alchan), alsev)
        self.writer.write(cmd.encode())
        await self.writer.drain()

    async def gn_dumpalarms(self, alsev=1, alchan=AlarmChan.ALL, aluid=None):
        """Ask gnhastd to dump all current alarms to us

        :param alsev: minimum severity (default 1)
        :param alchan: channel to dump (default ALL)
        :param aluid: alarm uid to dump (default any)
        """

        cmd = 'dumpalarms '
        if alsev != 1:
            cmd += 'alsev:{0} '.format(alsev)
        if alchan != AlarmChan.ALL:
            cmd += 'alchan:{0} '.format(int(alchan))
        if aluid is not None:
            cmd += 'aluid:{0} '.format(aluid)
        cmd += '\n'
        self.writer.write(cmd.encode())
        await self.writer.drain()

    async def gn_rawcmd(self, cmd):
        """Send a raw dirty command to gnhast.  Appends the \n

        :param cmd: the text string to send
        """

        csend = cmd + '\n'
        self.writer.write(csend.encode())
        await self.writer.drain()

    async def gn_ask_device(self, dev):
        """Ask gnhastd for current data for this device

        :param dev: device to ask gnhast about
        :returns:
        :rtype:

        """
        if dev['name'] == '' or dev['uid'] == '':
            return
        if dev['type'] == 0 or dev['subtype'] == 0:
            return

        cmd = 'ask uid:{0}\n'.format(dev['uid'])

        self.writer.write(cmd.encode())
        await self.writer.drain()

    async def gn_imalive(self):
        """Send a ping reply
        """
        self.LOG_DEBUG("PING REPLY")
        cmd = "imalive\n"
        self.writer.write(cmd.encode())
        await self.writer.drain()

    async def collector_healthcheck(self):
        """Check if we are ok, if so, send a imalive
        """
        if self.collector_healthy:
            await self.gn_imalive()
            self.LOG_DEBUG("I am ok")
        else:
            self.LOG_WARNING("Collector is non-functional")

    async def gn_disconnect(self):
        """Send a disconnect command to gnhastd

        :returns:
        :rtype:

        """
        if self.writer is not None:
            self.writer.write("disconnect\n".encode())
            await self.writer.drain()

    async def gn_client_name(self, name):
        """Send our client name to gnhastd

        :param name: the name of our collector
        :returns:
        :rtype:

        """
        send = "client client:{0}\n".format(name)
        self.writer.write(send.encode())
        await self.writer.drain()

    async def shutdown(self, sig, loop):
        """Shutdown the collector

        :param sig: Signal we recieved
        :param loop: the asyncio loop
        :returns: nothing
        :rtype:

        """
        self.LOG_DEBUG('caught {0}'.format(sig.name))
        await self.gn_disconnect()
        tasks = [task for task in asyncio.Task.all_tasks() if task is not
                 asyncio.tasks.Task.current_task()]
        list(map(lambda task: task.cancel(), tasks))
        results = await asyncio.gather(*tasks, return_exceptions=True)
        self.LOG_DEBUG('finished awaiting cancelled tasks, results: {0}'.format(results))
        loop.stop()

    async def abort(self):
        """Abort the collector hard

        :returns: None
        :rtype: None

        """
        self.LOG_ERROR("Aborting collector")
        await self.shutdown(signal.SIGTERM, self.loop)
        exit(1)

    async def gn_connect(self, host='127.0.0.1', port=2920):
        """Create a new connection to gnhastd server

        :param host: gnhastd host (default 127.0.0.1)
        :param port: gnhastd port (default 2920)
        :returns: the gnhastd object
        :rtype:

        """
        try:
            self.reader, self.writer = await asyncio.open_connection(host, port, loop=self.loop)
            return self
        except (asyncio.TimeoutError, ConnectionRefusedError):
            self.LOG_ERROR("Cannot connect to gnhastd {0}:{1}".format(host, str(port)))
            raise ConnectionError('Connection to gnhastd Failed')

    async def gnhastd_listener(self):
        """Listen to gnhastd for commands and info

        :returns:
        :rtype:

        """
        valid_data = True
        while valid_data:
            data = await self.reader.readline()
            if data.decode() == '':
                valid_data = False
            command = data.decode()
            if command != '':
                self.LOG_DEBUG('Got command: {0}'.format(command.rstrip()))
                cmd_words = shlex.split(command.rstrip())
                # pprint(cmd_words)
                if not cmd_words[0] or cmd_words[0] == '':
                    self.LOG_WARNING("Ignoring garbage command")
                    continue
                if cmd_words[0] == 'reg':
                    self.command_reg(cmd_words)
                elif cmd_words[0] == 'upd':
                    self.command_upd(cmd_words)
                elif cmd_words[0] == 'endldevs':
                    self.LOG_DEBUG('Ignored endldevs')
                elif cmd_words[0] == 'ping':
                    await self.collector_healthcheck()
                elif cmd_words[0] == 'setalarm':
                    await self.command_setalarm(cmd_words)
                else:
                    self.LOG_WARNING('Unhandled command')

    async def gn_build_client(self, client_name):
        """Build a new client for gnhastd

        :param client_name: our client name
        :returns:
        :rtype:

        """
        # read our config file
        self.parse_cfg()
        self.log_open()
        # open a connection to gnhastd
        try:
            await self.gn_connect(self.config['gnhastd']['hostname'], self.config['gnhastd']['port'])
            # send our name
            await self.gn_client_name(client_name)
        except ConnectionError:
            await self.abort()

    def log_open(self):
        """Open the logfile for writing

        :returns: logfile
        :rtype: file descriptor

        """
        try:
            if self.config['logfile']:
                try:
                    self.log = open(self.config['logfile'], 'a')
                except Exception as e:
                    self.log = sys.stderr
                    self.LOG_ERROR('cannot open log: {0}'.format(str(e)))
            else:
                self.log = sys.stderr
        except KeyError:
            self.log = sys.stderr

    def LOG(self, msg, mode=LOG_INFO):
        if mode == LOG_INFO:
            ls = '{0} [INFO]:'.format(datetime.now().ctime())
        elif mode == LOG_ERROR:
            ls = '{0} [ERROR]:'.format(datetime.now().ctime())
        elif mode == LOG_WARNING:
            ls = '{0} [WARNING]:'.format(datetime.now().ctime())
        elif mode == LOG_DEBUG:
            ls = '{0} [DEBUG]:'.format(datetime.now().ctime())
        print(ls + msg, file=self.log)

    def LOG_DEBUG(self, msg):
        if self.debug:
            self.LOG(msg, mode=LOG_DEBUG)

    def LOG_ERROR(self, msg):
        self.LOG(msg, mode=LOG_ERROR)

    def LOG_WARNING(self, msg):
        self.LOG(msg, mode=LOG_WARNING)

#!/usr/bin/env python

import asyncio
from gnhast import confuseparse
from pprint import pprint
import time
from pint import UnitRegistry
import shlex
import functools
import signal
import re
import copy

# Simple c-like enum. Sigh.
class DEVTYPE:
    DEVICE_NONE, DEVICE_SWITCH, DEVICE_DIMMER, \
        DEVICE_SENSOR, DEVICE_TIMER, DEVICE_BLIND, \
        *_ = range(0, 100)

# Protocol is kinda useless, so I'm just skipping it until I nuke it from the
# main tree

class SUBTYPE:
    SUBTYPE_NONE, SUBTYPE_SWITCH, SUBTYPE_OUTLET, \
        SUBTYPE_TEMP, SUBTYPE_HUMID, SUBTYPE_COUNTER, \
        SUBTYPE_PRESSURE, SUBTYPE_SPEED, SUBTYPE_DIR, \
        SUBTYPE_PH,SUBTYPE_WETNESS, SUBTYPE_HUB, SUBTYPE_LUX, \
        SUBTYPE_VOLTAGE, SUBTYPE_WATTSEC, SUBTYPE_WATT,SUBTYPE_AMPS, \
        SUBTYPE_RAINRATE, SUBTYPE_WEATHER,SUBTYPE_ALARMSTATUS, \
        SUBTYPE_NUMBER, SUBTYPE_PERCENTAGE, SUBTYPE_FLOWRATE, \
        SUBTYPE_DISTANCE, SUBTYPE_VOLUME, SUBTYPE_TIMER, \
        SUBTYPE_THMODE,SUBTYPE_THSTATE, SUBTYPE_SMNUMBER, \
        SUBTYPE_BLIND, SUBTYPE_COLLECTOR, SUBTYPE_TRIGGER, \
        SUBTYPE_ORP, SUBTYPE_SALINITY, SUBTYPE_DAYLIGHT, \
        SUBTYPE_MOONPH, SUBTYPE_TRISTATE, *_ = range(0, 100)

class TSCALE:
    TSCALE_F, TSCALE_C, TSCALE_K, TSCALE_R, *_ = range(0, 100)

class BAROSCALE:
    BAROSCALE_IN, BAROSCALE_MM, BAROSCALE_MB, BAROSCALE_CB, *_ = range(0, 100)

class gnhast:
    def __init__(self, cfgfile):
        self.cfg = cfgfile
        self.loop = asyncio.get_event_loop()
        self.devices = []
        self.devtype = DEVTYPE()
        self.subtype = SUBTYPE()
        self.tscale= TSCALE()
        self.baroscale = BAROSCALE()
        self.arg_by_subt = [ "none", "switch", "switch", "temp", "humid",
                             "count", "pres", "speed", "dir", "ph", "wet",
                             "hub", "lux", "volts", "wsec", "watt", "amps",
                             "rain", "weather", "alarm", "number", "pct",
                             "flow", "distance", "volume", "timer",
                             "thmode", "thstate", "smnum", "blind",
                             "collector", "trigger", "orp", "salinity",
                             "moonph", "tristate" ]
        self.DEVICE = {
            'uid': '', 'loc': '', 'name': '', 'rrdname': '',
            'proto': 0, 'type': 0, 'subtype': 0,
            'scale': 0,
            'data': 0, 'last': 0, 'min': 0, 'max': 0, 'avg': 0,
            'lowat': 0, 'hiwat': 0, 'change': 0,
            'handler': 0, 'hargs': 0,
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
            'moonph', 'tristate', 'bool' ]
        self.cf_tscale = ['F', 'C', 'K', 'R']
        self.cf_speedscale = ['mph', 'ms', 'kph', 'knots']
        self.cf_lengthscale = ['in', 'mm']
        self.cf_baroscale = ['in', 'mm', 'mb', 'cb']
        self.cf_lightscale = ['wm2', 'lux']
        self.cf_salinescale = ['ppt', 'sg', 'ms']

        self.collector_healthy = True
        self.debug = False

    def parse_convert_to_int(self, value, ptype):
        if isinstance(value, int):
            return value
        return ptype.index(value)

    def dprint(self, thing):
        if self.debug:
            print('DEBUG: ' + thing)

    def new_device(self, uid, name, type, subtype):
        dev = copy.deepcopy(self.DEVICE)
        dev['name'] = name
        dev['devt'] = type
        dev['uid'] = uid
        dev['subt'] = subtype
        self.devices.append(dev)
        return dev

    def parse_cfg(self):
        """Parse a config file
        """
        modcfg = ''
        with open(self.cfg, "r") as f:
            for line in f:
                x = line.rstrip()
                if not x.endswith('{') and not x == '':
                    x += ';'
                modcfg += x + '\n'
        self.config = confuseparse.parse(modcfg)

        # Now look for device-* entries and reform them
        self.config.update({'devices':dict()})
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
                    x['subtype'] = self.parse_convert_to_int(x['subtype'], self.cf_subt)
                if 'tscale' in x:
                    x['tscale'] = self.parse_convert_to_int(x['tscale'], self.cf_tscale)
                if 'speedscale' in x:
                    x['speedscale'] = self.parse_convert_to_int(x['speedscale'], self.cf_speedscale)
                if 'lengthscale' in x:
                    x['lengthscale'] = self.parse_convert_to_int(x['lengthscale'], self.cf_lengthscale)
                if 'baroscale' in x:
                    x['baroscale'] = self.parse_convert_to_int(x['baroscale'], self.cf_baroscale)
                if 'lightscale' in x:
                    x['lightscale'] = self.parse_convert_to_int(x['lightscale'], self.cf_lightscale)
                if 'salinescale' in x:
                    x['salinescale'] = self.parse_convert_to_int(x['salinescale'], self.cf_salinescale)
                keylist.append(key)
                # While we are here, append them to the internal devices list
                self.devices.append(self.config['devices'][m.group(1)])

        for key in keylist:
            del self.config[key]

        if self.debug:
            pprint(self.config)
        return self.config

    def gn_scale_temp(self, temp, curscale, newscale):
        ureg = UnitRegistry()
        Q_ = ureg.Quantity

        if curscale == self.tscale.TSCALE_F:
            temp_s = Q_(temp, ureg.degF)
        if curscale == self.tscale.TSCALE_C:
            temp_s = Q_(temp, ureg.degC)
        if curscale == self.tscale.TSCALE_K:
            temp_s = Q_(temp, ureg.kelvin)
        if curscale == self.tscale.TSCALE_R:
            temp_s = Q_(temp, ureg.degR)

        if newscale == self.tscale.TSCALE_F:
            return temp_s.to('degF')
        if newscale == self.tscale.TSCALE_C:
            return temp_s.to('degC')
        if newscale == self.tscale.TSCALE_K:
            return temp_s.to('kelvin')
        if newscale == self.tscale.TSCALE_R:
            return temp_s.to('degR')
        return temp

    def word_to_dev(self, device, cmdword):
        # take a string like devt:1 and import it to a device
        data = cmdword.split(':')
        vwords = ['uid', 'name', 'rate', 'rrdname', 'devt', 'proto',
                  'subt', 'client', 'scale', 'handler', 'hargs',
                  'glist', 'dlist', 'collector', 'alsev', 'altext',
                  'aluid', 'alchan', 'spamhandler' ]

        if data[0] in self.arg_by_subt:
            data[0] = 'data'

        if data[0] not in vwords:
            self.dprint("Unhandled word: {0}".format(data[0]))
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
        # handle a register command
        if not cmd_word[0] or cmd_word[0] == '':
            return

        if cmd_word[0] != 'reg':
            return

        dev = copy.deepcopy(self.DEVICE)
        for word in cmd_word[1:]:
            self.word_to_dev(dev, word)
        self.devices.append(dev)
        self.dprint("Added device: {0}".format(dev['name']))

    def find_dev_byuid(self, uid):
        for dev in self.devices:
            if uid == dev['uid']:
                return dev
        return None

    def command_upd(self, cmd_word):
        # handle an update command
        if not cmd_word[0] or cmd_word[0] == '':
            return

        if cmd_word[0] != 'upd':
            return

        dev = None
        for word in cmd_word[1:]:
            parts = word.split(':')
            if parts[0] != 'uid':
                continue
            dev = self.find_dev_byuid(uid)

        if dev is None:
            return
        
        for word in cmd_word[1:]:
            self.word_to_dev(dev, word)
        self.dprint("Updated device: {0}".format(dev['name']))
        
    async def gn_register_device(self, dev):
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
        await writer.drain()

    async def gn_update_device(self, dev):
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

    async def gn_imalive(self):
        """Send a ping reply
        """
        cmd = "imalive\n"
        self.writer.write(cmd.encode())
        await self.writer.drain()

    async def collector_healthcheck(self):
        """Check if we are ok, if so, send a imalive
        """
        if self.collector_healthy:
            await self.gn_imalive()
            self.dprint("I am ok")
        else:
            print("WARNING: Collector is non-functional")
        
    async def gn_disconnect(self):
        self.writer.write("disconnect\n".encode())
        await self.writer.drain()

    async def gn_client_name(self, name):
        send = "client client:{0}\n".format(name)
        self.writer.write(send.encode())
        await self.writer.drain()

    async def shutdown(self, sig, loop):
        self.dprint('caught {0}'.format(sig.name))
        await self.gn_disconnect()
        tasks = [task for task in asyncio.Task.all_tasks() if task is not
                 asyncio.tasks.Task.current_task()]
        list(map(lambda task: task.cancel(), tasks))
        results = await asyncio.gather(*tasks, return_exceptions=True)
        self.dprint('finished awaiting cancelled tasks, results: {0}'.format(results))
        loop.stop()

    async def gn_connect(self, host, port):
        self.reader, self.writer = await asyncio.open_connection(host, port, loop=self.loop)
        return self

    async def gnhastd_listener(self):
        valid_data = True
        while valid_data:
            data = await self.reader.readline()
            if data.decode() == '':
                valid_data = False
            command = data.decode()
            if command != '':
                self.dprint('Got command: {0}'.format(command.rstrip()))
                cmd_words = shlex.split(command.rstrip())
                #pprint(cmd_words)
                if not cmd_words[0] or cmd_words[0] == '':
                    print("WARNING: Ignoring garbage command")
                    continue
                if cmd_words[0] == 'reg':
                    self.command_reg(cmd_words)
                elif cmd_words[0] == 'upd':
                    self.command_upd(cmd_words)
                elif cmd_words[0] == 'endldevs':
                    self.dprint('Ignored endldevs')
                elif cmd_words[0] == 'ping':
                    await self.collector_healthcheck()
                else:
                    print('WARNING: Unhandled command')
                    
    async def gn_build_client(self, client_name):
        # read our config file
        self.parse_cfg()
        # open a connection to gnhastd
        await self.gn_connect(self.config['gnhastd']['hostname'], self.config['gnhastd']['port'])
        # send our name
        await self.gn_client_name(client_name)

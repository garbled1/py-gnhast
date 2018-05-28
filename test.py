#!/usr/bin/env python
from gnhast import gnhast
import signal
import asyncio

x = gnhast.gnhast("/usr/src/gnhast/owsrvcoll/test.atlas.conf")
x.loop.run_until_complete(x.gn_build_client('foo'))

async def fiddle():
    msg = 'ldevs\n'
    x.writer.write(msg.encode())
    await asyncio.sleep(5)
    await x.gn_disconnect()

x.loop.create_task(x.gnhastd_listener())
x.loop.create_task(fiddle())

for sig in [ signal.SIGTERM, signal.SIGINT ]:
    x.loop.add_signal_handler(sig,
                              lambda: asyncio.ensure_future(x.shutdown(sig, x.loop)))
try:
    x.loop.run_forever()
finally:
    x.loop.close()

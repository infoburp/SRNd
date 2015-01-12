#!/usr/bin/python
import time
import signal
import fcntl
import os
import threading

import SRNd

srnd = SRNd.SRNd()
#signal.signal(signal.SIGIO, srnd.relay_dropper_handler)
signal.signal(signal.SIGIO, srnd.dropper.handler_progress_incoming)
signal.signal(signal.SIGHUP, srnd.update_hooks_outfeeds_plugins)
fd = os.open(srnd.watching(), os.O_RDONLY)
fcntl.fcntl(fd, fcntl.F_SETSIG, 0)
fcntl.fcntl(fd, fcntl.F_NOTIFY,
            fcntl.DN_MODIFY | fcntl.DN_CREATE | fcntl.DN_MULTISHOT)
srnd.start()
#srnd.dropper.start()
#time.sleep(1)
#srnd.dropper.handler_progress_incoming(None, None)
while True:
  try:
    time.sleep(3600)
  except KeyboardInterrupt:
    print
    print "[SRNd] shutting down.."
    srnd.shutdown()
    for thread in threading.enumerate():
      #print "joining ", thread
      try:
        thread.join()
      except RuntimeError as e:
        pass
    print "[SRNd] bye"
    exit(0)

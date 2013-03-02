import sys
import datetime
from rq import Queue, Connection, Worker

# print current date time to stderr and stdout
now = datetime.datetime.now()
dt = now.strftime("%Y-%m-%d %H:%M")
sys.stderr.write("\nStaring rq worker on " + dt + "\n\n")
print
print "Starting rq worker on %s" % dt
print

# Provide queue names to listen to as arguments to this script,
# similar to rqworker
with Connection():
    qs = map(Queue, sys.argv[1:]) or [Queue()]
    w = Worker(qs)
    w.work()

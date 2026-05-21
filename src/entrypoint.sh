#!/bin/sh

COMMAND='python3 start.py'
LOGFILE=restart.txt

writelog() {
  now=`date`
  echo "$now $*" >> $LOGFILE
}

writelog "Starting"
while true ; do
  $COMMAND > /dev/null 2>&1
  writelog "Exited with status $?"
  writelog "Restarting"
done

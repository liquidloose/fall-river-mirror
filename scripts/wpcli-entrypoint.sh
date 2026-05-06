#!/bin/sh
set -e
cd /var/www/html
if [ "$#" -gt 0 ]; then
  exec "$@"
fi
# No args (e.g. `up -d` with default command): stay alive for exec/shell attach.
exec tail -f /dev/null

#!/bin/bash
# Start Xvfb in the background
Xvfb :99 -screen 0 1920x1080x24 &
export DISPLAY=:99

# Wait a moment for Xvfb to start
sleep 1

# Run the actual command (passed as arguments)
exec "$@"
#!/bin/bash
# Docker entrypoint for headless browser/Playwright support.
# Xvfb provides a virtual display so browser automation can run without a real display.

# Update package lists (needed if Xvfb or other deps are installed at runtime)
apt update

# Start Xvfb (X Virtual Framebuffer) on display :99 with 1920x1080 resolution, 24-bit color
Xvfb :99 -screen 0 1920x1080x24 &
export DISPLAY=:99

# Wait for Xvfb to initialize before launching the main process
sleep 1

# Run the actual command (passed as arguments from docker-compose or Dockerfile CMD)
exec "$@"
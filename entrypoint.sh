#!/bin/bash
# Docker entrypoint for headless browser/Playwright support.
# Xvfb provides a virtual display so browser automation can run without a real display.
# Runs as root so Xvfb can start; then drops to app user (UID 1000) so writes to /code match host.

# Ensure X11 socket dir exists so Xvfb can run as non-root (euid != 0)
mkdir -p /tmp/.X11-unix

# Remove stale lock from previous container run (restart leaves /tmp intact)
rm -f /tmp/.X99-lock

# Start Xvfb (X Virtual Framebuffer) on display :99 with 1920x1080 resolution, 24-bit color
Xvfb :99 -screen 0 1920x1080x24 &
export DISPLAY=:99

# Wait for Xvfb to initialize before launching the main process
sleep 1

# Run as app user when root (gosu); when already 1000:1000, exec directly
[ "$(id -u)" = "0" ] && exec gosu app "$@" || exec "$@"
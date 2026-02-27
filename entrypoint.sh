#!/bin/bash
# Docker entrypoint for headless browser/Playwright support.
# Xvfb provides a virtual display so browser automation can run without a real display.
# Runs as root so Xvfb can start; then drops to app user (UID 1000) so writes to /code match host.

# Start Xvfb (X Virtual Framebuffer) on display :99 with 1920x1080 resolution, 24-bit color
Xvfb :99 -screen 0 1920x1080x24 &
export DISPLAY=:99

# Wait for Xvfb to initialize before launching the main process
sleep 1

# Run the actual command as app user (UID 1000) so bind-mounted /code has correct host permissions
exec gosu app "$@"
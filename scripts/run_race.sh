#!/usr/bin/env bash
set -euo pipefail
docker rm -f mi-dog-race 2>/dev/null || true
docker run -d --name mi-dog-race --shm-size=1g --privileged \
  -e DISPLAY="${DISPLAY:-:0}" -e WAYLAND_DISPLAY="${WAYLAND_DISPLAY:-wayland-0}" \
  -e XDG_RUNTIME_DIR=/mnt/wslg/runtime-dir -e PULSE_SERVER=/mnt/wslg/PulseServer \
  -v /tmp/.X11-unix:/tmp/.X11-unix -v /mnt/wslg:/mnt/wslg \
  mi-dog-solution:latest
printf 'Started mi-dog-race. Follow logs with: docker logs -f mi-dog-race\n'

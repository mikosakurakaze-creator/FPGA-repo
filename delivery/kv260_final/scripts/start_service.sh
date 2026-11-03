#!/bin/sh
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
test "$(id -u)" = 0
exec /usr/bin/python3 "$ROOT/ps/hardware_service.py"

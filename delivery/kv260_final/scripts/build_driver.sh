#!/bin/sh
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
test "$(uname -m)" = aarch64
make -C "/lib/modules/$(uname -r)/build" M="$ROOT/ps/driver" KCFLAGS=-Werror modules
dtc -@ -I dts -O dtb -o "$ROOT/ps/driver/joint_image.dtbo" "$ROOT/ps/driver/joint_image.dtso"
dtc -@ -I dts -O dtb -o "$ROOT/ps/driver/joint_resources.dtbo" "$ROOT/ps/driver/joint_resources.dtso"
test "$(modinfo -F vermagic "$ROOT/ps/driver/kv260_joint_once.ko" | cut -d ' ' -f 1)" = "$(uname -r)"

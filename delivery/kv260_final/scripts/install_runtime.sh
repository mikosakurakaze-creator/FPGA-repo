#!/bin/sh
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
test "$(uname -m)" = aarch64
python3 -c 'import sys; assert sys.version_info[:2]==(3,10), "Requires Ubuntu 22.04 Python 3.10"'
python3 -c 'import gi,numpy,PIL; gi.require_version("Gtk","3.0");gi.require_version("Gst","1.0");from gi.repository import Gtk,Gst'
mkdir -p "$ROOT/ps/deps" "$ROOT/ps/hdmi_runtime_assets" "$ROOT/ps/tools"
python3 -m pip install --no-index --no-deps --target "$ROOT/ps/deps" "$ROOT"/runtime_assets/*.whl
cp "$ROOT/runtime_assets/ssd_mobilenet.onnx" "$ROOT/ps/hdmi_runtime_assets/ssd_mobilenet.onnx"
python3 - "$ROOT" <<'PY'
import sys,tarfile,shutil
from pathlib import Path
r=Path(sys.argv[1]);target=r/'ps/tools'
with tarfile.open(r/'runtime_assets/ffmpeg_arm64.tar.xz') as t:
 for m in t.getmembers():
  if not m.isfile() or Path(m.name).name not in ['ffmpeg','ffprobe','GPLv3.txt','readme.txt']:continue
  p=target/Path(m.name).name
  with p.open('wb') as f:shutil.copyfileobj(t.extractfile(m),f)
  if p.name in ['ffmpeg','ffprobe']:p.chmod(0o755)
PY
PYTHONPATH="$ROOT/ps/deps" python3 -c 'import onnxruntime;print("RUNTIME_PASS",onnxruntime.__version__)'

"""Execute a command and persist command, UTC times, status and raw streams."""
import argparse
from datetime import datetime, timezone
from pathlib import Path
import subprocess
import sys
import os
from .io import write_json, sha256


def execute(root, label, command):
    folder = Path(root) / label
    folder.mkdir(parents=True, exist_ok=False)
    start = datetime.now(timezone.utc).isoformat()
    with (folder / 'stdout.log').open('wb') as out, (folder / 'stderr.log').open('wb') as err:
        result = subprocess.run(command, stdout=out, stderr=err)
    report = {'command': command, 'cwd': os.getcwd(), 'start_utc': start,
              'end_utc': datetime.now(timezone.utc).isoformat(), 'exit_status': result.returncode,
              'stdout_sha256': sha256(folder / 'stdout.log'), 'stderr_sha256': sha256(folder / 'stderr.log')}
    write_json(folder / 'execution.json', report)
    print(f'{label}: exit={result.returncode}', flush=True)
    return result.returncode


if __name__ == '__main__':
    p = argparse.ArgumentParser(__doc__)
    p.add_argument('root'); p.add_argument('label'); p.add_argument('command', nargs=argparse.REMAINDER)
    a = p.parse_args()
    cmd = a.command[1:] if a.command and a.command[0] == '--' else a.command
    sys.exit(execute(a.root, a.label, cmd))

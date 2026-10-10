"""Hash-gated single FRAMES=8 simulation; no continuation beyond natural finish."""
import argparse
import datetime
import json
import subprocess
import time
from pathlib import Path
from prepare_system import CONFIG, SHA


def now():
    return datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).isoformat()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', required=True, type=Path)
    args = parser.parse_args()
    run = args.run.resolve()
    assert not (run / 'system.log').exists() and not (run / 'exit_status.json').exists()
    manifest = json.loads((run / 'run_manifest.json').read_text())
    assert manifest['config'] == CONFIG
    for item in manifest['original_source_manifest']['source_files']:
        assert SHA(Path(item['path'])) == item['sha256']
    for item in manifest['substitutions']:
        assert SHA(Path(item['candidate'])) == item['candidate_sha256']
    for name, digest in manifest['protected_copies'].items():
        assert SHA(run / name) == digest
    assert SHA(run / 'system_tb.sv') == manifest['generated_tb_sha256']
    kernel = run / 'xsim.dir/phase4f_system/xsimk.exe'
    assert kernel.is_file() and 'Built simulation snapshot phase4f_system' in (run / 'elaborate.log').read_text()
    state = dict(status='RUNNING', started=now(), kernel_sha256=SHA(kernel), config=CONFIG)
    with (run / 'console.log').open('w') as log:
        process = subprocess.Popen(['cmd', '/c', str(run / 'simulate.cmd')], cwd=run,
                                   stdout=log, stderr=subprocess.STDOUT,
                                   creationflags=subprocess.CREATE_NO_WINDOW)
        state['pid'] = process.pid
        (run / 'process.json').write_text(json.dumps(state, indent=2))
        print('STARTED_FRAMES8', process.pid, flush=True)
        previous = ''
        while process.poll() is None:
            path = run / 'results/progress.csv'
            if path.exists():
                rows = path.read_text().splitlines()
                latest = rows[-1] if len(rows) > 1 else ''
                if latest and latest != previous:
                    print('PROGRESS', latest, flush=True)
                    previous = latest
            time.sleep(10)
    state.update(status='TERMINAL', finished=now(), exit_code=process.returncode)
    (run / 'exit_status.json').write_text(json.dumps(state, indent=2))
    print('TERMINAL_FRAMES8', process.returncode, flush=True)
    raise SystemExit(process.returncode)


if __name__ == '__main__':
    main()

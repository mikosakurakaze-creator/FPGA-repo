"""Rebuild numerical evidence in a NEW directory. No hardware or git changes."""
import argparse
from pathlib import Path
import sys
import json
from .record import execute
from .io import write_json, sha256


def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument('--source', required=True)
    parser.add_argument('--out', required=True)
    parser.add_argument('--image', help='Optional full RGB image, never resized')
    parser.add_argument('--scales', help='Declared per-node scale calibration JSON')
    args = parser.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=False)
    commands = out / 'commands'
    results = []
    def call(label, *command):
        result = execute(commands, label, [sys.executable, *map(str, command)])
        results.append({'label': label, 'exit_status': result})
        write_json(out / 'suite_status.json', {'commands': results, 'hardware_test': False})
        return result == 0
    call('environment', '-m', 'pip', 'freeze', '--all')
    call('source_identity', '-m', 'griddehaze_fixed.fetch', args.source)
    call('operator_tests', '-m', 'unittest', 'griddehaze_fixed.test_integer', 'griddehaze_fixed.test_io', 'griddehaze_fixed.test_plan', 'griddehaze_fixed.test_data', '-v')
    candidates = [('w8cal', 14, 8), ('w16cal', 14, 16)] if args.scales else [('w8f10', 10, 8), ('w16f10', 10, 16), ('w16f12', 12, 16)]
    extra = ['--scales', args.scales] if args.scales else []
    for name, frac, bits in candidates:
        package = out / name
        if not call('export_' + name, '-m', 'griddehaze_fixed.export', args.source, package,
                    '--activation-frac', frac, '--weight-bits', bits, *extra):
            continue
        call('audit_' + name, '-m', 'griddehaze_fixed.audit_package', package, '--report', out / (name + '_audit.json'))
        call('random_' + name, '-m', 'griddehaze_fixed.cli', 'run', '--package', package,
             '--source', args.source, '--out', out / (name + '_random'), '--pattern', 'random')
    selected_name = 'w16cal' if args.scales else 'w16f10'
    package = out / selected_name
    if (package / 'manifest.json').exists():
        for pattern in ['black', 'white', 'channel', 'impulse']:
            call(pattern, '-m', 'griddehaze_fixed.cli', 'run', '--package', package, '--source', args.source,
                 '--out', out / pattern, '--pattern', pattern)
        for h, w in [(4, 4), (32, 48), (34, 46)]:
            call(f'size_{h}x{w}', '-m', 'griddehaze_fixed.cli', 'run', '--package', package, '--source', args.source,
                 '--out', out / f'size_{h}x{w}', '--pattern', 'impulse', '--height', h, '--width', w)
        for backend, name in [('numpy', 'repeat'), ('direct', 'independent')]:
            if call(name, '-m', 'griddehaze_fixed.cli', 'run', '--package', package, '--source', args.source,
                    '--out', out / name, '--pattern', 'random', '--backend', backend, '--no-float'):
                call('compare_' + name, '-m', 'griddehaze_fixed.cli', 'compare', out / (selected_name + '_random'), out / name,
                     '--report', out / ('compare_' + name + '.json'))
        for h, w in [(33, 47), (675, 1280), (720, 1280)]:
            call(f'plan_{h}x{w}', '-m', 'griddehaze_fixed.plan', '--package', package,
                 '--height', h, '--width', w, '--out', out / f'plan_{h}x{w}.json')
        if args.image:
            call('full_image', '-m', 'griddehaze_fixed.cli', 'run', '--package', package,
                 '--source', args.source, '--out', out / 'full_image', '--image', args.image)
        repeat = out / (selected_name + '_repeat')
        call('export_repeat', '-m', 'griddehaze_fixed.export', args.source, repeat,
             '--activation-frac', 14 if args.scales else 10, '--weight-bits', 16, *extra)
        if (repeat / 'manifest.json').exists():
            identical = {f: sha256(package / f) == sha256(repeat / f)
                         for f in ['parameters.bin', 'graph.json', 'manifest.json']}
            write_json(out / 'export_determinism.json', identical)
    print(json.dumps(results, indent=2))
    raise SystemExit(1 if any(r['exit_status'] for r in results) else 0)


if __name__ == '__main__':
    main()

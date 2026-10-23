"""Rebuild missing low-light IPs in a fresh local directory; never edit the clone.

Run this driver through run_windows_desktop.py on packaged Windows parents.
Outputs are new build candidates, not the historical board-qualified binaries.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--reference', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--vitis', type=Path, required=True)
    a = p.parse_args()
    out = a.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    ref = a.reference.resolve()
    report = {'pass': False, 'scope': 'new HLS candidates; no historical board qualification',
              'inputs': {}, 'steps': {}}
    try:
        src = out / 'source'
        mappings = [
            ('fpga/hls/zero_dce_cnn_v1_2_30fps/candidate_b_rowstream_r4',
             ['zero_dce_cnn_top.cpp', 'zero_dce_cnn_top.h']),
            ('fpga/perf/cnn_v1_2_phase3b_r4',
             ['row_transfer.hpp', 'rowstream_arch.inc', 'rowstream_group_arch.inc']),
            ('fpga/hls/bilinear_fixed16_buffered',
             ['bilinear_fixed16_buffered.cpp', 'bilinear_fixed16_buffered.hpp']),
            ('fpga/hls/curve_image_fixed16', ['curve_image_fixed16.cpp', 'curve_image_fixed16.hpp'])]
        for relative, names in mappings:
            for name in names:
                source, dest = ref / relative / name, src / relative / name
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, dest)
                assert sha(source) == sha(dest)
                report['inputs'][relative + '/' + name] = sha(source)
        jobs = [('cnn', 'zero_dce_cnn_top', mappings[0][0]),
                ('bilinear', 'bilinear_fixed16_buffered', mappings[2][0]),
                ('curve', 'curve_image_fixed16', mappings[3][0])]
        for name, top, relative in jobs:
            work = out / name
            work.mkdir()
            cfg = work / 'hls_config.cfg'
            cfg.write_text('\n'.join(['part=xck26-sfvc784-2LV-c', '[hls]',
                'flow_target=vivado', 'clock=10',
                'syn.interface.m_axi_conservative_mode=false' if name == 'cnn' else '',
                'syn.file=' + (src / relative / (top + '.cpp')).as_posix(),
                'syn.top=' + top, 'package.output.format=ip_catalog', '']), encoding='utf-8')
            cmd = work / 'build.cmd'
            cmd.write_text('@echo off\nsetlocal\nset "PROCESSOR_ARCHITECTURE=AMD64"\n'
                'call "' + str(a.vitis / 'settings64.bat') + '"\n'
                'if errorlevel 1 exit /b %errorlevel%\n'
                'call "' + str(a.vitis / 'bin/v++.bat') + '" -c --mode hls --config "'
                + str(cfg) + '" --work_dir "' + str(work / 'component') + '"\n'
                'exit /b %errorlevel%\n', encoding='utf-8')
            print('Building ' + name + ': ' + str(work / 'build.log'), flush=True)
            with (work / 'build.log').open('wb') as log:
                result = subprocess.run([os.environ.get('COMSPEC', 'cmd.exe'), '/d', '/c', str(cmd)],
                                        cwd=work, stdout=log, stderr=subprocess.STDOUT)
            step = {'return_code': result.returncode, 'config_sha256': sha(cfg)}
            report['steps'][name] = step
            ip = work / 'component/hls/impl/ip/component.xml'
            xml = work / ('component/hls/syn/report/' + top + '_csynth.xml')
            if result.returncode or not ip.is_file() or not xml.is_file():
                raise RuntimeError(name + ' failed; inspect build.log')
            root = ET.parse(xml).getroot()
            step['resources'] = {c.tag: c.text for c in root.find('AreaEstimates/Resources')}
            step['estimated_clock_ns'] = root.findtext('PerformanceEstimates/SummaryOfTimingAnalysis/EstimatedClockPeriod')
            step['component_sha256'] = sha(ip)
            report['steps'][name] = step
            (out / 'run.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
        report['pass'] = True
    except Exception as exc:
        report['error'] = repr(exc)
        print(str(exc), file=sys.stderr)
    (out / 'run.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    return 0 if report['pass'] else 1


if __name__ == '__main__':
    sys.exit(main())

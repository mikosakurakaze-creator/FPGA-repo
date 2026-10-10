"""Run the already-elaborated single-CNN snapshot after local probe approval.

Invoke only after the local writer RTL overlap gate is explicitly confirmed.
This runner does not elaborate, alter the DDR, or start later stages.
"""
import argparse
import datetime
import json
import subprocess
import time
from pathlib import Path

from prepare_system import SHA


def now():
    return datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).isoformat()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run',required=True,type=Path)
    parser.add_argument('--local-probe-approved',action='store_true',required=True)
    parser.add_argument('--local-evidence',required=True,type=Path)
    args=parser.parse_args()
    run=args.run.resolve()
    assert args.local_probe_approved and args.local_evidence.is_file()
    assert not (run/'exit_status.json').exists()
    assert not (run/'system.log').exists()
    manifest=json.loads((run/'run_manifest.json').read_text())
    assert manifest['config']==dict(FRAMES=1,READ_OUTSTANDING=2,WRITE_OUTSTANDING=2,DDR_DELAY=16,SERVICE_PERIOD=1,POLL_PERIOD=128)
    local=json.loads(args.local_evidence.read_text())
    assert local['complete'] is True
    assert local['ddr_delay']==16 and local['write_outstanding']==2
    assert local['ddr_sha256']==manifest['original_source_manifest']['ddr_model_sha256']
    assert local['scenarios']
    for scenario in local['scenarios'].values():
        assert scenario['numerical_and_protocol_pass'] is True
        assert scenario['external_footprint_data_strobes_identical'] is True
        assert scenario['actual_data_overlap_rows']>0
        assert scenario['row_credit_peak']==2
    for item in manifest['original_source_manifest']['source_files']:
        assert SHA(Path(item['path']))==item['sha256']
    for item in manifest['substitutions']:
        assert SHA(Path(item['candidate']))==item['candidate_sha256']
    for name,digest in manifest['protected_copies'].items():
        assert SHA(run/name)==digest
    assert SHA(run/'system_tb.sv')==manifest['generated_tb_sha256']
    assert (run/'xsim.dir/phase4e_system/xsimk.exe').is_file()
    assert 'Built simulation snapshot phase4e_system' in (run/'elaborate.log').read_text()
    state=dict(status='RUNNING',started=now(),local_gate_approved=True,
               local_evidence=args.local_evidence.resolve().as_posix(),
               local_evidence_sha256=SHA(args.local_evidence),
               kernel_sha256=SHA(run/'xsim.dir/phase4e_system/xsimk.exe'))
    with (run/'console.log').open('w') as output:
        process=subprocess.Popen(['cmd','/c',str(run/'simulate.cmd')],cwd=run,
                                 stdout=output,stderr=subprocess.STDOUT,
                                 creationflags=subprocess.CREATE_NO_WINDOW)
        state['pid']=process.pid
        (run/'process.json').write_text(json.dumps(state,indent=2))
        print('STARTED_SINGLE_CNN',process.pid,flush=True)
        previous=''
        while process.poll() is None:
            path=run/'results/write_stats.csv'
            if path.exists():
                lines=path.read_text().splitlines()
                latest=lines[-1].split(',')[0] if len(lines)>1 else ''
                if latest and latest!=previous:
                    print('PROGRESS_CYCLE',latest,flush=True)
                    previous=latest
            time.sleep(10)
    state.update(status='TERMINAL',finished=now(),exit_code=process.returncode)
    (run/'exit_status.json').write_text(json.dumps(state,indent=2))
    print('TERMINAL_SINGLE_CNN',process.returncode,flush=True)
    raise SystemExit(process.returncode)


if __name__=='__main__':
    main()

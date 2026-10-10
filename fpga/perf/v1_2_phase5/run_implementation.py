"""Protect the Phase 4G delivery and run only its existing project through route."""
import datetime
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET

REPO = Path(__file__).resolve().parents[3]
BASE = Path('E:/HLS/kv260_three_module_v1_2_phase4')
PHASE4G = BASE / 'phase4g'
INTEGRATION = PHASE4G / 'integration_01'
PROJECT = INTEGRATION / 'project'
OUT = BASE / 'phase5/implementation_01'
SCRIPT = REPO / 'fpga/scripts/vivado_three_module_v1_2_impl.tcl'
TZ = datetime.timezone(datetime.timedelta(hours=8))


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def save(name, value):
    (OUT / name).write_text(json.dumps(value, indent=2) + '\n', encoding='utf-8')


def git(*args):
    return subprocess.check_output(['git', *args], cwd=REPO, text=True).strip()


def timestamp():
    return datetime.datetime.now(TZ).isoformat()


def project_configuration():
    root = ET.parse(PROJECT / 'v12_wc.xpr').getroot()
    # Only runtime run bookkeeping may change. Configuration and source sets stay fixed.
    return {tag: ET.tostring(root.find(tag), encoding='unicode')
            for tag in ('Configuration', 'FileSets')}


def prepare():
    if OUT.exists():
        raise RuntimeError('Refusing to overwrite Phase 5 evidence: ' + str(OUT))
    OUT.mkdir(parents=True)
    (OUT / 'reports').mkdir()
    sys.path.insert(0, str(REPO / 'fpga/perf/v1_2_phase4g'))
    from run_integration import verify_inputs
    verify_inputs(INTEGRATION)
    gate = json.loads((INTEGRATION / 'integration_gate.json').read_text())
    if gate['status'] != 'PASS':
        raise RuntimeError('Phase 4G integration gate is not PASS')
    for pathkey, hashkey in [('system_dcp', 'system_dcp_sha256'), ('cnn_dcp', 'cnn_dcp_sha256')]:
        if sha(gate[pathkey]) != gate[hashkey]:
            raise RuntimeError('Authoritative synthesized checkpoint changed: ' + pathkey)
    previous = json.loads((PHASE4G / 'protection_after.json').read_text())
    records = dict(previous['files'])
    recovery = json.loads((BASE / 'recovery_manifest.json').read_text())
    records.update({p: entry['sha256'] for p, entry in recovery['files'].items()})
    for p in PHASE4G.rglob('*'):
        if not p.is_file() or '__pycache__' in p.parts:
            continue
        if PROJECT in p.parents:
            relative = p.relative_to(PROJECT)
            # Protect source/generated design and all completed synthesis artifacts.
            if relative.parts[0] not in ('v12_wc.srcs', 'v12_wc.gen') and not (
                    relative.parts[0] == 'v12_wc.runs' and relative.parts[1].endswith('_synth_1')) and not (
                    relative.parts[0] == 'v12_wc.runs' and relative.parts[1] == 'synth_1'):
                continue
        records.setdefault(p.resolve().as_posix(), sha(p))
    changed = [p for p, digest in records.items() if not Path(p).is_file() or sha(p) != digest]
    if changed:
        raise RuntimeError('Protected Phase 4 inputs changed: ' + repr(changed))
    checkpoint = REPO / 'fpga/reports/v1_2_phase4_checkpoint.md'
    shutil.copyfile(checkpoint, OUT / 'checkpoint_before.md')
    shutil.copyfile(PROJECT / 'v12_wc.xpr', OUT / 'project_before.xpr')
    save('protection_before.json', dict(status='PASS', checked_at=timestamp(), files=records,
         count=len(records), checkpoint_backup_sha256=sha(OUT / 'checkpoint_before.md'),
         project_configuration=project_configuration(),
         git=dict(branch=git('branch', '--show-current'), head=git('rev-parse', 'HEAD'),
                  tracked_diff=git('diff', '--stat'), staged_diff=git('diff', '--cached', '--stat'),
                  status=git('status', '--short', '--untracked-files=all'))))
    print('PHASE5_PROTECTION_BEFORE=PASS FILES=' + str(len(records)), flush=True)


def after():
    before = json.loads((OUT / 'protection_before.json').read_text())
    changed = [p for p, digest in before['files'].items() if not Path(p).is_file() or sha(p) != digest]
    configuration_same = before['project_configuration'] == project_configuration()
    git_same = all(git(*args) == before['git'][key] for key, args in [
        ('branch', ('branch', '--show-current')), ('head', ('rev-parse', 'HEAD')),
        ('tracked_diff', ('diff', '--stat')), ('staged_diff', ('diff', '--cached', '--stat'))])
    exports = [p.as_posix() for p in PROJECT.rglob('*') if p.is_file() and p.suffix.lower() in ('.bit', '.xsa')]
    expected_metadata = []
    unresolved = list(changed)
    if changed:
        # Vivado refreshes generated synthesis run indexes when launching impl_1.
        # A narrow semantic audit permits only those indexes, never design inputs
        # or synthesis artifacts. Keep the initial byte-only failure as evidence.
        initial = OUT / 'protection_after.json'
        archived = OUT / 'protection_after_initial.json'
        if initial.is_file() and not archived.exists():
            shutil.copyfile(initial, archived)
        props = dict(line.rstrip('\n').split('\t', 1) for line in
                     (OUT / 'reports/run_status.tsv').read_text().splitlines()[1:])
        start_epoch = int(props['START_EPOCH'])
        baseline_project = ET.parse(OUT / 'project_before.xpr').getroot()
        runs = {node.get('Id'): node for node in baseline_project.find('Runs')}
        for name in changed:
            path = Path(name)
            if path.name != 'gen_run.xml' or path.parent.parent != PROJECT / 'v12_wc.runs':
                continue
            run_name = path.parent.name
            saved_run = runs.get(run_name)
            if saved_run is None or saved_run.get('Type') != 'Ft3:Synth':
                continue
            root = ET.parse(path).getroot()
            launch_epoch = int(root.get('LaunchTime', '0'))
            strategy = root.find('Strategy/StratHandle')
            saved_strategy = saved_run.find('Strategy/StratHandle')
            if not (root.tag == 'GenRun' and root.get('Id') == run_name and
                    root.get('LaunchPart') == saved_run.get('Part') == 'xck26-sfvc784-2LV-c' and
                    0 < launch_epoch < start_epoch and start_epoch <= path.stat().st_mtime <= start_epoch + 60 and
                    strategy is not None and saved_strategy is not None and
                    all(strategy.get(k) == saved_strategy.get(k) for k in ('Name', 'Flow'))):
                continue
            references = []
            for source in root.findall('./FileSet/File'):
                raw = source.get('Path', '')
                resolved = raw.replace('$PSRCDIR', (PROJECT / 'v12_wc.srcs').as_posix()).replace(
                    '$PGENDIR', (PROJECT / 'v12_wc.gen').as_posix())
                source_path = Path(resolved).resolve().as_posix()
                if '$' in resolved or source_path not in before['files'] or source_path in changed:
                    break
                references.append(source_path)
            else:
                anchors = [path.parent / 'runme.log', path.parent / '.vivado.end.rst']
                anchors += [path.parent / item.get('Name') for item in root.findall('./File')
                            if item.get('Type') in ('PA-TCL', 'RDS-DCP')]
                if not references or len(anchors) != 4 or any(
                        p.resolve().as_posix() not in before['files'] or
                        p.resolve().as_posix() in changed for p in anchors):
                    continue
                entry = dict(path=name, before_sha256=before['files'][name], after_sha256=sha(path),
                             run_id=run_name, part=root.get('LaunchPart'), original_synthesis_launch_epoch=launch_epoch,
                             metadata_mtime_epoch=path.stat().st_mtime, implementation_start_epoch=start_epoch,
                             original_strategy=strategy.attrib, protected_source_references=references,
                             unchanged_synthesis_anchors=[p.as_posix() for p in anchors],
                             before_xml_bytes_archived=False,
                             conclusion='Generated run index refreshed at implementation launch; all referenced design inputs, synthesis Tcl/log/end marker/DCP and project source/configuration remain byte-identical.')
                expected_metadata.append(entry)
                unresolved.remove(name)
        save('generated_metadata_audit.json', dict(status='PASS' if not unresolved else 'FAIL',
             checked_at=timestamp(), raw_changed=changed, unresolved_changes=unresolved,
             expected_generated_run_metadata_changes=expected_metadata,
             limitation='Original index bytes were not copied before launch; original SHA is retained. The original byte-only FAIL is preserved; acceptance uses unchanged source/configuration/synthesis anchors and narrow XML/time validation.'))
    result = dict(status='PASS' if not unresolved and configuration_same and git_same and not exports else 'FAIL',
                  checked_at=timestamp(), count=len(before['files']) - len(expected_metadata),
                  checked_count=len(before['files']), raw_changed=changed, changed=unresolved,
                  expected_generated_run_metadata_changes=expected_metadata,
                  project_configuration_unchanged=configuration_same, git_unchanged=git_same,
                  bitstream_xsa_files=exports)
    save('protection_after.json', result)
    print('PHASE5_PROTECTION_AFTER=' + result['status'], flush=True)
    if result['status'] != 'PASS':
        raise RuntimeError('Post-run protection failed; inspect protection_after.json')


def run():
    runner = OUT / 'run_implementation.cmd'
    runner.write_text('\n'.join([
        '@echo off', 'setlocal', 'set "PROCESSOR_ARCHITECTURE=AMD64"',
        'call "E:\\Xilinx\\2025.2\\data\\settings64.bat" || exit /b 1',
        'call "E:\\Xilinx\\2025.2\\Vivado\\bin\\vivado.bat" -mode batch -notrace -source "' + str(SCRIPT) +
        '" -log "' + str(OUT / 'implementation_vivado.log') + '" -journal "' + str(OUT / 'implementation_vivado.jou') +
        '" -tclargs "' + str(OUT) + '"',
        'exit /b %ERRORLEVEL%', '',
    ]), encoding='utf-8')
    started = timestamp()
    print('PHASE5_IMPLEMENTATION_START=' + started, flush=True)
    with (OUT / 'implementation_console.log').open('wb') as f:
        result = subprocess.run(['cmd.exe', '/d', '/c', str(runner)], cwd=OUT,
                                env={**os.environ, 'PROCESSOR_ARCHITECTURE': 'AMD64'},
                                stdout=f, stderr=subprocess.STDOUT)
    save('exit_status.json', dict(returncode=result.returncode, started_at=started, ended_at=timestamp(),
                                natural_process_exit=True, forced_termination=False, launch_to_step='route_design'))
    print('PHASE5_IMPLEMENTATION_EXIT=' + str(result.returncode), flush=True)
    after()
    if result.returncode:
        raise RuntimeError('Vivado batch did not complete; inspect the retained run/status evidence')


if __name__ == '__main__':
    if len(sys.argv) == 2 and sys.argv[1] == '--after':
        after()
    else:
        prepare()
        run()

"""Derive only six FIFO changes from the CURRENT audited source and routed DCP."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parent


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    ap = argparse.ArgumentParser(__doc__)
    for name in ('parent', 'parent-audit', 'prepared', 'out'):
        ap.add_argument('--' + name, type=Path, required=True)
    a = ap.parse_args()
    parent, out = a.parent.resolve(), a.out.resolve()
    audit = json.loads(a.parent_audit.read_text())
    if not audit['pass'] or not audit.get('independent_axi_revalidation'):
        raise ValueError('Current parent must have a passing corrected independent audit')
    for name, digest in audit['bound_files'].items():
        if sha(name) != digest:
            raise ValueError('Parent audit evidence changed: ' + name)
    prepared = json.loads((a.prepared / 'result.json').read_text())
    for name, digest in prepared['bound_files'].items():
        if sha(name) != digest:
            raise ValueError('Prepared target evidence changed: ' + name)
    if not prepared['pass'] or prepared['parent_checkpoint_sha256'] != audit['checkpoint_sha256']:
        raise ValueError('Six-node selection belongs to another routed parent')
    if len(prepared['nodes']) != 6 or prepared['tight_endpoints'] != 511:
        raise ValueError('Wrong current target coverage')
    manifest = json.loads((parent / 'inputs.json').read_text())
    for name, digest in manifest['source_files'].items():
        if sha(parent / name) != digest:
            raise ValueError('Parent source changed: ' + name)
    if sha(ROOT / 'system_build.tcl') != manifest['source_files']['system_build.tcl']:
        raise ValueError('Do not silently change the integration build script')
    out.mkdir(parents=True, exist_ok=False)
    (out / 'reports').mkdir()
    for name in manifest['source_files']:
        dest = out / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(parent / name, dest)
    shutil.copy2(parent / 'inputs.json', out / 'current_parent_inputs.json')
    shutil.copy2(a.parent_audit, out / 'current_parent_audit.json')
    shutil.copy2(a.prepared / 'result.json', out / 'current_target_selection.json')
    plan = {'parent_build': parent.as_posix(), 'parent_audit': a.parent_audit.resolve().as_posix(),
            'parent_audit_sha256': sha(a.parent_audit), 'parent_checkpoint': prepared['parent_checkpoint'],
            'parent_checkpoint_sha256': prepared['parent_checkpoint_sha256'],
            'targets': {row['key']: row['method'] for row in prepared['nodes']},
            'prepared_nodes_sha256': sha(a.prepared / 'result.json'),
            'algorithm_weights_clocks_addresses_unchanged': True, 'export_allowed': False}
    (out / 'targeted_fifo_plan.json').write_text(json.dumps(plan, indent=2) + '\n')
    shutil.copy2(ROOT / 'targeted_fifo_mapping.py', out / 'targeted_fifo_mapping.py')
    shutil.copy2(ROOT / 'targeted_fifo_policy.tcl', out / 'fifo_output_policy.tcl')
    for name in ('targeted_fifo_plan.json', 'targeted_fifo_mapping.py', 'fifo_output_policy.tcl'):
        manifest['source_files'][name] = sha(out / name)
    manifest['targeted_fifo_variant'] = plan
    (out / 'inputs.json').write_text(json.dumps(manifest, indent=2) + '\n')
    (out / 'gates.json').write_text(json.dumps({'adapter': 'adapter_result.json'}) + '\n')
    shutil.copy2(__file__, out / Path(__file__).name)
    print(json.dumps({'pass': True, 'build': out.as_posix(), 'targets': plan['targets'],
                      'parent_checkpoint_sha256': plan['parent_checkpoint_sha256'], 'export_allowed': False}))


if __name__ == '__main__':
    main()

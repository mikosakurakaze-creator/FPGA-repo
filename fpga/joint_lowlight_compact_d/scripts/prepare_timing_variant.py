"""Make a traceable, isolated RTL timing variant; never edit a frozen IP tree.

Propagate checked D dimensions and map small CNN address arithmetic to fabric.
The optional hold variant also removes a second fixed DSP preadder short path.
This is an experiment, not an accepted replacement delivery.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    p = argparse.ArgumentParser(__doc__)
    p.add_argument('--baseline', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--hold-address', action='store_true',
                   help='Also map the small DW window address add/multiply to fabric')
    a = p.parse_args()
    baseline, out = a.baseline.resolve(), a.out.resolve()
    if out.exists():
        raise ValueError('Preserve prior experiments; use a new output directory')
    manifest = json.loads((baseline / 'inputs.json').read_text())
    for name, digest in manifest['source_files'].items():
        if sha(baseline / name) != digest:
            raise ValueError('Frozen source changed: ' + name)
    cmd = [sys.executable, '-X', 'utf8', '-B', str(ROOT / 'scripts/build_system.py'),
           '--out', str(out), '--stage', 'prepare', '--reuse-adapter', str(baseline)]
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL)
    original = out / 'inputs.json'
    shutil.copy2(original, out / 'inputs_before_timing_variant.json')
    m = json.loads(original.read_text())
    changes = []

    def edit(name, replacements):
        file = out / name
        before = file.read_text()
        after = before
        for old, new in replacements:
            if after.count(old) != 1:
                raise ValueError('Expected one exact RTL anchor: ' + name + ' ' + old)
            after = after.replace(old, new)
        old_sha = sha(file)
        file.write_text(after, encoding='utf-8', newline='\n')
        changes.append({'path': name, 'before_sha256': old_sha, 'after_sha256': sha(file)})
        m['source_files'][name] = sha(file)

    edit('ip/compact_d/hdl/verilog/compact_d_top.v', [
        ('.h(height_read_reg_282),',
         '// Bounds were checked with the full 32-bit values before frame starts.\n'
         '    .h({22\'d0, height_read_reg_282[9:0]}),'),
        ('.w(width_read_reg_276),', '.w({21\'d0, width_read_reg_276[10:0]}),'),
    ])
    edit('ip/cnn/hdl/verilog/zero_dce_cnn_top_ama_addmuladd_6ns_2ns_6ns_6ns_11_4_1.v', [
        ('(* DowngradeIPIdentifiedWarnings="yes" *) module zero_dce_cnn_top_ama_addmuladd_6ns_2ns_6ns_6ns_11_4_1_DSP48_0 (',
         '// Small unpacker address arithmetic: identical pipeline/CE/reset semantics.\n'
         '(* DowngradeIPIdentifiedWarnings="yes", use_dsp="no" *) module zero_dce_cnn_top_ama_addmuladd_6ns_2ns_6ns_6ns_11_4_1_DSP48_0 ('),
    ])
    if a.hold_address:
        edit('ip/cnn/hdl/verilog/zero_dce_cnn_top_am_addmul_5ns_2ns_6ns_11_4_1.v', [
            ('(* DowngradeIPIdentifiedWarnings="yes" *) module zero_dce_cnn_top_am_addmul_5ns_2ns_6ns_11_4_1_DSP48_0(',
             '// Small DW window address arithmetic: preserve every register and CE.\n'
             '(* DowngradeIPIdentifiedWarnings="yes", use_dsp="no" *) module zero_dce_cnn_top_am_addmul_5ns_2ns_6ns_11_4_1_DSP48_0('),
        ])
    # Keep original preparation evidence intact and explicitly bind its successor.
    identity = {'variant': ('bounded_dimensions_fabric_addresses_hold_v2' if a.hold_address
                            else 'bounded_dimensions_fabric_address_v1'),
                'baseline': baseline.as_posix(),
                'baseline_manifest_sha256': sha(baseline / 'inputs.json'),
                'before_manifest_sha256': sha(out / 'inputs_before_timing_variant.json'),
                'changes': changes, 'export_allowed': False,
                'validation_required': ['dimension bounds and controller equivalence',
                                        'CNN address pipeline equivalence',
                                        'fresh synthesis and routed implementation'],
                'no_pipeline_latency_change': True,
                'algorithm_weights_numeric_contract_unchanged': True}
    m['rtl_timing_variant'] = identity
    original.write_text(json.dumps(m, indent=2) + '\n', encoding='utf-8')
    identity['derived_manifest_sha256'] = sha(original)
    (out / 'timing_variant.json').write_text(json.dumps(identity, indent=2) + '\n', encoding='utf-8')
    shutil.copy2(__file__, out / 'prepare_timing_variant.py')
    print(json.dumps(identity, indent=2))


if __name__ == '__main__':
    main()

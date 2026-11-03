"""Classify retained width-converter registers without reclassifying the failed audit."""
import argparse
import csv
import hashlib
import json
from pathlib import Path
import re


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def main():
    ap = argparse.ArgumentParser(__doc__)
    for name in ('build', 'failed-mapping', 'diagnosis', 'out'):
        ap.add_argument('--' + name, type=Path, required=True)
    a = ap.parse_args()
    if a.out.exists():
        raise ValueError('Preserve prior classification')
    result = {'pass': False, 'full_output_register_removal': False, 'bound_files': {}}

    def bind(p, digest=None):
        p = Path(p).resolve()
        actual = sha(p)
        result['bound_files'][p.as_posix()] = actual
        if digest is not None and actual != digest:
            raise ValueError('Mapping evidence changed: ' + str(p))
        return p

    try:
        failed = json.loads(bind(a.failed_mapping / 'result.json').read_text())
        diagnosis = json.loads(bind(a.diagnosis / 'result.json').read_text())
        dcp = bind(a.build / 'joint_synth.dcp')
        for folder, receipt in ((a.failed_mapping, failed), (a.diagnosis, diagnosis)):
            bind(folder / 'console.log', receipt['log_sha256'])
            bind(folder / 'timing_margin.tcl', receipt['script_sha256'])
            if receipt['source_checkpoint_sha256'] != sha(dcp):
                raise ValueError('Diagnostic source differs')
        if failed['pass'] or failed['exit_code'] != 1 or not diagnosis['pass'] or diagnosis['exit_code']:
            raise ValueError('Unexpected diagnostic receipts')
        failure_log = (a.failed_mapping / 'console.log').read_text()
        if 'SmartConnect output generic did not remove the old packed register bank' not in failure_log:
            raise ValueError('Unexpected original audit failure')
        mapping_text = bind(a.failed_mapping / 'fifo_synthesis_mapping.txt').read_text()
        result['preserved_output_decoders'] = int(re.search(r'^PRESERVED_OUTPUT_DECODERS=(\d+)$', mapping_text, re.M)[1])
        if result['preserved_output_decoders'] != 3616:
            raise ValueError('Actual decoder coverage changed')
        for name, digest in diagnosis['reports'].items():
            bind(a.diagnosis / name, digest)
        generated = a.build / 'project/joint_system.gen/sources_1/bd/system/ip'
        sources = list(generated.rglob('*.sv'))
        rows = list(csv.DictReader(bind(a.diagnosis / 'remaining_fifo_output_registers.tsv').open(), delimiter='\t'))
        groups = {}
        for row in rows:
            m = re.match(r'^system_i/(cnn_data_sc|curve_ddr_sc)/inst/s03_nodes/(s03_\w+_node)/inst/', row['cell'])
            request_logic = (row['driver_ref'] == 'LUT4' and
                '/curve_ddr_sc/inst/s03_nodes/s03_w_node/' in row['cell'] and
                '/gen_normal_area.gen_fifo_req.inst_fifo_req/' in row['cell'])
            if not m or row['ref'] != 'FDRE' or (row['driver_ref'] != 'RAMD32' and not request_logic):
                raise ValueError('Unexpected remaining output-register structure')
            top, instance = m.groups()
            key = top + '/' + instance
            if key not in groups:
                bd = list((generated / ('system_' + top + '_0') / 'bd_0/synth').glob('*.v'))
                if len(bd) != 1:
                    raise ValueError('Ambiguous generated module hierarchy')
                content = bind(bd[0]).read_text()
                names = re.findall(r'\b(\w+)\s+' + re.escape(instance) + r'\s*\(', content)
                if len(names) != 1:
                    raise ValueError('Cannot bind remaining node to generated wrapper')
                wrappers = [p for p in sources if p.parent.name == 'synth' and p.stem == names[0]]
                if len(wrappers) != 1:
                    raise ValueError('Ambiguous node wrapper')
                wrapper = bind(wrappers[0]).read_text()
                keys = ('C_FIFO_TYPE', 'C_FIFO_SIZE', 'C_FIFO_OUTPUT_REG', 'C_S_NUM_BYTES_ARRAY', 'C_M_NUM_BYTES_ARRAY')
                params = {}
                for param in keys:
                    match = re.search(r'\.' + param + r'\(([^)]+)\)', wrapper)
                    if not match:
                        raise ValueError('Missing node parameter ' + param)
                    value = match[1]
                    verilog_hex = re.fullmatch(r"\d+'[hH]([0-9a-fA-F]+)", value)
                    params[param] = int(verilog_hex[1], 16) if verilog_hex else int(value, 0)
                if [params[k] for k in keys[:3]] != [0, 5, 0] or \
                   {params[k] for k in keys[3:]} != {4, 16}:
                    raise ValueError('Retained register is not a reviewed 32/128-bit conversion node')
                groups[key] = {'module': names[0], 'parameters': params, 'registers': 0}
            groups[key]['registers'] += 1
        expected = {'cnn_data_sc/s03_ar_node': 117, 'cnn_data_sc/s03_r_node': 135,
                    'curve_ddr_sc/s03_aw_node': 117, 'curve_ddr_sc/s03_b_node': 2,
                    'curve_ddr_sc/s03_w_node': 149}
        if {k: v['registers'] for k, v in groups.items()} != expected or len(rows) != 520:
            raise ValueError('Remaining-register coverage differs from the recorded diagnosis')
        result['groups'] = groups
        result['remaining_registers'] = len(rows)
        result['source_checkpoint_sha256'] = sha(dcp)
        result['scope'] = ('Partial mapping change: 3616 local decoders retained; residual 520 SmartConnect '
                           'registers are confirmed at generated 32/128-bit conversion nodes. '
                           'Original all-registers-removal audit remains failed; routed benefit is unproven.')
        result['pass'] = True
    except Exception as exc:
        result['error'] = str(exc)
        raise
    finally:
        a.out.write_text(json.dumps(result, indent=2) + '\n')
        print(json.dumps({k: v for k, v in result.items() if k != 'bound_files'}, indent=2))


if __name__ == '__main__':
    main()

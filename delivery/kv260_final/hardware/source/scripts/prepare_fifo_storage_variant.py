"""Derive a source-bound FIFO storage/output variant without editing frozen IP.

An address-dependent XOR encoding preserves every stored value at the port, but
puts a real decoder between LUTRAM and its existing output FF. No cycle is added.
The explicit preserved decoder is intentional: a wire/buffer can be optimized
back into the original dedicated intra-slice RAM-to-FF short connection.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[1]
D_NAMES = [f'ip/compact_d/hdl/verilog/compact_d_top_fifo_w128_d32_A{s}.v'
           for s in ('', '_x', '_x0', '_x1')]
D_NAMES += ['ip/compact_d/hdl/verilog/compact_d_top_fifo_w48_d32_A.v']
ARRAY_NAMES = [
    'ip/cnn/hdl/verilog/zero_dce_cnn_top_p_anonymous_namespace_depth_band_actor_source_RAM_2P_LUTRAM_1R1W.v',
    'prepare/hls/impl/ip/hdl/verilog/joint_rgb8_prepare_convert_tiles_original_tile_RAM_2P_LUTRAM_1R1W.v',
]


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def transform(before, *, fifo):
    width = 'DATA_WIDTH' if fifo else 'DataWidth'
    memory, read, write = ('mem', 'raddr', 'waddr') if fifo else ('ram', 'address0', 'address1')
    din, dout = ('din', 'mem_reg') if fifo else ('d1', 'q0')
    # Generated FIFO and array templates have different indentation; preserve it.
    write_expr = f'{memory}[{write}] <= {din};'
    read_expr = f'{dout} <= {memory}[{read}];'
    if before.count(write_expr) != 1 or before.count(read_expr) != 1:
        raise ValueError('Memory template does not match the reviewed 1R1W contract')
    marker = '    reg  [DATA_WIDTH-1:0] mem_reg;' if fifo else '(* ram_style = "distributed" *) reg [DataWidth-1:0] ram[0:AddressRange-1];'
    if before.count(marker) != 1:
        raise ValueError('Expected exactly one memory declaration anchor')
    decoder = f'''

// Internal storage code: encoded[a] = value[a] XOR {{WIDTH{{a[0]}}}}.
// Decode before the existing registered read, preserving CE/reset/read latency.
wire [{width}-1:0] hold_encoded_read = {memory}[{read}];
wire [{width}-1:0] hold_decoded_read;
genvar hold_bit;
generate for (hold_bit = 0; hold_bit < {width}; hold_bit = hold_bit + 1) begin : hold_output_decode
    (* DONT_TOUCH = "yes" *) LUT2 #(.INIT(4'h6)) decode_xor (
        .I0(hold_encoded_read[hold_bit]), .I1({read}[0]), .O(hold_decoded_read[hold_bit]));
end endgenerate
'''
    after = before.replace(marker, marker + decoder)
    after = after.replace(write_expr, f'{memory}[{write}] <= {din} ^ {{{width}{{{write}[0]}}}};')
    return after.replace(read_expr, f'{dout} <= hold_decoded_read;')


def main():
    p = argparse.ArgumentParser(__doc__)
    p.add_argument('--baseline', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    a = p.parse_args()
    baseline, out = a.baseline.resolve(), a.out.resolve()
    manifest = json.loads((baseline/'inputs.json').read_text())
    # Verify all inherited inputs before creating a successor.
    for name, digest in manifest['source_files'].items():
        if sha(baseline/name) != digest:
            raise ValueError('Frozen input changed: '+name)
    if not json.loads((baseline/'synth_result.json').read_text())['pass']:
        raise ValueError('The parent synthesis was not successful')
    out.mkdir(parents=True, exist_ok=False)
    (out/'reports').mkdir()
    for name in manifest['source_files']:
        dest = out/name
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(baseline/name, dest)
    shutil.copy2(baseline/'inputs.json', out/'parent_inputs.json')
    shutil.copy2(baseline/'timing_variant.json', out/'parent_timing_variant.json')
    shutil.copy2(baseline/'synth_result.json', out/'parent_synth_result.json')
    shutil.copy2(__file__, out/Path(__file__).name)
    changes = []
    for name in D_NAMES+ARRAY_NAMES:
        file = out/name
        before = file.read_text()
        before_sha = sha(file)
        after = transform(before, fifo=name in D_NAMES)
        file.write_text(after, encoding='utf-8', newline='\n')
        changes.append({'path':name, 'before_sha256':before_sha, 'after_sha256':sha(file),
                        'kind':'address_xor_storage_with_preserved_output_decoder'})
        manifest['source_files'][name] = sha(file)
    # Freeze the actual current build script, including any explicitly reviewed
    # SmartConnect policy hook, rather than inheriting an obsolete copy.
    shutil.copy2(ROOT/'scripts/system_build.tcl', out/'system_build.tcl')
    manifest['source_files']['system_build.tcl'] = sha(out/'system_build.tcl')
    shutil.copy2(ROOT/'scripts/fifo_output_policy.tcl',out/'fifo_output_policy.tcl')
    manifest['source_files']['fifo_output_policy.tcl']=sha(out/'fifo_output_policy.tcl')
    identity = {'variant':'fifo_address_encoded_storage_v1', 'baseline':baseline.as_posix(),
                'baseline_manifest_sha256':sha(baseline/'inputs.json'), 'changes':changes,
                'algorithm_weights_numeric_contract_unchanged':True,
                'local_memory_read_latency_unchanged':True,
                'fifo_capacity_and_handshake_unchanged':True,
                'smartconnect_output_policy':'Disable existing vendor output register on 32-entry LUTRAM nodes; transaction latency may change',
                'clocks_mhz':[100,200], 'export_allowed':False,
                'validation_required':['cycle-by-cycle old/new FIFO and RAM simulation',
                                       'actual synthesized decoder/memory mapping audit',
                                       'new joint route, setup/hold and independent reopen']}
    manifest['fifo_storage_variant'] = identity
    (out/'inputs.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
    identity['derived_manifest_sha256'] = sha(out/'inputs.json')
    (out/'fifo_storage_variant.json').write_text(json.dumps(identity,indent=2)+'\n',encoding='utf-8')
    # Adapter success is historical. The derived RTL requires its own gate.
    (out/'gates.json').write_text(json.dumps({'adapter':'adapter_result.json'})+'\n')
    print(json.dumps({'build':out.as_posix(),'changed_memory_templates':len(changes),
                      'source_manifest_sha256':sha(out/'inputs.json'),'export_allowed':False}))


if __name__ == '__main__':
    main()

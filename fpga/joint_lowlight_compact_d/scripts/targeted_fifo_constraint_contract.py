"""Permit exactly the eight provenance substitutions caused by four XPM FIFOs.

Actual timing commands, their scopes/order, and reset-cut multiplicities remain
identical. This is specific to the audited Vivado 2025.2 synchronous FIFO change.
"""
from collections import Counter

from audit_fifo_storage_timing import compiled_contract


BRAM_KEYS = frozenset(sc + '/m00_r_node' for sc in
    ('bilinear_ddr_sc', 'cnn_data_sc', 'cnn_model_sc', 'curve_ddr_sc'))
VENDOR_XPM = 'd:/vivado/2025.2/data/ip/xpm/'


def provenance_pairs(keys):
    if frozenset(keys) != BRAM_KEYS or len(keys) != 4:
        raise ValueError('Only the four current R FIFO nodes can change provenance')

    def source(script, scope, braces):
        path = VENDOR_XPM + script
        scope = '{' + scope + '}' if braces else scope
        return ('set_property SRC_FILE_INFO {cfile:' + path + ' rfile:' + path +
                ' id:ENUMERATION order:LATE scoped_inst:' + scope +
                ' unmanaged:yes rxprname:' + path + '} [current_design]')

    pairs = []
    for key in sorted(keys):
        sc, node = key.split('/')
        prefix = f'system_i/{sc}/inst/m00_nodes/{node}/inst/inst_mi_handler/'
        for branch in ('gen_normal_area.gen_fifo_req.inst_fifo_req/', 'gen_normal_area.inst_fifo_node_payld/'):
            old = prefix + branch + 'gen_xpm_memory_fifo.inst_fifo/gen_mem_rep[0].inst_xpm_memory'
            new = prefix + branch + 'gen_xpm_fifo_wrapper.inst_fifo/gen_xpm_fifo_sync.inst_xpm_fifo_sync'
            pairs.append((source('xpm_memory/tcl/xpm_memory_xdc.tcl', old, True),
                          source('xpm_fifo/tcl/xpm_fifo_rst.tcl', new, False)))
    return pairs


def line_provenance(source, numbers):
    return Counter((source, 'set_property src_info {type:SCOPED_XDC file:ENUMERATION line:' +
                    str(n) + ' export:INPUT save:NONE read:READ} [current_design]') for n in numbers)


def compare_targeted_compiled(old, new, keys):
    a, b = compiled_contract(old), compiled_contract(new)
    if a == b:
        return {'identical': True, 'provenance_substitutions': 0}
    if a[:2] != b[:2]:
        raise ValueError('Actual timing commands, order, scopes or reset exceptions changed')
    pairs = provenance_pairs(keys)
    before, after, before_lines, after_lines = Counter(), Counter(), Counter(), Counter()
    for first, second in pairs:
        before[first] += 1
        after[second] += 1
        before_lines.update(line_provenance(first, [*range(1, 47), 49, 53, 67]))
        after_lines.update(line_provenance(second, [*range(1, 47), 49, 56, 57]))
    if a[2] - b[2] != before or b[2] - a[2] != after:
        raise ValueError('Unexpected source provenance outside the eight exact FIFO substitutions')
    if a[3] - b[3] != before_lines or b[3] - a[3] != after_lines:
        raise ValueError('Unexpected source-line provenance or multiplicity change')
    return {'identical': False, 'actual_timing_commands_unchanged': True,
            'provenance_substitutions': 8, 'provenance_line_substitutions': 392}

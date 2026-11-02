"""Transform only the current routed candidate's selected FIFO wrappers.

R/W channels may use the vendor XPM FIFO BRAM backend with registered output.
Command channels keep LUTRAM and get two preserved identity LUTs on payload.
No sequential logic, handshake, payload encoding or AXI register address is added
by the identity buffer. Real vendor simulation and synthesis remain required.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re


def parameter(text, name):
    values = re.findall(r'\.' + name + r'\((\d+)\)', text)
    if len(values) != 1:
        raise ValueError('Expected one literal node parameter: ' + name)
    return int(values[0])


def set_parameter(text, name, value):
    old = parameter(text, name)
    text = text.replace(f'.{name}({old})', f'.{name}({value})')
    return text.replace(f'{name}={old},', f'{name}={value},')


def output_register_off(text):
    if parameter(text, 'C_FIFO_TYPE') != 0 or parameter(text, 'C_FIFO_SIZE') != 5:
        raise ValueError('Only inherited 32-entry LUTRAM nodes may be transformed')
    return set_parameter(text, 'C_FIFO_OUTPUT_REG', 0)


def bram_output(text):
    if parameter(text, 'C_CHANNEL') not in (0, 1):
        raise ValueError('Vendor forbids BRAM on AR/AW/B command channels')
    if parameter(text, 'C_FIFO_TYPE') != 0 or parameter(text, 'C_FIFO_SIZE') != 5:
        raise ValueError('Unexpected parent FIFO storage')
    for name, value in [('C_FIFO_IP', 2), ('C_FIFO_TYPE', 1),
                        ('C_FIFO_SIZE', 9), ('C_FIFO_OUTPUT_REG', 1)]:
        text = set_parameter(text, name, value)
    return text


def buffered_payload(text):
    if parameter(text, 'C_CHANNEL') not in (2, 3, 4):
        raise ValueError('The targeted identity buffer is for command channels')
    if parameter(text, 'C_FIFO_TYPE') != 0 or parameter(text, 'C_FIFO_SIZE') != 5 \
       or parameter(text, 'C_FIFO_OUTPUT_REG') != 0:
        raise ValueError('Expected current unregistered 32-entry LUTRAM output')
    match = re.search(r'output wire \[(\d+) : 0\] m_sc_payld;', text)
    if not match or text.count('.m_sc_payld(m_sc_payld)') != 1 or text.count('endmodule') != 1:
        raise ValueError('Unexpected generated payload port/connection')
    high = int(match[1])
    anchor = re.search(r'^  sc_node_v1_0_\d+_top #\(', text, re.M)
    if not anchor:
        raise ValueError('Missing generated vendor instance anchor')
    block = f'''
// Identity data path only; original vendor send/recv/req/info are untouched.
wire [{high}:0] hold_raw_payload;
wire [{high}:0] hold_middle_payload;
genvar hold_payload_bit;
generate for (hold_payload_bit=0; hold_payload_bit<={high}; hold_payload_bit=hold_payload_bit+1) begin : hold_payload_delay
    (* DONT_TOUCH = "yes" *) LUT1 #(.INIT(2'h2)) delay_first (
        .I0(hold_raw_payload[hold_payload_bit]), .O(hold_middle_payload[hold_payload_bit]));
    (* DONT_TOUCH = "yes" *) LUT1 #(.INIT(2'h2)) delay_second (
        .I0(hold_middle_payload[hold_payload_bit]), .O(m_sc_payld[hold_payload_bit]));
end endgenerate
'''
    return text[:anchor.start()] + block + text[anchor.start():].replace(
        '.m_sc_payld(m_sc_payld)', '.m_sc_payld(hold_raw_payload)')


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def transform(text, method):
    current = output_register_off(text)
    if method == 'bram':
        return bram_output(current)
    if method == 'buffer':
        return buffered_payload(current)
    if method == 'inherit':
        return current
    raise ValueError('Unknown FIFO mapping method')


def probe(root):
    """Prepare a new disposable probe, never an old generated project."""
    records, lut_count = [], 0
    for file in root.joinpath('project').rglob('*.sv'):
        if file.parent.name not in ('sim', 'synth'):
            continue
        text = file.read_text()
        if not re.search(r'sc_node_v1_0_\d+_top\s*#\(', text):
            continue
        if parameter(text, 'C_FIFO_TYPE') != 0 or parameter(text, 'C_FIFO_SIZE') != 5:
            continue
        channel = parameter(text, 'C_CHANNEL')
        method = 'bram' if channel == 0 else 'buffer' if channel in (2, 4) else 'inherit'
        if method == 'buffer' and file.parent.name == 'synth':
            lut_count += 2 * parameter(text, 'C_PAYLD_WIDTH')
        backup = root/'before'/file.relative_to(root/'project')
        backup.parent.mkdir(parents=True, exist_ok=True)
        backup.write_bytes(file.read_bytes())
        file.write_text(transform(text, method), encoding='utf-8', newline='\n')
        records.append({'path':file.as_posix(), 'backup':backup.as_posix(),
                        'before':sha(backup), 'after':sha(file), 'method':method})
    if len(records) != 10:
        raise ValueError('Incomplete five-channel probe')
    (root/'probe_source_identity.json').write_text(json.dumps(records,indent=2)+'\n')
    (root/'probe_helper_sha256.txt').write_text(sha(__file__)+'\n')
    print(f'buffer_luts {lut_count} changed_nodes 3')


def policy(root, verify=False):
    plan = json.loads((root/'targeted_fifo_plan.json').read_text())
    parent = Path(plan['parent_build'])
    targets = plan['targets']
    path = root/'targeted_generated_sources.json'
    if verify:
        records = json.loads(path.read_text())
        for row in records:
            backup, file = root/row['backup'], root/row['path']
            if sha(backup) != row['before'] or sha(file) != row['after'] \
               or sha(parent/row['path']) != row['parent_current_sha256']:
                raise ValueError('Generated FIFO identity changed: '+row['path'])
            if file.read_text() != transform(backup.read_text(), row['method']):
                raise ValueError('Generated FIFO policy changed: '+row['path'])
        print('TARGETED_FIFO_POLICY_VERIFIED='+str(len(records)))
        return
    if path.exists():
        raise ValueError('Preserve the prior source policy application')
    records, changed = [], Counter()
    generated = root/'project/joint_system.gen/sources_1/bd/system'
    for file in generated.rglob('*.sv'):
        if file.parent.name not in ('sim', 'synth'):
            continue
        before = file.read_text()
        if not re.search(r'sc_node_v1_0_\d+_top\s*#\(', before):
            continue
        if parameter(before, 'C_FIFO_TYPE') != 0 or parameter(before, 'C_FIFO_SIZE') != 5:
            continue
        match = re.search(r'/ip/system_(\w+_sc)_0/', file.as_posix())
        if not match:
            raise ValueError('Cannot identify generated SmartConnect')
        xci = json.loads((file.parent.parent/(file.stem+'.xci')).read_text())
        node = xci['ip_inst']['cell_name']
        key = match[1]+'/'+node
        method = targets.get(key, 'inherit')
        rel = file.relative_to(root)
        parent_file = parent/rel
        if parent_file.read_text() != output_register_off(before):
            raise ValueError('Fresh generated node differs from CURRENT parent: '+key)
        backup = root/'fifo_generated_before'/rel
        backup.parent.mkdir(parents=True,exist_ok=True)
        backup.write_bytes(file.read_bytes())
        file.write_text(transform(before, method),encoding='utf-8',newline='\n')
        records.append({'path':rel.as_posix(),'backup':backup.relative_to(root).as_posix(),
                        'before':sha(backup),'after':sha(file),'key':key,'method':method,
                        'parent_current_sha256':sha(parent_file)})
        if method != 'inherit':
            changed[key] += 1
    if len(records) != 132 or dict(changed) != {key:2 for key in targets}:
        raise ValueError('Targeted source coverage is incomplete: '+str(changed))
    path.write_text(json.dumps(records,indent=2)+'\n')
    # Existing create-stage gate expects this portable Tcl list of pairs.
    pairs = ['{'+str(root/r['path']).replace('\\','/')+'} {'+
             str(root/r['backup']).replace('\\','/')+'}' for r in records]
    (root/'fifo_output_override_records.list').write_text('\n'.join('{'+r+'}' for r in pairs)+'\n')
    print('TARGETED_FIFO_POLICY_APPLIED='+str(len(changed)))
    policy(root, verify=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument('mode',choices=('probe','apply','verify'))
    parser.add_argument('root',type=Path)
    args=parser.parse_args()
    if args.mode == 'probe':
        probe(args.root.resolve())
    else:
        policy(args.root.resolve(), verify=args.mode=='verify')

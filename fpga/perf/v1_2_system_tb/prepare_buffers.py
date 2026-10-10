"""Create a shared, guarded DDR map with two slots and independent lifetimes."""
from pathlib import Path
import hashlib
import json

RUN = Path('E:/HLS/kv260_three_module_v1_2_phase4')
BASE = 0x10000000
ALIGNMENT = 4096


def main():
    data = RUN / 'data'
    assert (data / 'golden_manifest.json').exists()
    assert 'FULL_FIXED_POINT_VENDOR_GOLDEN_PASS' in (RUN / 'golden_vendor.log').read_text()
    specs = [('weights',10075,'weights_int8.bin'), ('bias',1944,'bias_int32.bin'),
             ('frac',486,'weight_frac.bin'), ('lut',8194,'tanh_lut_q15.bin'),
             ('workspace',2442240,None)]
    for name, size, source in [('cnn_input',38160,'input_q14.bin'),('a_low',38160,None),
                               ('a_full',5495040,None),('model_input',5495040,'model_input_q14.bin'),
                               ('enhanced',5495040,None)]:
        for slot in range(2):
            specs.append((name+str(slot),size,source))
    regions = {}
    cursor = 0
    for name,size,source in specs:
        cursor = ((cursor + ALIGNMENT - 1) // ALIGNMENT) * ALIGNMENT
        regions[name] = dict(base=BASE+cursor+256, offset=cursor+256, bytes=size,
                             source=source, prefix_guard_bytes=256, suffix_guard_bytes=256,
                             alignment_bytes=16)
        cursor += 256 + size + 256
    total = ((cursor+15)//16)*16
    memory = bytearray(bytes.fromhex('3930') * (total//2))
    for name,r in regions.items():
        if r['source']:
            content = (data / r['source']).read_bytes()
            assert len(content) == r['bytes']
            memory[r['offset']:r['offset']+r['bytes']] = content
        assert r['base'] % 16 == 0 and BASE <= r['base'] < 0x80000000
    ordered = sorted(regions.values(), key=lambda r:r['base'])
    assert all(a['base']+a['bytes']+256 <= b['base']-256 for a,b in zip(ordered,ordered[1:]))
    (RUN / 'shared_ddr.hex').write_text(''.join(f'{int.from_bytes(memory[i:i+16],"little"):032x}\n'
                                               for i in range(0,total,16)))
    for name, source in [('low','expected_a_low_q14.bin'),('full','expected_a_full_q14.bin'),('enhanced','expected_enhanced_q14.bin')]:
        content = (data/source).read_bytes()
        (RUN / ('golden_'+name+'.hex')).write_text(''.join(f'{int.from_bytes(content[i:i+2],"little"):04x}\n'
                                                         for i in range(0,len(content),2)))
    result = dict(ddr_base=BASE, memory_bytes=total, memory_words128=total//16, regions=regions,
                  non_overlap=True, model_frame='night_01', alignment_bytes=16,
                  workspace_slots=1, intermediate_and_io_slots=2,
                  lifetime={'a_low':'CNN start through Bilinear done',
                            'a_full':'Bilinear start through Curve done',
                            'cnn_input':'host prepare through CNN done',
                            'model_input':'host prepare through Curve done',
                            'enhanced':'Curve start through host numerical check/release',
                            'workspace':'single CNN instance start through done'},
                  shared_memory_sha256=hashlib.sha256(memory).hexdigest())
    (RUN / 'buffer_map.json').write_text(json.dumps(result,indent=2))
    print('Guarded shared DDR ready:', total, 'bytes;', len(regions), 'non-overlapping regions.')


if __name__ == '__main__':
    main()

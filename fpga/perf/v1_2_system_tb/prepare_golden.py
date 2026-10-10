"""Full-size Phase 4 raw golden from the frozen V1 fixed-point arithmetic.

All image-derived inputs are existing numerical tensors, never decoded images.
Checks CNN preprocessing consistency before building full Bilinear/Curve goldens.
"""
from array import array
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import struct
import sys

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[3]
RUN = Path('E:/HLS/kv260_three_module_v1_2_phase4')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    data = RUN / 'data'
    assert not (data / 'golden_manifest.json').exists()
    source = Path('E:/HLS/wzh_cnn_alow_audit_b364692/outputs/zero_dce_pp/quantization/integer/wzh_model_input_fp32.f32')
    payload = source.read_bytes()
    assert len(payload) == 2747520 * 4
    full = array('h')
    for (v,) in struct.iter_unpack('<f', payload):
        assert math.isfinite(v) and 0 <= v <= 1
        full.append(min(32767, max(-32768, math.floor(v * 16384 + .5))))
    assert sys.byteorder == 'little'
    (data / 'model_input_q14.bin').write_bytes(full.tobytes())
    low_input = array('h', (data / 'input_q14.bin').read_bytes())
    preprocessing_mismatches = 0
    spec = importlib.util.spec_from_file_location('fixed_v1', ROOT / 'fpga/reference/fixed_point_v1/arithmetic.py')
    reference = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(reference)
    for c in range(3):
        for y in range(60):
            for x in range(106):
                p = c * 720 * 1272 + (12 * y + 5) * 1272 + 12 * x + 5
                val = reference.nearest_even_shift(full[p] + full[p+1] + full[p+1272] + full[p+1273], 2)
                preprocessing_mismatches += val != low_input[(c * 60 + y) * 106 + x]
    assert preprocessing_mismatches == 0, 'Full/low inputs are not the same preprocessed frame'
    low = array('h', (data / 'expected_a_low_q14.bin').read_bytes())
    a_full = array('h')
    for c in range(3):
        for y in range(720):
            for x in range(1272):
                a_full.append(reference.bilinear_pixel_raw(low, 60, 106, c, y, x))
        print('Bilinear golden channel', c, 'complete', flush=True)
    enhanced = array('h', (reference.curve_pixel_raw(x, a) for x, a in zip(full, a_full)))
    (data / 'expected_a_full_q14.bin').write_bytes(a_full.tobytes())
    (data / 'expected_enhanced_q14.bin').write_bytes(enhanced.tobytes())
    paths = [data / n for n in ('input_q14.bin', 'expected_a_low_q14.bin', 'model_input_q14.bin',
                               'expected_a_full_q14.bin', 'expected_enhanced_q14.bin')]
    result = dict(real_frame='night_01', full_model_source=str(source), full_model_source_sha256=sha(source),
                  arithmetic_source=str(ROOT / 'fpga/reference/fixed_point_v1/arithmetic.py'),
                  arithmetic_sha256=sha(ROOT / 'fpga/reference/fixed_point_v1/arithmetic.py'),
                  protocol_sha256=sha(ROOT / 'fpga/docs/v1_fixed_point_protocol.json'),
                  preprocessing_mismatches=preprocessing_mismatches,
                  a_low_scalars=len(low), a_full_scalars=len(a_full), enhanced_scalars=len(enhanced),
                  files={p.name: dict(bytes=p.stat().st_size, sha256=sha(p)) for p in paths})
    (data / 'golden_manifest.json').write_text(json.dumps(result, indent=2))
    print('Full-size fixed-point golden PASS, same-frame preprocessing exact.', flush=True)


if __name__ == '__main__':
    main()

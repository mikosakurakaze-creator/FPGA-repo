"""Prepare isolated Phase 4 inputs; never write frozen HLS sources or IPs."""
from pathlib import Path
import hashlib
import json
import shutil

ROOT = Path(__file__).resolve().parents[3]
RUN = Path('E:/HLS/kv260_three_module_v1_2_phase4')


def main():
    assert (RUN / 'recovery_manifest.json').is_file()
    data = RUN / 'data'
    data.mkdir(exist_ok=False)
    for name in ('input_q14.bin', 'weights_int8.bin', 'bias_int32.bin', 'weight_frac.bin',
                 'tanh_lut_q15.bin', 'expected_a_low_q14.bin'):
        shutil.copy2(Path('E:/HLS/cnn_v1_2_phase3b_r4/data') / name, data / name)
    cfg = (ROOT / 'fpga/hls/zero_dce_cnn_v1_2_30fps/candidate_b_rowstream_r4/hls_config.cfg').read_text()
    cfg = cfg.replace('csim.argv=E:/HLS/cnn_v1_2_phase3b_r4/data', 'csim.argv=' + data.as_posix())
    (RUN / 'r4_hls_config.cfg').write_text(cfg)
    iprepo = RUN / 'ip_repo'
    iprepo.mkdir(exist_ok=False)
    stable = {
        'bilinear': Path('E:/HLS/fpga_bilinear_fixed16_buffered/fpga_bilinear_fixed16_buffered/hls/impl/ip'),
        'curve': Path('E:/HLS/fpga_curve_fixed16/fpga_curve_fixed16/hls/impl/ip'),
    }
    copied = {}
    for name, src in stable.items():
        dest = iprepo / name
        shutil.copytree(src, dest)
        hashes = {str(p.relative_to(src)): hashlib.sha256(p.read_bytes()).hexdigest()
                  for p in src.rglob('*') if p.is_file()}
        assert all(hashlib.sha256((dest / n).read_bytes()).hexdigest() == s for n, s in hashes.items())
        copied[name] = dict(source=str(src), copy=str(dest), files=hashes)
    (RUN / 'stable_ip_copies.json').write_text(json.dumps(copied, indent=2))
    # Clone only the saved BD, not the old project/cache/runs. Its generated
    # output path is explicitly redirected to the independent V1.2 project.
    bd = ROOT / 'fpga/vivado/three_module_integration_v1_1/three_module_integration_v1_1.srcs/sources_1/bd/system/system.bd'
    design = json.loads(bd.read_text())
    info = design['design']['design_info']
    info['gen_directory'] = '../../../../three_module_integration_v1_2.gen/sources_1/bd/system'
    (RUN / 'system_seed.bd').write_text(json.dumps(design, indent=2))
    print('Prepared independent data, HLS config, stable IP copies and V1.2 BD seed.')


if __name__ == '__main__':
    main()

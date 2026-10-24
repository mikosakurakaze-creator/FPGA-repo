"""Assemble a new local B-group candidate handoff; never upload or overwrite."""
import argparse
import json
from pathlib import Path
import shutil
import zipfile
from .io import sha256, write_json
from .verify_delivery import verify


def main():
    p = argparse.ArgumentParser(__doc__)
    p.add_argument('--runs', required=True); p.add_argument('--out', required=True)
    a = p.parse_args()
    runs, out = Path(a.runs).resolve(), Path(a.out).resolve()
    archive = out.with_suffix('.zip')
    if out.exists() or archive.exists(): raise FileExistsError('Preserve previous delivery')
    suite = runs / 'run_003'
    status = json.loads((suite / 'suite_status.json').read_text())
    assert all(c['exit_status'] == 0 for c in status['commands'])
    assert json.loads((suite / 'compare_independent.json').read_text())['exact']
    assert json.loads((suite / 'compare_repeat.json').read_text())['exact']
    assert all(json.loads((suite / 'export_determinism.json').read_text()).values())
    for name in ['final_foggy001', 'final_720p']:
        report = json.loads((runs / name / 'report.json').read_text())
        assert len(report['nodes']) == 320
        assert sum(n['saturated_low'] + n['saturated_high'] for n in report['nodes']) == 0
    assert json.loads((runs / 'compare_fpga_final/status.json').read_text())['all_expectations_met']
    out.mkdir(parents=True)
    package_root = Path(__file__).parent
    shutil.copytree(package_root, out / 'griddehaze_fixed', ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
    shutil.copytree(suite / 'w16cal', out / 'package')
    shutil.copytree(suite / 'w8cal', out / 'alternative_int8')
    cases = {'w16cal_random': 'random', 'black': 'black', 'white': 'white', 'channel': 'channel',
             'impulse': 'impulse', 'size_4x4': 'size_4x4', 'size_32x48': 'size_32x48', 'size_34x46': 'size_34x46'}
    for src, dest in cases.items(): shutil.copytree(suite / src, out / 'golden' / dest)
    for name, dest in [('final_foggy001', 'foggy001_675x1280'), ('final_720p', 'random_720x1280')]:
        shutil.copytree(runs / name, out / 'golden' / dest)
    shutil.copytree(runs / 'validation15', out / 'evidence' / 'validation15')
    shutil.copytree(runs / 'compare_fpga_final', out / 'evidence' / 'compare_fpga_final')
    shutil.copytree(runs / 'commands', out / 'evidence' / 'commands')
    shutil.copytree(suite / 'commands', out / 'evidence' / 'final_suite_commands')
    # Keep original run records and hashes, without copying environments, source
    # weights, datasets, caches, or large repeated intermediate tensors.
    for name in ['suite_status.json', 'compare_independent.json', 'compare_repeat.json', 'export_determinism.json',
                 'plan_33x47.json', 'plan_675x1280.json', 'plan_720x1280.json',
                 'final-parameter-audit.json', 'final-byte-audit.json', 'w8cal_audit.json', 'w16cal_audit.json']:
        shutil.copy2(suite / name, out / 'evidence' / name)
    for name in ['validation_summary.json', 'compare_original_random.json', 'parameter_audit.json']:
        shutil.copy2(runs / 'clean_reproduce' / name, out / 'evidence' / ('clean_' + name))
    for version in ['run_001', 'run_002']:
        for f in (runs / version).glob('*random/report.json'):
            dest = out / 'evidence' / 'superseded' / version / (f.parent.name + '.json')
            dest.parent.mkdir(parents=True, exist_ok=True); shutil.copy2(f, dest)
    (out / 'provenance').mkdir()
    shutil.copy2(runs / 'userdata/splits.json', out / 'provenance/splits.json')
    shutil.copy2(runs / 'source/provenance.json', out / 'provenance/upstream.json')
    shutil.copy2(runs / 'source/tree.json', out / 'provenance/upstream_tree.json')
    for f in runs.glob('install*.log'): shutil.copy2(f, out / 'provenance' / f.name)
    shutil.copy2(package_root / 'README.md', out / 'README.md')
    quick = '''# 给 wzh 的开工入口（候选，视觉/ABI 待确认）

首选 package/，INT16 权重与逐节点 INT16 激活；alternative_int8/ 是单独候选，不能混用 Golden。
先读 griddehaze_fixed/docs/INTERFACE.md 和 AUDIT.md。

安装依赖后，从此解压目录执行：

    python -m griddehaze_fixed.verify_delivery .
    python -m griddehaze_fixed.fetch outputs/source
    python -m griddehaze_fixed.cli run --package package --source outputs/source --image golden/random/input.png --out outputs/replay_random
    python -m griddehaze_fixed.cli compare golden/random outputs/replay_random --report outputs/replay_compare.json

Golden/random 保存320节点原始文件；完整原尺寸输入/输出在 golden/foggy001_675x1280 与 random_720x1280。
完整图节点保留哈希/范围/饱和，非全部原始中间张量。FPGA raw 比较命令见 README。
未做真板/HLS/RTL/性能测试；请确认位宽、每节点尺度、反卷积目标尺寸、DDR/DMA/寄存器 ABI 后集成。
本包仅在本地生成供主人转交；未自动上传或联系任何队友。
'''
    (out / 'WZH_START_HERE.md').write_text(quick, encoding='utf-8')
    m = json.loads((out / 'package/manifest.json').read_text())
    files = [{'path': p.relative_to(out).as_posix(), 'bytes': p.stat().st_size, 'sha256': sha256(p)}
             for p in sorted(out.rglob('*')) if p.is_file()]
    write_json(out / 'DELIVERY.json', {'format_version': 'griddehaze-a-handoff-v1',
               'bundle_id': m['identity']['bundle_id'], 'status': 'numerically_verified_candidate_visual_and_b_abi_pending',
               'hardware_test': False, 'files': files})
    verify(out)
    with zipfile.ZipFile(archive, 'x', compression=zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for f in sorted(out.rglob('*')):
            if f.is_file(): z.write(f, f.relative_to(out).as_posix())
    with zipfile.ZipFile(archive) as z:
        assert z.testzip() is None
    checksum = archive.with_suffix('.zip.sha256')
    checksum.write_text(f'{sha256(archive)}  {archive.name}\n', encoding='utf-8')
    print(json.dumps({'archive': str(archive), 'bytes': archive.stat().st_size, 'sha256': sha256(archive),
                      'files': len(files) + 1, 'bundle_id': m['identity']['bundle_id']}, indent=2))


if __name__ == '__main__': main()

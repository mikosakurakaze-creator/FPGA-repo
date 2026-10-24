"""Record recovered native outputs without overwriting the failed launch record."""
import json
from pathlib import Path
from preflight import ROOT, sha, save

out = ROOT / 'work/frame_native04'
original = json.loads((out / 'result.json').read_text(encoding='utf-8'))
log = out / 'native_resumed.log'
if 'ALL_FRAME_CASES_PASS cases=8 negative_tests=11' not in log.read_text(encoding='utf-8'):
    raise RuntimeError('recovered run completion marker absent')
cases = ['random', 'black', 'white', 'channel', 'impulse', 'size_4x4', 'size_32x48', 'size_34x46']
results = []
for i, name in enumerate(cases):
    golden = ROOT / 'a_candidate/golden' / name
    meta = json.loads((golden / 'report.json').read_text(encoding='utf-8'))
    for j, node in enumerate(meta['nodes']):
        actual = out / f'case{i}_node{j}.raw'
        if actual.stat().st_size != node['bytes'] or sha(actual) != node['sha256']:
            raise RuntimeError(f'node mismatch {name}/{j}')
    actual = out / f'case{i}_output.raw'
    expected = json.loads((golden / 'output.json').read_text(encoding='utf-8'))
    if actual.stat().st_size != expected['bytes'] or sha(actual) != expected['sha256']:
        raise RuntimeError('final output mismatch ' + name)
    results.append(dict(case=name, nodes=320, exact=True, output_sha256=sha(actual)))
report = dict(pass_result=True, verification_kind='recovered_native_outputs',
              original_result_preserved=True, original_result_sha256=sha(out / 'result.json'),
              original_launch_error=original.get('error'), log_sha256=sha(log),
              executable_sha256=sha(out / 'test_frame.exe'), cases=results,
              actual_node_files_checked=2560, negative_tests=11,
              limitations=['The resumed process exit code 0 was observed at execution time; this recorder does not rerun it.',
                           'No claim about why antivirus treatment changed or whether anyone allowed the binary.',
                           'Host integer execution, not RTL, implementation or a board result.'])
save(out / 'recovered_result.json', report)
print(json.dumps({k:v for k,v in report.items() if k != 'cases'}, indent=2))

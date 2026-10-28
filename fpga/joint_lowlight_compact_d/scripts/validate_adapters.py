"""Independent rational Golden, full-frame Host/CSim, and HLS IP export.

All generated tensors/tool output stay outside Git. No model training/inference,
implementation, Git mutation, or board access is performed by this script.
"""
from array import array
import argparse
from fractions import Fraction
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import struct
import subprocess
import sys
import time
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
H, W = 720, 1272
COUNT = 3 * H * W
D_REF = '8c202508d267151c4ae034975b17947818be7865'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def prepare(out, lowlight):
    fixtures = out / 'fixtures'
    fixtures.mkdir(exist_ok=False)
    # Nontrivial colour/row/column pattern exercises all 256 inputs, plane/row
    # boundaries and the final pixel; reference uses exact Fraction arithmetic.
    rgb = bytearray(COUNT)
    for y in range(H):
        for x in range(W):
            p = 3 * (y * W + x)
            rgb[p:p+3] = bytes(((x + 17*y) % 256, (3*x + y + 37) % 256,
                              (x ^ y ^ 193) % 256))
    original_table = [round(Fraction(p * 16384, 255)) for p in range(256)]
    d_table = [round(Fraction((2*p-255)*16384, 255)) for p in range(256)]
    # No half-integer can have denominator 255; Python ties-even equals D RHAZ.
    assert all(Fraction((2*p-255)*16384, 255).denominator % 2 for p in range(256))
    original = array('h', (original_table[rgb[3*i+c]] for c in range(3) for i in range(H*W)))
    d_input = array('h', (d_table[rgb[3*i+c]] for c in range(3) for i in range(H*W)))
    cnn = array('h')
    for c in range(3):
        for y in range(60):
            for x in range(106):
                indices = [c*H*W+(12*y+5+dy)*W+12*x+5+dx for dy in (0,1) for dx in (0,1)]
                cnn.append(round(Fraction(sum(original[i] for i in indices), 4)))
    assert sys.byteorder == 'little'
    (fixtures/'rgb.u8').write_bytes(rgb)
    for name, values in [('original', original), ('d_input', d_input), ('cnn_input', cnn)]:
        (fixtures/(name+'.i16')).write_bytes(values.tobytes())
    if lowlight.stat().st_size != COUNT*2:
        raise ValueError('Frozen lowlight Golden has wrong length')
    shutil.copy2(lowlight, fixtures/'lowlight.i16')
    # Archived D Golden is 1280 wide. Repack the first 1272 values of every row
    # solely to test bit-copy adaptation of real D output values. This is NOT a
    # Golden for running D at width 1272 and NOT a new D model validation.
    name = 'compact_d_fpga/board/k26_compact_d_20261025/validation/pattern_720p/21_output.relu.i16'
    payload = subprocess.check_output(['git','show',D_REF+':'+name], cwd=ROOT)
    if len(payload) != 3*H*1280*2:
        raise ValueError('Archived D Golden has wrong length')
    packed = b''.join(payload[(c*H+y)*1280*2:(c*H+y)*1280*2+W*2]
                      for c in range(3) for y in range(H))
    (fixtures/'d_output.i16').write_bytes(packed)
    bounds = array('h', ((i % 65536)-32768 for i in range(COUNT)))
    (fixtures/'signed_boundaries.i16').write_bytes(bounds.tobytes())
    manifest = dict(shape=[1,3,H,W], lowlight_source=str(lowlight), lowlight_sha256=sha(lowlight),
                    d_source_commit=D_REF, d_source_path=name,
                    d_source_sha256=hashlib.sha256(payload).hexdigest(),
                    d_copy_scope='1280-wide archived output row-repacked to 1272; adapter only, not D inference',
                    rgb8_values_tested=256, signed_values_tested=65536,
                    d_double_quantization_differences=sum(d_table[p] != 2*original_table[p]-16384 for p in range(256)),
                    files={p.name:dict(bytes=p.stat().st_size,sha256=sha(p)) for p in fixtures.iterdir() if p.is_file()})
    save(out/'golden_manifest.json',manifest)


def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--stage', choices=['prepare','native','csim','synth'], required=True)
    parser.add_argument('--vitis', type=Path, default=Path('E:/Xilinx/2025.2/Vitis'))
    parser.add_argument('--lowlight', type=Path, default=Path('E:/HLS/kv260_three_module_v1_2_phase4/data/expected_enhanced_q14.bin'))
    parser.add_argument('--compiler',type=Path,default=Path('C:/msys64/ucrt64/bin/g++.exe'))
    args = parser.parse_args()
    out = args.out.resolve()
    if not re.fullmatch(r'[A-Za-z0-9_:/\\.\-]+', str(out)):
        raise ValueError('Build directory needs an ASCII path without spaces')
    out.mkdir(parents=True, exist_ok=True)
    result = dict(stage=args.stage, passed=False, steps={}, scope='adapters only, no board measurement')
    try:
        if args.stage == 'prepare':
            prepare(out,args.lowlight)
        else:
            manifest=json.loads((out/'golden_manifest.json').read_text())
            for name, spec in manifest['files'].items():
                if sha(out/'fixtures'/name) != spec['sha256']:
                    raise ValueError('Changed Golden fixture '+name)
            if args.stage in ('native','csim'):
                # A missing output must fail this stage, even if Host/CSim was
                # run previously in the same build directory.
                for name in ('original','d_input','cnn_input','lowlight','d_output','signed_boundaries'):
                    (out/'fixtures'/('actual_'+name+'.i16')).unlink(missing_ok=True)
            source=out/'source'
            if not source.exists():
                source.mkdir()
                for p in (ROOT/'hls').iterdir():
                    shutil.copy2(p,source/p.name)
            for p in (ROOT/'hls').iterdir():
                if sha(p) != sha(source/p.name):
                    raise ValueError('Build source differs; use a fresh directory')
            result['source_sha256']={p.name:sha(p) for p in source.iterdir()}

            def execute(label, command):
                print('ADAPTER_STAGE='+label,flush=True)
                begin=time.perf_counter()
                with (out/(label+'.log')).open('wb') as log:
                    process=subprocess.run(list(map(str,command)),cwd=out,stdout=log,stderr=subprocess.STDOUT)
                result['steps'][label]=dict(exit_code=process.returncode, seconds=time.perf_counter()-begin,
                                           log_sha256=sha(out/(label+'.log')))
                text=(out/(label+'.log')).read_text(errors='replace')
                if process.returncode or re.search(r'(?mi)^\s*(ERROR|FATAL):|fatal error:',text):
                    raise RuntimeError(label+' failed; see '+str(out/(label+'.log')))
                return text

            def vendor(label, exe, flags):
                paths=[str(args.vitis.parent/'data/settings64.bat'),str(exe),*map(str,flags)]
                if any(re.search(r'[\r\n"&|<>^%!]',p) for p in paths):
                    raise ValueError('Unsafe vendor argument')
                command=out/(label+'.cmd')
                command.write_text('@echo off\nsetlocal\nset "PROCESSOR_ARCHITECTURE=AMD64"\ncall "'+paths[0]+'"\nif errorlevel 1 exit /b %errorlevel%\ncall '+' '.join('"'+p+'"' for p in paths[1:])+'\nexit /b %errorlevel%\n',encoding='ascii')
                return execute(label,[os.environ.get('COMSPEC','cmd.exe'),'/d','/c',command])

            if args.stage=='native':
                exe=out/'test_adapters.exe'
                execute('compile',[args.compiler,'-std=c++14','-O2','-Wno-unknown-pragmas',source/'joint_adapters.cpp',source/'test_adapters.cpp','-o',exe])
                text=execute('native',[exe,out/'fixtures'])
                if 'JOINT_ADAPTERS_PASS' not in text: raise RuntimeError('Incomplete Host test')
            else:
                result['ips']={}
                for top,define in [('joint_rgb8_prepare','TEST_PREPARE_ONLY'),('joint_q14_copy','TEST_COPY_ONLY')]:
                    config=out/(top+'.cfg')
                    lines=['part=xck26-sfvc784-2LV-c','[hls]','flow_target=vivado','clock=10','syn.top='+top,
                           'syn.file='+(source/'joint_adapters.cpp').as_posix(),
                           'tb.file='+(source/'test_adapters.cpp').as_posix(),
                           'tb.file_cflags='+(source/'test_adapters.cpp').as_posix()+',-D'+define,
                           'csim.argv='+(out/'fixtures').as_posix(),
                           'package.output.format=ip_catalog']
                    config.write_text('\n'.join(lines)+'\n',encoding='ascii')
                    work=out/top
                    if args.stage=='csim':
                        text=vendor('csim_'+top,args.vitis/'bin/vitis-run.bat',['--mode','hls','--csim','--config',config,'--work_dir',work])
                        if 'JOINT_ADAPTERS_PASS' not in text: raise RuntimeError('Incomplete CSim')
                    elif args.stage=='synth':
                        vendor('synth_'+top,args.vitis/'bin/v++.bat',['-c','--mode','hls','--config',config,'--work_dir',work])
                        xml=work/'hls/syn/report'/ (top+'_csynth.xml')
                        tree=ET.parse(xml)
                        def fields(path):
                            node=tree.find(path)
                            return {} if node is None else {v.tag:v.text for v in node}
                        result['ips'][top]=dict(resources=fields('.//AreaEstimates/Resources'),timing=fields('.//PerformanceEstimates/SummaryOfTimingAnalysis'),report_sha256=sha(xml))
                        zips=list(work.glob('hls/impl/ip/*.zip'))
                        if not zips:
                            vendor('export_'+top,args.vitis/'bin/vitis-run.bat',['--mode','hls','--package','--config',config,'--work_dir',work])
                            zips=list(work.glob('hls/impl/ip/*.zip'))
                        if not zips: raise RuntimeError('No exported IP zip')
                        result['ips'][top]['packages']={str(p):sha(p) for p in zips}
            if args.stage in ('native','csim'):
                names=['original','d_input','cnn_input','lowlight','d_output','signed_boundaries']
                for name in names:
                    if sha(out/'fixtures'/('actual_'+name+'.i16')) != manifest['files'][name+'.i16']['sha256']:
                        raise RuntimeError('Actual raw file hash mismatch: '+name)
                result['elementwise_mismatches']=0
                result['compared_scalars']=5*COUNT+3*60*106
                result['invalid_cookie_tests']=2
            result['golden_manifest_sha256']=sha(out/'golden_manifest.json')
        result['passed']=True
    except Exception as error:
        result['error']=str(error)
        raise
    finally:
        save(out/(args.stage+'_result.json'),result)
        print('ADAPTER_RESULT stage='+args.stage+' passed='+str(result['passed']),flush=True)


if __name__=='__main__':
    main()

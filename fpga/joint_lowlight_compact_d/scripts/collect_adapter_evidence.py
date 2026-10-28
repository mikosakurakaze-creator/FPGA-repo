"""Collect small review evidence after completed adapter checks; verify exported ABI."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser=argparse.ArgumentParser(__doc__)
    parser.add_argument('--build',type=Path,required=True)
    parser.add_argument('--out',type=Path,required=True)
    a=parser.parse_args()
    root=Path(__file__).resolve().parents[1]
    results={}
    for stage in ['native','csim','synth']:
        path=a.build/(stage+'_result.json')
        result=json.loads(path.read_text())
        assert result['passed'], stage+' did not pass'
        for name, digest in result['source_sha256'].items():
            assert sha(root/'hls'/name)==digest, 'Changed tested source '+name
        results[stage]=dict(path=str(path),sha256=sha(path))
    specs={
        'joint_rgb8_prepare': {'AP_RETURN':(0x10,32),'RGB_DATA':(0x18,64),
                             'ORIGINAL_Q14_DATA':(0x24,64),'D_INPUT_Q14_DATA':(0x30,64),
                             'CNN_INPUT_Q14_DATA':(0x3c,64),'ABI_COOKIE_DATA':(0x48,32)},
        'joint_q14_copy': {'AP_RETURN':(0x10,32),'SOURCE_DATA':(0x18,64),
                           'DESTINATION_DATA':(0x24,64),'ABI_COOKIE_DATA':(0x30,32)}
    }
    ips={}
    for top, fields in specs.items():
        ip=a.build/top/'hls/impl/ip'
        header=ip/'drivers'/(top+'_v1_0')/'src'/('x'+top+'_hw.h')
        text=header.read_text()
        defines=dict(re.findall(r'^#define\s+(\w+)\s+(0x[0-9a-fA-F]+|[0-9]+)\s*$',text,re.M))
        prefix='X'+top.upper()+'_CONTROL_'
        for name, (offset, bits) in fields.items():
            assert int(defines[prefix+'ADDR_'+name],0)==offset, top+' offset '+name
            assert int(defines[prefix+'BITS_'+name],0)==bits, top+' width '+name
        package=ip/('xilinx_com_hls_'+top+'_1_0.zip')
        ips[top]=dict(driver_sha256=sha(header), component_sha256=sha(ip/'component.xml'),
                      package_path=str(package), package_sha256=sha(package),
                      abi_verified={name:dict(offset=hex(offset),bits=bits) for name,(offset,bits) in fields.items()})
    golden=json.loads((a.build/'golden_manifest.json').read_text())
    for name, spec in golden['files'].items():
        assert sha(a.build/'fixtures'/name)==spec['sha256'], 'Changed fixture '+name
    for name in ('original','d_input','cnn_input','lowlight','d_output','signed_boundaries'):
        assert sha(a.build/'fixtures'/('actual_'+name+'.i16'))==golden['files'][name+'.i16']['sha256']
    a.out.mkdir(parents=True,exist_ok=True)
    for name in ('golden_manifest.json','native_result.json','csim_result.json','synth_result.json'):
        shutil.copy2(a.build/name,a.out/name)
    result=dict(passed=True, verification_scope='Full-frame adapters: Host + HLS CSim, HLS synthesis/export, actual ABI; no RTL/board result',
                compared_scalars_per_numeric_run=13756680, mismatches=0,
                source_sha256={p.name:sha(p) for p in (root/'hls').iterdir() if p.is_file()},
                results=results,ips=ips,
                limitations=['No adapter RTL co-simulation','No 1272-wide D model Golden or combined model RTL run',
                             'Archived 1280-wide D values only test raw-copy adaptation','No bitstream/route/board/performance measurement'])
    (a.out/'adapter_evidence.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print('ADAPTER_EVIDENCE_PASS')


if __name__=='__main__':
    main()

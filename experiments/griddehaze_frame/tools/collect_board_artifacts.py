"""Collect only a completed matching build for local board handoff; no ZIP/Git."""
import argparse
import json
from pathlib import Path
import shutil
import zipfile
from preflight import ROOT,sha,save

p=argparse.ArgumentParser(__doc__)
p.add_argument('--build',type=Path,required=True)
p.add_argument('--out',type=Path,required=True)
a=p.parse_args();b=a.build.resolve()
manifest=json.loads((b/'build.json').read_text(encoding='utf-8'))
for stage in ['create','synth','impl','export']:
    if not manifest['stages'].get(stage,{}).get('pass'):raise RuntimeError('Build stage incomplete '+stage)
for identity in ['compiled_sources_audit_sha256','routed_test_result_sha256','legacy_test_result_sha256']:
    if not manifest.get(identity):raise RuntimeError('Missing release gate '+identity)
for name,identity in [('new_core_routed_test.json','routed_test_result_sha256'),
                      ('legacy_routed_test.json','legacy_test_result_sha256'),
                      ('compiled_sources_audit.json','compiled_sources_audit_sha256')]:
    if sha(b/name)!=manifest[identity]:raise RuntimeError('Release evidence changed '+name)
for name,expected in manifest['stages']['export']['outputs_sha256'].items():
    if sha(b/name)!=expected:raise RuntimeError('Export identity changed '+name)
with zipfile.ZipFile(b/'griddehaze_system.xsa') as z:
    if z.testzip() is not None:raise RuntimeError('XSA CRC failure')
    bits=[n for n in z.namelist() if n.endswith('.bit')]
    if len(bits)!=1 or z.read(bits[0])!=(b/'griddehaze_system.bit').read_bytes():
        raise RuntimeError('XSA embedded bit differs from external bit')
    if not any(n.endswith('.hwh') for n in z.namelist()):raise RuntimeError('XSA lacks HWH')
out=a.out.resolve();out.mkdir(parents=True,exist_ok=False)
files={}
for name in ['griddehaze_system.bit','griddehaze_system.xsa','build.json','compiled_sources_audit.json',
             'new_core_routed_test.json','legacy_routed_test.json','routed_timing.rpt',
             'routed_utilization_summary.rpt','route_status.rpt','routed_drc.rpt']:
    shutil.copy2(b/name,out/name);files[name]=dict(bytes=(out/name).stat().st_size,sha256=sha(out/name))
for source,name in [(ROOT/'docs/frame_interface.md','frame_interface.md'),
                    (ROOT/'docs/system_seed_correction_20261024.md','system_seed_correction_20261024.md'),
                    (b/'ip/griddehaze/drivers/griddehaze_frame_top_v1_0/src/xgriddehaze_frame_top_hw.h','xgriddehaze_frame_top_hw.h')]:
    shutil.copy2(source,out/name);files[name]=dict(bytes=(out/name).stat().st_size,sha256=sha(out/name))
readme='''# GridDehazeNet K26 上板候选

此目录只在同版综合、布线时序、新核全系统数值回归及旧核回归通过后生成。

- `griddehaze_system.bit`：五核系统配置文件；保留低照度和旧 weather，增加 GridDehazeNet。
- `griddehaze_system.xsa`：同版硬件平台，内嵌 bit 已与外部 bit 逐字节比较。
- `frame_interface.md`、实际寄存器头文件：新核控制和 DDR 合同，base=0xA0040000。
- `build.json`、综合源码核查、时序/资源/DRC：实际构建与验证身份；SHA256.json 为本目录清单。

本地仿真使用独立 PS/DDR 刺激，不是板测。此候选尚需软件侧完成平台加载、可信独占低 DDR 分配、缓存一致性与输入输出适配，然后由真板验收。上传、Linux 驱动、设备树部署及 HDMI 不在本轮实现范围。

A 参数、数据集、运行输出及工具缓存不在本目录。参数保持冻结 INT16 bundle；不得将旧核 Q14 输入/输出合同套用到新核逐节点尺度和 F13 输出。未承诺 720p 视频帧率。
'''
(out/'README.md').write_text(readme,encoding='utf-8')
files['README.md']=dict(bytes=(out/'README.md').stat().st_size,sha256=sha(out/'README.md'))
save(out/'SHA256.json',dict(build_source=str(b),files=files,board_execution=False))
print('LOCAL_BOARD_ARTIFACTS_PASS '+str(out))

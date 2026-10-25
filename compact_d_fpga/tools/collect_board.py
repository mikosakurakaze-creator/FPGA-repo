"""Collect the D board files and verify their actual bytes and timing reports."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import zipfile
import xml.etree.ElementTree as ET
from vendor_runtime import run_vendor

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def bit_payload(data):
    pos = 2+int.from_bytes(data[:2], 'big')
    if data[pos:pos+2] != b'\0\1':
        raise ValueError('Invalid bit header')
    pos += 2
    for tag in b'abcde':
        if data[pos] != tag:
            raise ValueError('Unexpected bit field')
        pos += 1
        size = 4 if tag == ord('e') else 2
        length = int.from_bytes(data[pos:pos+size], 'big')
        pos += size
        if tag == ord('e'):
            if pos+length != len(data) or length % 4:
                raise ValueError('Invalid bit payload')
            return data[pos:]
        pos += length


def verify(folder):
    bit = (folder/'compact_d_system.bit').read_bytes()
    with zipfile.ZipFile(folder/'compact_d_system.xsa') as z:
        if z.testzip():
            raise ValueError('XSA CRC failure')
        bits = [n for n in z.namelist() if n.endswith('.bit')]
        if len(bits) != 1 or z.read(bits[0]) != bit:
            raise ValueError('XSA and external bit differ')
        if z.read('system.hwh') != (folder/'compact_d_system.hwh').read_bytes():
            raise ValueError('XSA and full system HWH differ')
    hwh = ET.fromstring((folder/'compact_d_system.hwh').read_bytes())
    core = next(m for m in hwh.iter('MODULE') if m.get('INSTANCE') == 'compact_d_top_0')
    params = {p.get('NAME'): p.get('VALUE') for p in core.iter('PARAMETER')}
    if int(params['C_S_AXI_CONTROL_BASEADDR'], 0) != 0xA0050000:
        raise ValueError('Unexpected control address in HWH')
    memories = {m.get('MASTERBUSINTERFACE'): m for m in core.iter('MEMRANGE')}
    for master, hp in [('m_axi_gmem_in', 'S_AXI_HP0_FPD'), ('m_axi_gmem_out', 'S_AXI_HP3_FPD')]:
        entry = memories[master]
        if entry.get('SLAVEBUSINTERFACE') != hp or int(entry.get('HIGHVALUE'), 0) != 0x7fffffff:
            raise ValueError('Unexpected DDR map in HWH')
    reset = next(m for m in hwh.iter('MODULE') if m.get('INSTANCE') == 'rst_ps_d')
    reset_params = {p.get('NAME'): p.get('VALUE') for p in reset.iter('PARAMETER')}
    if reset_params['C_EXT_RESET_HIGH'] != '0':
        raise ValueError('Reset polarity differs from PS resetn')
    ps = next(m for m in hwh.iter('MODULE') if m.get('INSTANCE') == 'zynq_ultra_ps_e_0')
    ps_params = {p.get('NAME'): p.get('VALUE') for p in ps.iter('PARAMETER')}
    if any(ps_params['C_SAXIGP'+str(i)+'_DATA_WIDTH'] != '128' for i in (2, 5)):
        raise ValueError('PS HP0/HP3 data width differs')
    clock = next(p for p in core.iter('PORT') if p.get('NAME') == 'ap_clk')
    if abs(int(clock.get('CLKFREQUENCY'))-200000000) > 20000:
        raise ValueError('D clock differs from 200 MHz configuration')
    payload = bit_payload(bit)
    swapped = bytearray(len(payload))
    for i in range(4):
        swapped[i::4] = payload[3-i::4]
    if swapped != (folder/'compact_d_system.bit.bin').read_bytes():
        raise ValueError('BIN and bit payload differ')
    for row in (folder/'SHA256SUMS').read_text(encoding='utf-8').splitlines():
        digest, name = row.split('  ', 1)
        if sha(folder/name) != digest:
            raise ValueError('Changed release file: '+name)
    print('D_BOARD_FILES_IDENTITY_PASS', flush=True)


def main():
    p = argparse.ArgumentParser(__doc__)
    p.add_argument('--build', type=Path, default=Path('D:/weather_builds/compact_d_system03'))
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--verify-only', action='store_true')
    p.add_argument('--runtime', type=Path, default=Path('D:/weather_builds/compact_d_vendor_runtime01'))
    p.add_argument('--vivado', type=Path, default=Path('D:/vivado/2025.2/Vivado'))
    p.add_argument('--hls', type=Path, default=Path('D:/weather_builds/compact_d_cosim01'))
    p.add_argument('--numeric', type=Path, default=Path('D:/weather_builds/compact_d_numeric01'))
    a = p.parse_args()
    if a.verify_only:
        verify(a.out)
        return
    b, out = a.build, a.out
    build = json.loads((b/'build.json').read_text(encoding='utf-8'))
    if not all(build['stages'].get(s, {}).get('pass_result') for s in ['create', 'synth', 'export']) or not any(build['stages'].get(s, {}).get('pass_result') for s in ['impl', 'verify_impl']):
        raise ValueError('Necessary Vivado stages incomplete')
    if build['stages'].get('verify_impl', {}).get('pass_result') and sha(b/'system_routed.dcp') != build['stages']['verify_impl']['checkpoint_sha256']:
        raise ValueError('Verified checkpoint changed')
    hls = a.hls
    hls_result = json.loads((hls/'result.json').read_text(encoding='utf-8'))
    if not hls_result['pass_result'] or hls_result['stage'] != 'cosim':
        raise ValueError('RTL regression incomplete')
    if build['parameters'] != hls_result['parameters']:
        raise ValueError('HLS parameter identity differs')
    for name in ['compact_d.cpp', 'compact_d.hpp']:
        if sha(ROOT/'hls'/name) != build['hls_source_sha256'][name] or sha(hls/name) != build['hls_source_sha256'][name]:
            raise ValueError('Hardware source differs: '+name)
    if sha(b/'ip/compact_d/xilinx_com_hls_compact_d_top_1_0.zip') != sha(hls/'component/hls/impl/ip/xilinx_com_hls_compact_d_top_1_0.zip'):
        raise ValueError('Validated and implemented IP differ')
    timing = (b/'routed_timing.rpt').read_text(errors='replace')
    match = re.search(r'WNS\(ns\).*?WPWS\(ns\).*?\n\s*-[-\s]+\n\s*([^\n]+)', timing, re.S)
    if not match:
        raise ValueError('Missing timing summary')
    fields = match.group(1).split()
    if len(fields) != 12 or any(float(fields[i]) < 0 for i in (0, 4, 8)) or any(int(fields[i]) for i in (2, 6, 10)):
        raise ValueError('Timing failed')
    route = (b/'route_status.rpt').read_text(errors='replace')
    counts = {key: int(re.search(r'# of '+key+r'\.+\s*:\s*(\d+)', route).group(1)) for key in ['routable nets', 'fully routed nets', 'nets with routing errors']}
    if not counts['routable nets'] or counts['routable nets'] != counts['fully routed nets'] or counts['nets with routing errors']:
        raise ValueError('Routing incomplete')
    out.mkdir(parents=True, exist_ok=False)
    for name in ['compact_d_system.bit', 'compact_d_system.xsa']:
        shutil.copy2(b/name, out/name)
    with zipfile.ZipFile(out/'compact_d_system.xsa') as z:
        (out/'compact_d_system.hwh').write_bytes(z.read('system.hwh'))
        for name in z.namelist():
            if name.startswith('psu_init') and not name.endswith('/'):
                path = out/'ps_init'/Path(name).name
                path.parent.mkdir(exist_ok=True)
                path.write_bytes(z.read(name))
    (out/'fpga.bif').write_text('all:\n{\n  compact_d_system.bit\n}\n', encoding='ascii', newline='\n')
    with (out/'bootgen.log').open('wb') as log:
        result = run_vendor(a.vivado, a.runtime, 'bootgen.exe', ['-arch', 'zynqmp', '-image', 'fpga.bif', '-process_bitstream', 'bin', '-w', 'on'], out.resolve(), log)
    if result.returncode or not (out/'compact_d_system.bit.bin').is_file():
        raise ValueError('Bootgen did not produce BIN')
    reports = out/'reports'
    reports.mkdir()
    for name in ['routed_timing.rpt', 'routed_utilization.rpt', 'route_status.rpt', 'routed_drc.rpt', 'build.json', 'system_recreate.tcl', 'ps_config.tcl']:
        shutil.copy2(b/name, reports/name)
    for name in ['verified_timing.rpt', 'verified_route_status.rpt']:
        if (b/name).is_file():
            shutil.copy2(b/name, reports/name)
    for name in ['create.tcl', 'synth.tcl', 'impl.tcl', 'verify_impl.tcl', 'export.tcl', 'verify_impl.log', 'export.log']:
        if (b/name).is_file():
            shutil.copy2(b/name, reports/name)
    for name in ['result.json', 'cosim.log', 'component/hls/sim/report/compact_d_top_cosim.rpt', 'component/hls/syn/report/compact_d_top_csynth.rpt']:
        shutil.copy2(hls/name, reports/('hls_'+Path(name).name))
    for stage, folder in [('host', 'compact_d_native02'), ('csim', 'compact_d_csim04')]:
        source = Path('D:/weather_builds')/folder
        evidence = json.loads((source/'result.json').read_text(encoding='utf-8'))
        if not evidence['pass_result'] or evidence['parameters'] != build['parameters']:
            raise ValueError('Software reference evidence differs: '+stage)
        shutil.copy2(source/'result.json', reports/(stage+'_result.json'))
    vectors = out/'validation'
    for name in ['random_8x8', 'random_33x47']:
        target = vectors/name
        target.mkdir(parents=True)
        folder = a.numeric/'golden'/name
        for filename in ['input.i16', '21_output.relu.i16', 'report.json']:
            shutil.copy2(folder/filename, target/filename)
    shutil.copytree('D:/weather_builds/compact_d_width_review01', vectors/'width_1280_rtl')
    for name in ['random_17x1280', 'pattern_720p']:
        target = vectors/name
        target.mkdir()
        source = Path('D:/weather_builds/compact_d_large_vectors01')/name
        for filename in ['input.i16', '21_output.relu.i16', 'report.json']:
            shutil.copy2(source/filename, target/filename)
    shutil.copytree(a.numeric/'package', out/'model_int16')
    shutil.copy2(ROOT/'docs/INTERFACE.md', out/'INTERFACE.md')
    shutil.copy2(ROOT/'tools/compare_output.py', out/'compare_output.py')
    shutil.copy2(b/'ip/compact_d/drivers/compact_d_top_v1_0/src/xcompact_d_top_hw.h', out/'xcompact_d_top_hw.h')
    shutil.copy2(b/'ip/compact_d/xilinx_com_hls_compact_d_top_1_0.zip', out/'compact_d_ip.zip')
    (out/'README.md').write_text(f'''# D 模型 K26 上板文件

本目录为独立 D 镜像，使用冻结的 INT16 权重。旧 Weather、GridDehazeNet、低照度核属于各自镜像，当前 bit 不包含它们。

## 上板入口

- `compact_d_system.bit`：Vivado/JTAG 位流。
- `compact_d_system.bit.bin`：同一位流的 bootgen 转换结果，供下游 FPGA manager 集成。
- `compact_d_system.xsa`：包含同版 bit 的硬件平台。
- `compact_d_system.hwh`：完整系统 HWH，与 XSA 内文件一致。
- `INTERFACE.md`、`xcompact_d_top_hw.h`：DDR、寄存器和数值合同。
- `model_int16/`：与镜像绑定的 A 参数及清单；运行时无需 DMA 上传权重。
- `validation/`：8×8、33×47、17×1280、720p 输入及整数 Golden，以及最大宽度 RTL 输出证据。
- `reports/`：实际综合、RTL、布线、时序和构建记录。
- `ps_init/`：XSA 中导出的 PS 初始化文件，由下游按现有启动流程使用。

控制基址 `0xA0050000`，cookie `0x44433031`，PL 时钟 200 MHz。输入、输出分别经 HP0、HP3 访问低 2 GiB DDR。调用侧须提供两个不重叠、物理连续且 cache 一致的缓冲区；720p 共需约 10.55 MiB。详细布局和启动顺序见接口合同。

## 已有证据

Host 和 CSim 各完成 12 帧、22 节点整数对齐；RTL 小图套件完成 12 帧及 3 次非法调用。两帧 17×1280 的活动输出与 A Golden 一致，大图完整套件未完成。200 MHz 布线后 setup WNS {fields[0]} ns、hold WHS {fields[4]} ns，路由完整。

720p 完整 RTL、真板数值、DDR 连续帧及 30 FPS 实测尚未完成。6 phase/像素对应的约 27.65 ms 仅是计算主体预算，不含流水填充、DDR 停顿等开销。

## 文件核验

`SHA256SUMS` 记录落盘字节的 SHA-256。可运行项目中的 `tools/collect_board.py --out 本目录 --verify-only` 核对全部文件、XSA 内外 bit/HWH 及 BIN payload。下游使用本目录内成套文件，不混用旧接口或其他模型参数。

原始 INT16 输出比较示例：`python compare_output.py --expected validation/random_8x8/21_output.relu.i16 --actual board_output.i16 --height 8 --width 8`。要求原始整数零差异，不用显示图代替数值比较。
''', encoding='utf-8', newline='\n')
    manifest = dict(kind='independent_D_image', parameters=build['parameters'], control_base='0xA0050000',
                    clock_mhz=200, setup_wns_ns=float(fields[0]), hold_whs_ns=float(fields[4]), pulse_slack_ns=float(fields[8]),
                    route=counts, full720p_rtl_completed=False, board_measured=False,
                    numerical_scope='12-call small/odd RTL suite; active output of two 17x1280 captures',
                    files={f.relative_to(out).as_posix(): dict(bytes=f.stat().st_size, sha256=sha(f)) for f in sorted(out.rglob('*')) if f.is_file()})
    (out/'manifest.json').write_text(json.dumps(manifest, indent=2, ensure_ascii=False)+'\n', encoding='utf-8', newline='\n')
    sums=''.join(sha(f)+'  '+f.relative_to(out).as_posix()+'\n' for f in sorted(out.rglob('*')) if f.is_file() and f.name != 'SHA256SUMS')
    (out/'SHA256SUMS').write_text(sums, encoding='utf-8', newline='\n')
    verify(out)


if __name__ == '__main__':
    main()

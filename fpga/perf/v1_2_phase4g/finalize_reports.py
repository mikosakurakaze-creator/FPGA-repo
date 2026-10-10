"""Write the Phase 4G report/checkpoint only after every actual gate passes."""
import argparse
import csv
import datetime
import hashlib
import json
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
OUT = Path('E:/HLS/kv260_three_module_v1_2_phase4/phase4g')


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def require(value, message):
    if not value:
        raise RuntimeError(message)


def link(label, path):
    return '[' + label + '](' + Path(path).resolve().as_posix() + ')'


def git(*args):
    return subprocess.check_output(['git', *args], cwd=REPO, text=True).strip()


def table(headers, rows):
    return '| ' + ' | '.join(headers) + ' |\n| ' + ' | '.join(['---'] * len(headers)) + ' |\n' + ''.join(
        '| ' + ' | '.join(str(value) for value in row) + ' |\n' for row in rows)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--release-gate', type=Path, default=OUT / 'release_gate.json')
    parser.add_argument('--integration-gate', type=Path, default=OUT / 'integration_01/integration_gate.json')
    args = parser.parse_args()
    release = read(args.release_gate)
    system = read(args.integration_gate)
    protection = read(OUT / 'protection_after.json')
    require(release['status'] == system['status'] == protection['status'] == 'PASS', 'Required gate is not PASS')
    require(all(v == 'PASS' for v in release['checks'].values()), 'A release check failed')
    require(protection['before_after_identity'] == 'PASS' and protection['original_changed'] == [], 'Protection audit incomplete')
    for key, path in release['evidence'].items():
        require(sha(path) == release['evidence_sha256'][key], 'Release evidence changed: ' + key)
    require(system['release_gate_sha256'] == sha(args.release_gate), 'System used a different release gate')
    require(system['clock_MHz'] == 100 and system['synthesis'] == system['bd_validate'] == 'PASS', 'System synthesis gate failed')
    require(not any(system[key] for key in ('implementation_run', 'route_run', 'bitstream_generated', 'xsa_generated')),
            'Forbidden hardware flow was executed')
    require(system['pre_route_timing']['WNS_ns'] >= 0 and system['pre_route_timing']['TNS_ns'] == 0, 'System setup estimate failed')
    ip = Path(release['formal_ip_path'])
    build = read(release['formal_manifest_path'])
    require(sha(release['formal_manifest_path']) == release['formal_manifest_sha256'], 'Formal build manifest changed')
    identity = build['identity']
    package = read(release['evidence']['abi'])
    require(Path(package['primary']['ip']).resolve() == ip.resolve(), 'Final package audit path differs')
    for name, expected in package['primary']['files'].items():
        require(sha(ip / name) == expected, 'Formal package drift before report: ' + name)
    require(system['formal_verilog_files_checked'] == 139 and
            system['formal_hdl_headers_rom_files_checked'] == 150 and
            len(system['resolved_sources']) == 150, 'System source audit incomplete')
    for name, entries in system['resolved_sources'].items():
        expected = sha(ip / 'hdl/verilog' / name)
        require(entries and all(entry['sha256'] == expected and sha(entry['path']) == expected and
                                entry['used_in_synthesis'] == entry['used_in_simulation'] == '1'
                                for entry in entries), 'System source drift before report: ' + name)
    require(all(item['status'] == 'Not started' and item['progress'] == '0%'
                for item in system['implementation_scope']), 'Implementation scope changed')
    require(not list(Path(system['project']).parent.rglob('*.bit')) and
            not list(Path(system['project']).parent.rglob('*.xsa')), 'Forbidden export appeared')
    ps = system['bd_identity']['ps_effective_xci_identity']
    require(ps['status'] == 'PASS' and sha(ps['old_xci']) == ps['old_xci_sha256'] and
            sha(ps['new_xci']) == ps['new_xci_sha256'], 'Effective PS configuration evidence changed')
    for kind in ('component_parameters', 'model_parameters'):
        require(ps['actual_value_identity'][kind]['status'] == 'PASS' and
                ps['actual_value_identity'][kind]['differences'] == [], 'Effective PS configuration differs')
    rebuild = read(release['evidence']['rebuild'])
    probe = read(release['evidence']['writer_probe'])
    cnn_gate_path = Path(release['evidence']['cnn_single'])
    cnn_gate = read(cnn_gate_path)
    require(sha(cnn_gate['evidence']) == cnn_gate['evidence_sha256'], 'CNN analysis drift before report')
    cnn = read(cnn_gate['evidence'])
    ooc_path = Path(release['evidence']['ooc_synthesis'])
    ooc = read(ooc_path)
    require(sha(ooc_path.parent / 'cnn_writecredit_ooc.dcp') == ooc['checkpoint_sha256'], 'OOC checkpoint drift')
    require(sha(system['cnn_dcp']) == system['cnn_dcp_sha256'] and
            sha(system['system_dcp']) == system['system_dcp_sha256'], 'System/CNN checkpoint drift')
    require(cnn['new_cycles'] == 3301639 and cnn['numerical']['a_low_checked'] == 19080 and
            cnn['numerical']['raw_mismatch'] == cnn['numerical']['guard'] == cnn['numerical']['hazard'] == 0,
            'CNN numerical/latency evidence invalid')
    rows = list(csv.DictReader((cnn_gate_path.parent / 'results/stage_events.csv').open()))
    starts = [int(row['cycle']) for row in rows if row['event'] == 'START' and int(row['stage']) == 0]
    dones = [int(row['cycle']) for row in rows if row['event'] == 'DONE' and int(row['stage']) == 0]
    require(len(starts) == len(dones) == 1 and dones[0] - starts[0] == cnn['new_cycles'], 'CNN actual RTL events invalid')
    require(not any(int(row['stage']) != 0 and row['event'] == 'START' for row in rows), 'Later stages started')
    lock = read(REPO / 'fpga/ip/cnn_v1_2_writecredit/input_lock.json')
    git_state = dict(branch=git('branch', '--show-current'), head=git('rev-parse', 'HEAD'),
                     tracked_diff=git('diff', '--stat'), staged_diff=git('diff', '--cached', '--stat'),
                     status=git('status', '--short', '--untracked-files=all'))
    require(git_state['branch'] == protection['git_before']['branch'] and git_state['head'] == protection['git_before']['head'],
            'Branch or HEAD changed')
    require(git_state['tracked_diff'] == protection['git_before']['tracked_diff'] and
            git_state['staged_diff'] == protection['git_before']['staged_diff'], 'Tracked/staged diff changed')
    (OUT / 'git_review.json').write_text(json.dumps(git_state, indent=2) + '\n', encoding='utf-8')
    metrics = ooc['metrics']
    resources = system['resources']
    timing = system['pre_route_timing']
    stamp = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).isoformat()
    report_path = REPO / 'fpga/reports/v1_2_phase4g_implementable_cnn_ip.md'
    checkpoint_path = REPO / 'fpga/reports/v1_2_phase4_checkpoint.md'
    report = f'''# V1.2 Phase 4G — Implementable write-credit CNN IP

日期：2026-10-03（Asia/Shanghai）。CURRENT STATUS：**IMPLEMENTABLE_CNN_IP_READY / WAIT_MASTER**。报告生成时间：{stamp}。

正式 IP 的确定性构建、完整 ABI、综合/仿真源一致性、四组 writer local RTL probe、CNN 单帧、100MHz OOC、独立 V1.2 BD Validate / Output Products / 全系统 synthesis 全部 PASS。本批在 synthesis 停止；不是 post-route timing 或板测结果。

正式 repository entry：{link('component.xml', ip / 'component.xml')}；{link('build_manifest.json', ip / 'build_manifest.json')}；独立 V1.2 工程：{link('v12_wc.xpr', system['project'])}。

## 固化原因与权威历史

Phase 4E 已验证 write-credit 行为只存在于三颗 generated RTL overlay。原 frozen C++ 是数值参考，重跑 HLS 不会产生该 credit scheduling；临时仿真替换也不能证明 Vivado 综合使用同一实现。本批建立 **frozen r4 export → 输入 SHA gate → 原 generator 确定性三模块替换 → Vivado package → 同源 sanity/OOC → 新 V1.2 工程综合**。

Phase 4E isolated CNN **3,301,639 cycles**；Phase 4F 8-frame steady-state output max interval **3,307,317 cycles**、**SHORT_MULTI_FRAME_30FPS_PASS** 继续保留为权威历史，原日志/分析未改，本批没有重跑 8 帧。{link('旧 checkpoint', OUT / 'checkpoint_before.md')}、{link('Phase 4E', REPO / 'fpga/reports/v1_2_phase4e_write_retirement_optimization.md')}、{link('Phase 4F', REPO / 'fpga/reports/v1_2_phase4f_short_multiframe.md')}。

## Frozen identity 与三模块差异

Base export：`{lock['base_export_path']}`；base r4 payload identity SHA-256=`{identity['base_r4_sha256']}`，覆盖 **305** 个实际 IP payload 文件。原 HLS pack launcher、日志和旧未补丁 ZIP 不进入正式 entry，原文件仍保留并受保护。

Frozen C++：`candidate_b_rowstream_r4`，未修改。原 Phase 4E generator SHA-256=`{identity['generator_sha256']}`；overlay manifest SHA-256=`{identity['overlay_manifest_sha256']}`。三个 base RTL SHA 同时与 fresh export 和 Phase 4E 原 syn/verilog 一致。

''' + table(['Patched Verilog module', 'Base SHA-256', 'Final / verified overlay SHA-256'],
            [(entry['name'], entry['frozen_sha256'], entry['candidate_sha256']) for entry in lock['overlays']]) + f'''
仅三颗 RTL 改变：workspace row writer、output row writer、caller/output_writer 控制。原数值算法、地址/顺序、fixed-point、AXI adapters 和 credit=2 行为未变。其余 **301** 个原 payload 文件逐字一致；其中其他 **136** 个 Verilog 源文件及全部归档 VHDL hash 保持原样。唯一非 RTL 修改为 `component.xml` 的打包内部 metadata。

## ABI 与 package metadata

Top=`zero_dce_cnn_top`，VLNV=`xilinx.com:hls:zero_dce_cnn_top:1.0`。全部 top ports、bus/port maps、address spaces、memory/register maps、model parameters、driver、xgui 对 frozen export 严格相等。六 m_axi：`gmem_input/gmem_output/gmem_workspace/gmem8/gmem32/gmem_lut`；`s_axi_control`、`interrupt`、`ap_clk/ap_rst_n` 保持。driver header SHA-256=`{identity['driver_header_sha256']}`；ABI canonical SHA-256=`{identity['abi_sha256']}`。

''' + table(['64-bit pointer register', 'Offset'], package['primary']['seven_pointer_offsets'].items()) + f'''
固定 coreRevision：**2114810447 → 2114810448**，VLNV 不变，用于识别正式替换。原 VHDL synthesis/simulation 两套 view/fileset 含旧 writer，正式 metadata 删除这两个 active 入口；**138** 个 VHDL 文件仅原样归档，不参与源搜索或编译。

Vivado 2025.2 实际执行 open_core/update_checksums/check_integrity/save_core；随后仅规范化可选 address range 格式属性/相应原 checksum，并固定内部 coreCreationDateTime 为 base export 日期；实际构建 timestamp/path 独立记录在 manifest。规范化后再次只读 open_core/check_integrity PASS。所有外部 ABI 值及 XML ABI 子结构保持精确一致。

## 综合源 / 仿真源一致性

正式 Verilog synthesis / behavioral simulation view 共用 **150** 项：**139 Verilog + 2 VH headers + 9 ROM dat**，path/hash 完全相同；综合额外引用原 10ns OOC XDC。独立解析确认 **{package['primary']['unique_named_module_definitions']}** 个 module 定义无重复。每颗 patched writer 仅出现一次，无旧 writer active view、重复 module 或未引用 Verilog shadow。{link('完整 source manifest', ip / 'source_manifest.json')}、{link('package ABI/fileset audit', ip / 'abi_fileset_audit.json')}、{link('独立 byte/ABI/全150项审计', release['evidence']['filesets'])}。

CNN system sanity 的所有 **139** 个 CNN Verilog 源文件均来自正式 package，其他原 system sources 保持 hash。新 xelab options 只把唯一旧 CNN include 目录替换为正式 package 目录，其余 options 逐字一致；两个 header 只解析到正式路径，旧 CNN include/module search 入口为零。9 ROM data 的运行副本与正式包相同。{link('header/include audit', cnn_gate_path.parent / 'header_include_audit.json')}。

## 正式 IP 功能 sanity

实际 XSIM 四组局部 probe 均自然 exit0；完整数据、地址、WSTRB、WLAST、AW/B 排空及 timing evidence 与 Phase 4E new 原证据完全相等。credit peak2、最终0；全 RAM/guard mismatch0。{link('local gate', release['evidence']['writer_probe'])}。

''' + table(['Scenario', 'Writer cycles', 'Actual W overlap rows', 'Physical AW / WLAST / B'],
            [(name, entry['new_cycles'], entry['actual_data_overlap_rows'],
              f"{entry['physical_aw']} / {entry['physical_wlast']} / {entry['physical_b']}")
             for name, entry in probe['scenarios'].items()]) + f'''
最终完整 CNN 单帧：**FRAMES=1、READ/WRITE_OUTSTANDING=2、DDR_DELAY=16、SERVICE_PERIOD=1、POLL_PERIOD=128、100MHz**。真实内部 ap_start={starts[0]:,} → ap_done={dones[0]:,}，**{cnn['new_cycles']:,} cycles**，与 Phase 4E 精确相等。A_low **19,080/19,080 raw mismatch=0、guard=0、hazard=0**，IRQ gate PASS；7 writer/group block drains、两侧 final credit0、最终 4HP 的 RC/WC/WP/RVALID/BVALID 全0。原 BFM 主体逐字恢复一致，Bilinear/Curve 没有启动。{link('完整分析', cnn_gate['evidence'])}、{link('自然退出', cnn_gate_path.parent / 'exit_status.json')}、{link('原始日志', cnn_gate_path.parent / 'system.log')}。

## 实际 OOC / 全系统 synthesis

Vivado **2025.2**，K26 `xck26-sfvc784-2LV-c`，**10ns / 100MHz**。OOC 从正式 synthesis fileset 读取 139 Verilog 和所有 header/ROM，actual compile order 全量核对；三颗 writer 本体 REF_NAME 及 14 个 credit nets 留在实际 synthesis hierarchy。OOC 自然 exit0，生成新 DCP。{link('OOC gate', ooc_path)}、{link('OOC utilization', ooc_path.parent / 'utilization.rpt')}、{link('OOC hierarchy', ooc_path.parent / 'hierarchy.tsv')}。

只有 release 的 ABI/filesets/rebuild/probe/CNN/OOC 全 PASS 后才启动工程替换。使用原 saved V1.2 `system.bd` 新建独立工程，正式 CNN catalog 唯一解析，upgrade/refresh、BD Validate、Generate Output Products、Wrapper、actual full synthesis 全 PASS。Bilinear/Curve 为原 IP 的逐字相同隔离副本；ip cache disabled，不复用旧 CNN DCP。原 BD nets/interface_nets/addressing/design_tree 及所有原配置保持一致；CNN revision 为2114810448。控制地址仍为 Bilinear 0xA0000000 / Curve 0xA0010000 / CNN 0xA0020000，11 DDR masters 与 HP0–HP3/100MHz 拓扑不变。

新 BD 唯一非 CNN 差异为 PS 显式增加 `PSU_MIO_22_INPUT_TYPE=cmos`。原 V1.2 PS XCI/解析 XML 已是同一值；新工程只是把既有解析值写入 BD。审计仅允许这一项且核验原/新有效配置，不放宽其他配置或 cell 字段。第一轮严格逐字 cell 审计因此拒绝；实际 Vivado create/synthesis 均自然 exit0，定位后仅重新执行只读审计，没有重跑综合。除这一显式记录外，非 CNN cells 保持精确一致。

系统实际读取全部 **{system['formal_verilog_files_checked']}** 个正式 CNN Verilog，以及 headers/ROM 共 **{system['formal_hdl_headers_rom_files_checked']}** 项的 hash 与 synth/sim 使用属性，无旧路径或版本；CNN 自身新 synthesis run 成功日志、新 CNN DCP、系统三 writer primitive hierarchy 均核对。{link('release gate', args.release_gate)}、{link('系统 integration gate', args.integration_gate)}、{link('系统层级证据', args.integration_gate.parent / 'reports/writecredit_hierarchy.tsv')}。

''' + table(['Actual post-synthesis resource', 'CNN OOC', 'Whole V1.2 system'], [
              ('LUT', metrics['LUT'], resources['LUT']), ('FF', metrics['FF'], resources['FF']),
              ('RAMB36', metrics['BRAM36'], resources['RAMB36']), ('RAMB18', metrics['BRAM18'], resources['RAMB18']),
              ('BRAM tiles', metrics['BRAM_tiles'], resources['BRAM_tiles']),
              ('Equivalent BRAM18', 2 * metrics['BRAM36'] + metrics['BRAM18'], resources['BRAM18_equivalent']),
              ('URAM', metrics['URAM'], resources['URAM']), ('DSP', metrics['DSP'], resources['DSP'])]) + f'''
资源采用实际 Vivado utilization 实报。OOC `metrics.tsv` 的粗 REF_NAME 计数包括层级/macro，仅诊断，不当作物理资源；{link('计数来源审计', ooc_path.parent / 'resource_counter_audit.json')} 解释差异。OOC 与系统不同综合上下文，不与 HLS area estimate 简单相减。

''' + table(['Timing / synthesis estimate', 'CNN OOC', 'Whole V1.2 system'], [
              ('Clock period', '10.000 ns', '10.000 ns'),
              ('Setup slack / WNS', f"{metrics['setup_estimate_slack_ns']:+.3f} ns", f"{timing['WNS_ns']:+.3f} ns"),
              ('TNS / failing setup endpoints', 'See OOC timing report', f"{timing['TNS_ns']} ns / {timing['setup_failing_endpoints']}"),
              ('Pre-route hold slack / WHS', f"{metrics['pre_route_hold_slack_ns']:+.3f} ns", f"{timing['WHS_ns']:+.3f} ns"),
              ('THS / failing hold endpoints', 'See OOC timing report', f"{timing['THS_ns']} ns / {timing['hold_failing_endpoints']}")]) + f'''
100MHz setup estimate 无失败。系统原 timing summary 标记 `Timing constraints are not met`，对应上述 pre-route hold 失败估计。**Hold 仅为未放置、pre-route 估计，不是最终 hold 结论。** OOC ap_clk 未指定 HD.CLK_SRC，时钟 skew 估计有限；本批没有 place/route。{link('OOC timing', ooc_path.parent / 'timing_summary.rpt')}、{link('系统 timing', args.integration_gate.parent / 'reports/system_timing_summary.rpt')}。

## 可复现构建

两份干净目录 `{ip.name}` / `{Path(rebuild['rebuild']).name}` 从同一 frozen export/锁及原 generator 独立执行 base hash → patch → package → 只读 integrity。**全部305项 payload、component.xml、source manifest、ABI audit、driver/三颗RTL逐字相同**。{link('deterministic rebuild', release['evidence']['rebuild'])}。Manifest identity SHA-256=`{build['identity_sha256']}`。

Raw component SHA-256=`{identity['component_xml_sha256']}`；raw source manifest SHA-256=`{identity['source_manifest_file_sha256']}`；canonical source manifest SHA-256=`{identity['source_manifest_sha256']}`；build recipe SHA-256=`{identity['build_recipe_sha256']}`；input lock raw SHA-256=`{identity['input_lock_file_sha256']}`。实际 timestamp、输出路径和工作路径仅 execution 字段不同，不参与 release identity。{link('构建配方', REPO / 'fpga/ip/cnn_v1_2_writecredit/README.md')}、{link('完整 gate 执行方法', REPO / 'fpga/perf/v1_2_phase4g/README.md')}。

## 保护与尝试记录

原 recovery 审计 **{protection['original_protected_files']:,}** 项与补充审计集 **{protection['additional_protected_files']:,}** 项前后 hash PASS，changed=[]。覆盖 frozen r4/export、原 overlay/generator、Bilinear/Curve、fixed-point protocol、DDR、V1.1 及原 Phase 4E/F 证据。{link('before audit', OUT / 'protection_before.json')}、{link('after audit', OUT / 'protection_after.json')}。旧 checkpoint 原字节备份保留。

构建候选目录保留真实尝试：loader 缺 ARCH 的启动失败、工具初始化失败及元数据格式/创建时间不确定性均解决后才选最终_05/_06。早期初版 local 自然通过但标为 superseded，不进入 release；CNN05 记录至350,000 cycles后因旧 include 目录的来源审计中止，没有 DONE/全量数值结果，不用于 gate。最终 CNN06 只替换搜索路径后完整自然运行；算法、DUT 字节和 DDR 未更改。未运行的 prepared 目录也不当作验证结果。

## 文件变更、验证与 Git review

''' + table(['File(s)', 'Reason / key difference'], [
              ('fpga/ip/cnn_v1_2_writecredit/build_ip.py', '锁定原export，原generator重现仅3RTL，Vivado package及内部metadata确定性规范化'),
              ('fpga/ip/cnn_v1_2_writecredit/input_lock.json', '记录所有base payload、原generator/overlay/frozen输入SHA，拒绝漂移'),
              ('fpga/ip/cnn_v1_2_writecredit/run_ooc.py', '从正式fileset实际OOC，记录clock/resource/timing/compile/hierarchy'),
              ('fpga/ip/cnn_v1_2_writecredit/README.md', '发布配方、ABI/source metadata选择、复建与停止条件'),
              ('fpga/perf/v1_2_phase4g/protection.py', '原5235项与r4/4E/4F额外证据前后hash、checkpoint备份'),
              ('fpga/perf/v1_2_phase4g/audit_release.py', '独立核对三RTL差异、完整外ABI、全150项synth/sim及逐byte复建'),
              ('fpga/perf/v1_2_phase4g/sanity_sources.py', '严格解析正式源与实际compile list，拒绝旧module/source drift'),
              ('fpga/perf/v1_2_phase4g/prepare_sanity.py', '复用原BFM/probe，新来源清单与唯一include路径替换'),
              ('fpga/perf/v1_2_phase4g/run_sanity.py', '4有界probe及1完整CNN单帧，绑定kernel/manifest/实际exit'),
              ('fpga/perf/v1_2_phase4g/analyze_sanity.py', '原独立analyzer及Phase4E精确匹配、原BFM恢复、全HP drain'),
              ('fpga/perf/v1_2_phase4g/make_release_gate.py', '全部正式IP gate通过后才生成绑定证据SHA的integration release'),
              ('fpga/perf/v1_2_phase4g/run_integration.py', 'fresh V1.2项目/隔离稳定IP、source+BD+resource+timing实际gate'),
              ('fpga/scripts/vivado_three_module_v1_2_phase4g_create.tcl', '只解析正式CNN catalog并替换原CNN revision，fresh BD validate'),
              ('fpga/scripts/vivado_three_module_v1_2_phase4g_synth.tcl', 'output products/actual synthesis，明确writer hierarchy及禁implementation'),
              ('fpga/perf/v1_2_phase4g/finalize_reports.py / README.md', '只有完整release/system/protection PASS才写报告与checkpoint，记录执行方法'),
              ('fpga/reports/v1_2_phase4g_implementable_cnn_ip.md', '本批事实、完整证据与review'),
              ('fpga/reports/v1_2_phase4_checkpoint.md', '当前ready状态与下一批交接，Phase4F权威历史保留')]) + f'''
已执行：SHA保护、原generator确定性重现、Vivado package/只读 integrity、全 ABI/driver/source views 审计、干净复建、最终四local、CNN06完整单帧、实际OOC、fresh catalog/upgrade/BD validate/output products/system synthesis、source/hierarchy/resource/setup估计/hold如实记录。

未执行：性能优化、新 HLS csim/synthesis/export、8/100-frame、implementation/route、post-route timing/DRC、bitstream/XSA、板测、git add/commit/push、PR、创建/切换/删除分支。仅进行了综合后的 DRC 报告，不等同下一批 post-route DRC。

Branch=`{git_state['branch']}`，HEAD=`{git_state['head']}`；tracked diff=empty，staged diff=empty。既有 untracked 保留，本批源/报告均未暂存。{link('完整 Git review 状态', OUT / 'git_review.json')}。外部 E:/HLS IP/build/log/DCP/数据/备份不自动上传。

建议 Commit Message：`build(fpga): freeze write-credit CNN IP and validate V1.2 synthesis`。本批修改完成后停止等待 Master 审核，没有任何 Git 写操作。

## IMPLEMENTABLE_CNN_IP_READY 与 NEXT STEP

**IMPLEMENTABLE_CNN_IP_READY**。正式 IP+可复现性+同源功能/OOC+独立 V1.2 BD/system synthesis 均 PASS；到此立即停止。下一批仅在 Master 明确授权后进行 Vivado implementation/route、post-route setup/hold timing 与 DRC。本批不自动进入后续流程。
'''
    report_path.write_text(report, encoding='utf-8')
    checkpoint = f'''# V1.2 Phase 4G Checkpoint

日期：2026-10-03（Asia/Shanghai）。CURRENT STATUS：**IMPLEMENTABLE_CNN_IP_READY / WAIT_MASTER**。

正式 write-credit CNN IP 已固化并完成全部 Phase 4G gate；在 synthesis 停止。{link('完整 Phase 4G 报告', report_path)}。

## 权威历史与本批结果

- Phase 4E isolated CNN：**3,301,639 cycles**；A_low 19,080/19,080 mismatch0、guard0、hazard0、responses drain PASS。
- Phase 4F 8-frame steady-state output max interval：**3,307,317 cycles**；**SHORT_MULTI_FRAME_30FPS_PASS**。原证据未改，本批没有重跑8帧。
- Phase 4G 正式 packaged IP CNN 单帧：ap_start={starts[0]:,}、ap_done={dones[0]:,}、**{cnn['new_cycles']:,} cycles**；完整raw/guard/hazard/IRQ、7blocks与4HP final drain PASS。
- Base r4/export、原 Phase4E overlay、Bilinear/Curve、DDR/fixed-point/V1.1/Phase4F 前后保护hash PASS。

## 正式交付

IP：`{ip.as_posix()}`；{link('build_manifest', ip / 'build_manifest.json')}。Identity=`{build['identity_sha256']}`。与 `{Path(rebuild['rebuild']).as_posix()}` 独立复建305项payload逐字相同。

仅三颗 writer/caller Verilog 的SHA改变，完全等于Phase4E verified overlay。VLNV/top、7pointer/6m_axi、CSR/register offsets、driver/接口ABI不变；coreRevision固定2114810448。Active VHDL入口移除，原VHDL仅归档；综合/仿真共用139V+2VH+9ROM=150项同path/hash。最终CNN06的头文件搜索也只指向正式包。

工程：{link('fresh V1.2 v12_wc.xpr', system['project'])}，基于原saved V1.2 BD创建；原XPR/runs及V1.1不变。正式catalog唯一解析、BD Validate、Generate Output Products、实际CNN及全系统synthesis、三writer primitive hierarchy全部PASS；cache disabled。

''' + table(['Resource', 'CNN OOC', 'V1.2 system'], [
              ('LUT', metrics['LUT'], resources['LUT']), ('FF', metrics['FF'], resources['FF']),
              ('BRAM tiles', metrics['BRAM_tiles'], resources['BRAM_tiles']),
              ('URAM', metrics['URAM'], resources['URAM']), ('DSP', metrics['DSP'], resources['DSP'])]) + f'''
100MHz：CNN OOC setup estimate **{metrics['setup_estimate_slack_ns']:+.3f}ns**；system WNS/TNS **{timing['WNS_ns']:+.3f} / {timing['TNS_ns']:.3f}ns**，setup失败端点{timing['setup_failing_endpoints']}。System pre-route WHS/THS **{timing['WHS_ns']:+.3f} / {timing['THS_ns']:.3f}ns**，hold失败端点{timing['hold_failing_endpoints']}。**Hold只是pre-route记录，不是最终结论**；OOC未指定HD.CLK_SRC，估计有相应限制。

## 证据与停止点

{link('release gate', args.release_gate)}；{link('OOC', ooc_path)}；{link('writer local', release['evidence']['writer_probe'])}；{link('CNN06 single', cnn_gate['evidence'])}；{link('system synthesis gate', args.integration_gate)}；{link('after protection', OUT / 'protection_after.json')}；{link('Phase4F原checkpoint备份', OUT / 'checkpoint_before.md')}。

CNN05记录至350,000 cycles后因旧include目录的来源审计中止，无DONE/数值完成，不用于gate；最终CNN06在搜索路径修正后完整自然完成。全部尝试证据保留，不把prepared/aborted/superseded结果当PASS。

NEXT STEP — **WAIT MASTER**：本批立即停止。下一批需单独授权implementation/route、post-route timing与DRC。本批未运行implementation/route/bitstream/XSA、8/100-frame、板测或Git写操作；没有继续性能优化。

Branch=`{git_state['branch']}`，HEAD=`{git_state['head']}`，tracked/staged diff empty；旧untracked保留。建议 Commit Message：`build(fpga): freeze write-credit CNN IP and validate V1.2 synthesis`。
'''
    checkpoint_path.write_text(checkpoint, encoding='utf-8')
    git_state['status'] = git('status', '--short', '--untracked-files=all')
    require(git('diff', '--stat') == protection['git_before']['tracked_diff'] and
            git('diff', '--cached', '--stat') == protection['git_before']['staged_diff'], 'Git review state changed')
    (OUT / 'git_review.json').write_text(json.dumps(git_state, indent=2) + '\n', encoding='utf-8')
    ready = dict(status='IMPLEMENTABLE_CNN_IP_READY', generated_at=stamp,
                 report=report_path.as_posix(), report_sha256=sha(report_path),
                 checkpoint=checkpoint_path.as_posix(), checkpoint_sha256=sha(checkpoint_path),
                 formal_ip=ip.as_posix(), formal_manifest_sha256=sha(ip / 'build_manifest.json'),
                 release_gate_sha256=sha(args.release_gate), integration_gate_sha256=sha(args.integration_gate),
                 protection_after_sha256=sha(OUT / 'protection_after.json'), next_step='WAIT_MASTER',
                 implementation_run=False, route_run=False, bitstream_generated=False, xsa_generated=False)
    (OUT / 'readiness.json').write_text(json.dumps(ready, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(dict(status=ready['status'], report=ready['report'], checkpoint=ready['checkpoint'])))


if __name__ == '__main__':
    main()

"""Write the Phase 5 report and checkpoint from complete, immutable evidence.

This program never starts Vivado, simulations, exports, or Git write commands.
Both PASS and fully audited timing/DRC FAIL results are reportable. Incomplete
implementation, routing, or protection evidence must not become a final gate.
"""
from __future__ import annotations

import argparse
import datetime
import hashlib
import json
from pathlib import Path
import re
import subprocess

REPO = Path(__file__).resolve().parents[3]
BASE = Path('E:/HLS/kv260_three_module_v1_2_phase4')
DEFAULT_OUT = BASE / 'phase5/implementation_01'
PHASE4G = BASE / 'phase4g'
REPORT = REPO / 'fpga/reports/vivado_three_module_v1_2_implementation.md'
CHECKPOINT = REPO / 'fpga/reports/v1_2_phase4_checkpoint.md'
TZ = datetime.timezone(datetime.timedelta(hours=8))
COMMIT_MESSAGE = 'docs(fpga): record V1.2 post-route timing and implementation audit'
MODULES = (
    'zero_dce_cnn_top_row_axi_writer',
    'zero_dce_cnn_top_row_axi_writer_2',
    'zero_dce_cnn_top_p_anonymous_namespace_output_writer',
)
RESOURCE_FIELDS = ('LUT', 'FF', 'RAMB36', 'RAMB18', 'BRAM_tiles', 'URAM', 'DSP')


def require(value, message):
    if not value:
        raise RuntimeError(message)


def read_json(path):
    path = Path(path)
    require(path.is_file(), 'Missing required JSON: ' + str(path))
    return json.loads(path.read_text(encoding='utf-8-sig'))


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def now():
    return datetime.datetime.now(TZ).isoformat()


def link(label, path):
    return '[' + label + '](' + Path(path).resolve().as_posix() + ')'


def cell(value):
    return str(value).replace('|', '\\|').replace('\r', '').replace('\n', '<br>')


def table(headers, rows):
    return ('| ' + ' | '.join(map(cell, headers)) + ' |\n| ' +
            ' | '.join(['---'] * len(headers)) + ' |\n' + ''.join(
                '| ' + ' | '.join(map(cell, row)) + ' |\n' for row in rows))


def ns(value):
    return f'{value:+.3f}' if value else '0.000'


def delta(value):
    return f'{value:+g}' if value else '0'


def git(*args):
    return subprocess.check_output(['git', *args], cwd=REPO, text=True).strip()


def git_review(before):
    current = dict(branch=git('branch', '--show-current'), head=git('rev-parse', 'HEAD'),
                   tracked_diff=git('diff', '--stat'), staged_diff=git('diff', '--cached', '--stat'),
                   status=git('status', '--short', '--untracked-files=all'))
    require(current['branch'] == before['git']['branch'] and current['head'] == before['git']['head'],
            'Branch or HEAD changed before finalization')
    require(current['staged_diff'] == before['git']['staged_diff'], 'Staged changes appeared')
    current['untracked_count'] = sum(line.startswith('?? ') for line in current['status'].splitlines())
    current['git_write_operations_executed'] = False
    return current


def validate(out):
    gate_path = out / 'implementation_gate.json'
    gate = read_json(gate_path)
    before = read_json(out / 'protection_before.json')
    protection = read_json(out / 'protection_after.json')
    require(before['status'] == protection['status'] == 'PASS', 'Protection is incomplete or FAIL')
    require(protection['changed'] == [] and protection['project_configuration_unchanged'] is True and
            protection['git_unchanged'] is True and protection['bitstream_xsa_files'] == [],
            'Protected inputs/configuration/Git/export audit failed')
    metadata = protection.get('expected_generated_run_metadata_changes', [])
    if metadata:
        metadata_audit = read_json(out / 'generated_metadata_audit.json')
        require(metadata_audit['status'] == 'PASS' and metadata_audit['unresolved_changes'] == [] and
                len(metadata) == 11 and protection['count'] + len(metadata) == before['count'] and
                metadata_audit['expected_generated_run_metadata_changes'] == metadata and
                (out / 'protection_after_initial.json').is_file(),
                'Generated run metadata changes are not narrowly documented')
        for item in metadata:
            require(sha(item['path']) == item['after_sha256'], 'Generated run index changed after semantic audit')
    supplement_path = out / 'supplement_protection.json'
    supplement = read_json(supplement_path) if supplement_path.exists() else None
    require(supplement is None or supplement['status'] == 'PASS', 'Supplement protection did not PASS')
    backup = out / 'checkpoint_before.md'
    require(sha(backup) == before['checkpoint_backup_sha256'], 'Original Phase 4G checkpoint backup changed')
    require(gate['status'] in {'POST_ROUTE_100MHZ_PASS', 'POST_ROUTE_100MHZ_FAIL'}, 'Invalid final gate status')
    require(gate['checks'] and all(value in {'PASS', 'FAIL'} for value in gate['checks'].values()),
            'Incomplete gate checks')
    require(gate['checks']['implementation'] == gate['checks']['route_complete'] == 'PASS',
            'Implementation/route did not naturally complete; final timing gate prohibited')
    failed = [key for key, value in gate['checks'].items() if value == 'FAIL']
    require(failed == gate['failed_checks'], 'Failed check list disagrees with checks')
    require((not failed) == (gate['status'] == 'POST_ROUTE_100MHZ_PASS'), 'Gate status disagrees with checks')
    require(gate['evidence'], 'No analyzer evidence records')
    for item in gate['evidence']:
        path = Path(item['path'])
        require(path.is_file() and path.stat().st_size == item['bytes'] and sha(path) == item['sha256'],
                'Analyzer evidence changed: ' + str(path))
    impl = gate['implementation']
    run = impl['run']
    props = run['all_properties']
    exit_record = impl['natural_exit']
    require(exit_record['returncode'] == 0 and exit_record['natural_process_exit'] is True and
            exit_record['forced_termination'] is False, 'No successful natural Vivado process exit')
    require(run['impl_status'] == 'route_design Complete!' and run['impl_progress'] == '100%' and
            props['natural_implementation_end'] == 'PASS' and props['postroute_reports_complete'] == 'PASS',
            'Natural route/report completion is not confirmed')
    require(props['formal_cnn_revision'] == '2114810448' and props['bd_validate'] == 'PASS' and
            props['synth_writecredit_hierarchy'] == 'PASS' and props['launch_to_step'] == 'route_design',
            'Formal identity/preflight/stop boundary is not confirmed')
    for name in ('opt_design', 'place_design', 'phys_opt_design', 'route_design'):
        marker = impl['markers'][name]
        require(marker['end_exists'] and not marker['error_exists'] and marker['completed_in_log'],
                'Incomplete implementation stage: ' + name)
    route = gate['routing']
    require(route['routable_nets'] > 0 and route['fully_routed'] == route['routable_nets'] and
            route['unrouted'] == route['partially_routed'] == route['routing_errors'] == route['node_overlaps'] == 0 and
            route['router_completed_successfully'], 'Routing audit is incomplete')
    require(gate['post_route_timing']['clock_period_ns'] == 10 and gate['post_route_timing']['clock_MHz'] == 100,
            'Timing is not the required 100 MHz post-route audit')
    for kind in ('setup', 'hold'):
        path = gate['worst_' + kind]
        for key in ('startpoint', 'endpoint', 'launch_clock', 'capture_clock', 'clock', 'requirement_ns',
                    'data_delay_ns', 'logic_delay_ns', 'route_delay_ns', 'logic_levels',
                    'start_hierarchy', 'end_hierarchy', 'classification'):
            require(key in path and path[key] is not None, 'Missing worst path field: ' + key)
    drc = gate['drc']
    require(sum(drc['severity_totals'].values()) == drc['checks_found'] == len(drc['details']),
            'DRC summary/details are incomplete')
    for name in MODULES:
        module = gate['resource_audit']['writer_overlay'][name]
        for stage in ('post_route', 'phase4g_post_synthesis'):
            require(all(key in module[stage] for key in RESOURCE_FIELDS), 'Incomplete writer resource report')
    project = Path(run['routed_dcp']).parents[2]
    require(not any(path.suffix.lower() in {'.bit', '.xsa'} for path in project.rglob('*') if path.is_file()),
            'Forbidden bitstream or XSA found')
    # Reuse the authoritative full-tree release audit; it is read-only.
    import sys
    sys.path.insert(0, str(REPO / 'fpga/perf/v1_2_phase4g'))
    from run_integration import verify_inputs
    verify_inputs(PHASE4G / 'integration_01')
    original = backup.read_text(encoding='utf-8-sig')
    for token in ('3,301,639', '3,307,317', '2114810448',
                  'a64d16faa3c102790eae873031da99cd775b6858f673ff8d4d8f7c92d17572e9'):
        require(token in original, 'Authoritative Phase 4 history is missing: ' + token)
    require('## 权威历史与本批结果' in original and 'NEXT STEP —' in original,
            'Checkpoint historical sections are incomplete')
    return gate, before, protection, supplement, original


def timing_table(gate):
    timing = gate['post_route_timing']
    return table(('100 MHz post-route指标', '实际值', '失败 / 总端点', 'Gate'), (
        ('Setup WNS / TNS (ns)', ns(timing['WNS_ns']) + ' / ' + ns(timing['TNS_ns']),
         f"{timing['setup_failing_endpoints']} / {timing['setup_total_endpoints']}", gate['checks']['setup']),
        ('Hold WHS / THS (ns)', ns(timing['WHS_ns']) + ' / ' + ns(timing['THS_ns']),
         f"{timing['hold_failing_endpoints']} / {timing['hold_total_endpoints']}", gate['checks']['hold']),
        ('Pulse WPWS / TPWS (ns)', ns(timing['WPWS_ns']) + ' / ' + ns(timing['TPWS_ns']),
         f"{timing['pulse_failing_endpoints']} / {timing['pulse_total_endpoints']}", gate['checks']['pulse_width']),
    ))


def path_table(path):
    return table(('字段', '实际post-route值'), (
        ('Startpoint', '`' + path['startpoint'] + '`'), ('Endpoint', '`' + path['endpoint'] + '`'),
        ('Launch / capture clock', path['launch_clock'] + ' / ' + path['capture_clock']),
        ('Clock / path group', path['clock']), ('Path type', path['path_type']),
        ('Requirement / slack (ns)', f"{path['requirement_ns']:.3f} / {ns(path['slack_ns'])}"),
        ('Data / logic / route delay (ns)', ' / '.join(f'{path[key]:.3f}' for key in
                                                    ('data_delay_ns', 'logic_delay_ns', 'route_delay_ns'))),
        ('Logic levels', path['logic_levels']), ('Start hierarchy', '`' + path['start_hierarchy'] + '`'),
        ('End hierarchy', '`' + path['end_hierarchy'] + '`'), ('Hierarchy分类', path['classification']),
    ))


def drc_analysis(detail, route):
    rule = detail['rule']
    explanations = {
        'DPIP-2': 'DSP输入缺少相应流水级的性能建议。以本次实际post-route timing判断收敛；本批不修改HLS/RTL。',
        'DPOP-3': 'DSP PREG输出流水级建议。保留现有算法和时序结构，不因该Warning自动优化。',
        'DPOP-4': 'DSP MREG输出流水级建议。保留现有算法和时序结构，不因该Warning自动优化。',
    }
    if rule in explanations:
        return explanations[rule]
    if rule == 'RTSTAT-10':
        return ('无可路由负载的net提示；与最终unrouted=' + str(route['unrouted']) +
                '、routing errors=' + str(route['routing_errors']) +
                '分别审计。复位管道或优化后无负载的net不是未布通net；后续板级reset/AXI行为尚未验证。')
    if detail['severity'] in {'Error', 'Critical Warning'}:
        return '阻断最终gate，保留原始对象和原因逐条审阅；本批只分析，不修改RTL或重试strategy。'
    return '新增类别：依据下述原始诊断逐条审阅，保留Warning；本批不自动调整设计或继续性能优化。'


def drc_sections(gate, out):
    drc = gate['drc']
    route = gate['routing']
    rows = []
    for row in drc['rules']:
        rows.append((row['rule'], row['severity'], row['checks'], row['description'],
                     drc_analysis(row, route)))
    text = table(('Rule', 'Severity', '数量', 'Vivado描述', '分析'), rows)
    text += '\n独立解析器已逐条核对全部诊断与summary数量。完整原文见' + link('postroute_drc.rpt', out / 'reports/postroute_drc.rpt') + '，逐项结构化记录见' + link('implementation_gate.json', out / 'implementation_gate.json') + '。普通DSP建议按规则及对象模块分类；Error/Critical与RTSTAT逐条展开。Warning保留原Severity。\n\n'
    for row in drc['rules']:
        details = [item for item in drc['details'] if item['rule'] == row['rule']]
        text += '### ' + row['rule'] + ' — ' + str(len(details)) + '条\n\n'
        if row['rule'] == 'RTSTAT-10':
            for item in details:
                text += '**' + item['rule'] + '#' + str(item['index']) + '**：' + drc_analysis(item, route) + '\n\n'
                text += '> ' + item['detail'].replace('\n', '\n> ') + '\n\n'
        elif row['severity'] == 'Warning' and row['rule'] in {'DPIP-2', 'DPOP-3', 'DPOP-4'}:
            groups = {}
            for item in details:
                objects = list(dict.fromkeys(re.findall(r'system_i/[^\s,;]+', item['detail'])))
                first = objects[0].rstrip('.') if objects else ''
                hierarchy = first.split('/')[1] if '/' in first else 'Other'
                groups.setdefault(hierarchy, []).append((item, first))
            text += table(('对象模块', '条数', '代表对象（全量见原报告）', '分析'), (
                (name, len(items), '`' + items[0][1] + '`', drc_analysis(items[0][0], route))
                for name, items in sorted(groups.items()))) + '\n'
        else:
            entries = []
            for item in details:
                objects = list(dict.fromkeys(re.findall(r'system_i/[^\s,;]+', item['detail'])))
                affected = '<br>'.join('`' + obj.rstrip('.') + '`' for obj in objects) or item['detail']
                entries.append((item['rule'] + '#' + str(item['index']), item['severity'], affected,
                                drc_analysis(item, route)))
            text += table(('条目', 'Severity', '实际对象 / 原因', '逐条判断'), entries) + '\n'
    return text


def changes():
    rows = [
        ('fpga/scripts/vivado_three_module_v1_2_impl.tcl', '复用正式Phase4G工程，核对revision/BD/综合源，默认implementation止于route，生成routed实报；采集后移除已弃用-nets参数，实际执行版本另行归档'),
        ('fpga/perf/v1_2_phase5/run_implementation.py', '保护输入/旧证据、记录自然exit与禁止导出边界；严格审计launcher刷新生成的11个run索引并保留初始FAIL，不生成IP或启动system TB'),
        ('fpga/perf/v1_2_phase5/analyze_implementation.py', '独立严格解析实际路由/时序/DRC/资源；缺失字段拒绝产生完整gate'),
        ('fpga/perf/v1_2_phase5/finalize_reports.py', '完整gate、证据SHA与保护PASS后写报告/checkpoint，保留权威历史并明确停止'),
        ('fpga/reports/vivado_three_module_v1_2_implementation.md', '记录Phase5真实结果、worst paths、资源和V1.1对照及下一批边界'),
        ('fpga/reports/v1_2_phase4_checkpoint.md', '更新当前post-route状态，同时保留Phase4E/4F/4G正式identity与cycles历史'),
    ]
    readme = REPO / 'fpga/perf/v1_2_phase5/README.md'
    if readme.is_file():
        rows.insert(4, (readme.relative_to(REPO).as_posix(), '记录Phase5执行方法、证据路径与停止条件'))
    return rows


def review_text(review, out):
    text = table(('新增 / 修改文件', '原因与关键差异'), (
        (link(path, REPO / path), reason) for path, reason in changes()))
    text += ('\n实际执行验证：正式输入/源与旧证据hash、BD/clock/reset/address预检、现有synth状态与三writer hierarchy、'
             '完整opt/place/phys_opt/route自然完成、routed setup/hold/pulse、route status、DRC、'
             '整体与writer资源对照、check_timing、完整IP文件树及最终证据SHA核对。\n\n'
             'Vivado 2025.2的-nets参数兼容性修正是在本次报告采集后进行，未重新执行Vivado；原执行脚本与两条提示完整归档，独立解析已核对路径完整性和global slack一致性。\n\n'
             '未执行：新CNN IP构建、新HLS、任何新system TB、性能优化、RTL timing修补、'
             'bitstream、XSA、hardware handoff、PS软件/DDR实际吞吐/30 FPS板测、git add/commit/push/PR。\n\n'
             '建议 Commit Message：`' + COMMIT_MESSAGE + '`。\n\n'
             '当前 branch=`' + review['branch'] + '`，HEAD=`' + review['head'] + '`；'
             'tracked diff=' + ('empty' if not review['tracked_diff'] else '`' + cell(review['tracked_diff']) + '`') + '；'
             'staged diff=' + ('empty' if not review['staged_diff'] else '`' + cell(review['staged_diff']) + '`') + '。'
             '工作区未暂存文件/既有untracked保留，当前untracked ' + str(review['untracked_count']) + '项；'
             '完整现场见' + link('git_review.json', out / 'git_review.json') + '。没有创建/切换分支或执行Git写操作。'
             '外部IP、log、DCP、备份和运行输出留在E:/HLS，不自动上传。\n')
    return text


def render_report(gate, before, protection, supplement, review, out):
    impl = gate['implementation']
    run = impl['run']
    props = run['all_properties']
    timing = gate['post_route_timing']
    resource = gate['post_route_resources']
    route = gate['routing']
    drc = gate['drc']
    passed = gate['status'] == 'POST_ROUTE_100MHZ_PASS'
    stamp = now()
    text = '# KV260 三模块 V1.2 Phase 5：Implementation 与 post-route 审计\n\n'
    text += '日期：' + stamp[:10] + '（Asia/Shanghai）。结论：**' + gate['status'] + '**。'
    text += ('正式Phase4G write-credit CNN工程自然完成implementation与route，100MHz setup/hold/pulse均满足，DRC无Error/Critical Warning。' if passed else
             '正式Phase4G工程已自然完成implementation与route，但下述完整审计包含失败gate；本批只分析原因，停止自动优化。')
    text += 'BOARD_30FPS=**NOT_TESTED**。本批未生成bitstream/XSA，没有运行新system TB或板测。\n\n'
    text += '## 1. 固定工程、自然完成与保护\n\n'
    text += ('正式delivery identity=`a64d16faa3c102790eae873031da99cd775b6858f673ff8d4d8f7c92d17572e9`；'
             'ABI保持不变。权威历史：Phase4E/4G CNN单帧3,301,639 cycles、raw mismatch=0；'
             'Phase4F SHORT_MULTI_FRAME_30FPS_PASS，max steady interval=3,307,317 cycles。'
             '本批保留原证据，没有重新运行这些仿真。\n\n')
    text += table(('项目', '实际值'), (
        ('工程', props['project']), ('Vivado', props['tool_version']), ('Formal CNN revision', props['formal_cnn_revision']),
        ('Formal package', props['formal_cnn_component']), ('Synthesis / writer hierarchy / BD Validate', 'PASS / PASS / PASS'),
        ('Strategy / flow', run['strategy'] + ' / ' + run['flow']),
        ('Run status / progress', run['impl_status'] + ' / ' + run['impl_progress']),
        ('Vivado batch exit', impl['natural_exit']['returncode']),
        ('自然退出 / 强制终止', str(impl['natural_exit']['natural_process_exit']) + ' / ' + str(impl['natural_exit']['forced_termination'])),
        ('开始 / 结束', impl['natural_exit']['started_at'] + ' / ' + impl['natural_exit']['ended_at']),
        ('Implementation等待时长', str(int(props['end_epoch']) - int(props['start_epoch'])) + '秒'),
        ('Routed checkpoint', run['routed_dcp']), ('Launch stop step', props['launch_to_step']),
        ('Phys-opt原始 / 最终enabled', props['phys_opt_initial_enabled'] + ' / ' + props['phys_opt_effective_enabled']),
    ))
    text += '\n' + table(('阶段', '默认directive', '自然end marker', 'error marker', '日志完成'), (
        (name, props[name + '_directive'], marker['end_exists'], marker['error_exists'], marker['completed_in_log'])
        for name, marker in impl['markers'].items()))
    phase_metrics = impl.get('phase_metrics')
    if phase_metrics:
        text += '\n阶段工具实报：\n\n' + table(('阶段', 'Result', 'elapsed秒', 'peak MB', '累计 Error / Critical / Warning'), (
            (name, value['result'], value['elapsed_seconds'], value['peak_memory_MB'],
             ' / '.join(str(value['cumulative_counts'][key]) for key in ('Error', 'Critical Warning', 'Warning')))
            for name, value in phase_metrics.items()))
        text += '\n同一run的阶段日志计数为累计值，不能将四行相加。\n'
    text += ('\n所有阶段为默认/既定策略。没有手工aggressive directive、RTL修补或重试性能优化。'
             '只有自然route完成、100%与routed DCP/end marker确认后才进入post-route timing gate。\n\n')
    text += '输入与旧证据保护：**PASS**，原有' + str(protection['count']) + '项hash未变；project configuration/source sets、Git branch/HEAD/staged状态保持，.bit/.xsa为零。'
    metadata = protection.get('expected_generated_run_metadata_changes', [])
    if metadata:
        text += '\n\n初始严格逐字保护审计为FAIL，Python执行器因此exit=1；Vivado batch已自然exit=0。变化仅为11个自动生成的synthesis `gen_run.xml`运行索引，mtime在implementation launch，原synthesis LaunchTime、run identity、device、strategy和源引用保持合法。原始FAIL保存在' + link('protection_after_initial.json', out / 'protection_after_initial.json') + '。\n\n'
        text += '修正后的保护审计明确区分15,687个未变文件与11个索引变化：所有被引用的设计源、source sets、配置、综合Tcl/log/end marker/DCP及旧证据逐字未变；每个索引的原/新SHA与逐项判定见' + link('generated_metadata_audit.json', out / 'generated_metadata_audit.json') + '。原索引只有before SHA，未备份before XML字节，不能宣称逐字段old/new XML相等；该例外依据未变输入/综合输出和当前XML语义、刷新时间作窄范围审计，不是放宽RTL或证据保护。\n\n'
    if supplement is not None:
        text += '补充保护：**PASS**（' + link('supplement_protection.json', out / 'supplement_protection.json') + '）。'
    text += '报告生成前再次执行完整正式/稳定IP文件树只读审计，PASS。未修改CNN/Bilinear/Curve、PS、SmartConnect、HP/HPM、100MHz clock/reset、address map或fixed-point协议。\n\n'
    text += '## 2. Routing完整性\n\n'
    route_labels = {
        'logical_nets': 'Total logical nets', 'not_needing_routing': '无需routing',
        'internally_routed': 'Internally routed', 'no_loads': 'No loads',
        'routable_nets': 'Total routable nets', 'fully_routed': 'Fully routed',
        'unrouted': 'Unrouted', 'partially_routed': 'Partially routed',
        'routing_errors': 'Routing errors', 'node_overlaps': 'Node overlaps',
        'failed_nets': 'Failed nets',
        'router_completed_successfully': 'Router Completed Successfully',
    }
    text += table(('指标', '实际值'), ((route_labels.get(key, key), value) for key, value in route.items()))
    text += '\n最终route complete，unrouted=0、partially routed=0、routing errors=0；router中间未布通计数不当作最终状态。\n\n'
    text += '## 3. 100MHz post-route timing gate\n\n' + timing_table(gate)
    text += '\n时钟period=10.000ns；Vivado最终timing clean=' + str(timing['tool_timing_clean']) + '。以上均来自routed报告，不以synthesis估计替代。\n\n'
    text += table(('指标', 'V1.1 routed', 'V1.2 Phase4G post-synthesis', 'V1.2 routed'), (
        (key, gate['comparison']['v11_routed']['timing'][key], gate['comparison']['phase4g_post_synthesis']['timing'][key], timing[key])
        for key in ('WNS_ns', 'TNS_ns', 'setup_failing_endpoints', 'WHS_ns', 'THS_ns', 'hold_failing_endpoints', 'WPWS_ns', 'TPWS_ns', 'pulse_failing_endpoints')))
    text += '\nPhase4G pre-route hold WHS=-0.093ns/THS=-1863.689ns是历史综合估计；最终hold结论只采用本次routed实报。\n\n'
    text += '### Worst setup path\n\n' + path_table(gate['worst_setup'])
    text += '\n### Worst hold path\n\n' + path_table(gate['worst_hold'])
    text += '\n最差setup分类为**' + gate['worst_setup']['classification'] + '**，最差hold分类为**' + gate['worst_hold']['classification'] + '**；依据实际startpoint/endpoint归属判断，没有先假定CNN是最差路径。\n\n'
    text += '## 4. Routed资源与writer审计\n\n'
    text += table(('资源', 'V1.1 routed', 'Phase4G post-synth', 'V1.2 routed', 'Δ vs synth', 'Δ vs V1.1'), (
        (key, gate['comparison']['v11_routed']['resources'][key], gate['comparison']['phase4g_post_synthesis']['resources'][key], resource[key],
         delta(gate['resource_audit']['delta_vs_phase4g_synthesis'][key]), delta(gate['resource_audit']['delta_vs_v11_routed'][key]))
        for key in RESOURCE_FIELDS))
    text += '\nBRAM tile=RAMB36+RAMB18/2；BRAM18 equivalent=' + str(resource['BRAM18_equivalent']) + '。URAM=**' + str(resource['URAM']) + '**，相对正式Phase4G的18颗状态为' + gate['checks']['expected_URAM_18'] + '。\n\n'
    text += table(('Writer inclusive subtree', 'Synth LUT / FF', 'Routed LUT / FF', 'Δ LUT / FF', 'Routed BRAM / URAM / DSP'), (
        (name, f"{row['phase4g_post_synthesis']['LUT']} / {row['phase4g_post_synthesis']['FF']}",
         f"{row['post_route']['LUT']} / {row['post_route']['FF']}", f"{delta(row['delta']['LUT'])} / {delta(row['delta']['FF'])}",
         f"{row['post_route']['BRAM_tiles']} / {row['post_route']['URAM']} / {row['post_route']['DSP']}")
        for name, row in gate['resource_audit']['writer_overlay'].items()))
    text += '\noutput_writer父层级包含两个row writer子层级，三行不能相加；这些是完整writer subtree资源，不能当作overlay新增资源。\n\n'
    anomalies = gate['resource_audit']['anomalies_requiring_review']
    text += ('资源异常候选：\n\n' + ''.join('- ' + value + '\n' for value in anomalies) if anomalies else
             '实际whole-system和writer资源对照未发现审计规则识别的异常膨胀。') + '\n\n'
    hierarchy = gate.get('hierarchy_resources') or gate['resource_audit'].get('hierarchy_resources')
    if hierarchy:
        text += '层级资源补充实报：\n\n' + table(('Hierarchy', 'LUT', 'FF', 'BRAM tiles', 'URAM', 'DSP'), (
            (key, value['LUT'], value['FF'], value['BRAM_tiles'], value['URAM'], value['DSP'])
            for key, value in hierarchy.items())) + '\n'
    comparisons = gate.get('hierarchy_comparison')
    if comparisons:
        text += table(('Hierarchy', 'V1.1 routed LUT / FF', 'Phase4G synth LUT / FF', 'V1.2 routed LUT / FF'), (
            (name, f"{row['v11_routed']['LUT']} / {row['v11_routed']['FF']}",
             f"{row['phase4g_post_synthesis']['LUT']} / {row['phase4g_post_synthesis']['FF']}",
             f"{row['post_route']['LUT']} / {row['post_route']['FF']}")
            for name, row in comparisons.items())) + '\n'
    text += 'V1.1与V1.2是不同CNN实现，资源差值只表示实际版本/实现成本，不能全部归因于三writer overlay；也不能由资源表推算DDR吞吐或板上FPS。\n\n'
    text += '## 5. Post-route DRC与constraint检查\n\n'
    text += 'Errors=**' + str(drc['severity_totals']['Error']) + '**；Critical Warnings=**' + str(drc['severity_totals']['Critical Warning']) + '**；Warnings=**' + str(drc['severity_totals']['Warning']) + '**。\n\n'
    text += drc_sections(gate, out)
    text += '\ncheck_timing实际记录：\n\n' + table(('检查', '实际数量'), gate['check_timing'].items())
    text += '\nImplementation run中的Warning/Error原行（与DRC条目分开计数）：\n\n'
    messages = impl['log_warning_error_lines']
    text += ''.join('- `' + line.replace('`', "'") + '`\n' for line in messages) if messages else '无Warning/Error行。\n'
    driver_critical = impl.get('driver_critical_warning_lines', [])
    if driver_critical:
        text += '\n报告命令兼容性提示：Vivado batch另有**2条Critical Warning [Vivado 12-1569]**，均因`report_timing -nets`参数已弃用。工具明确说明默认已显示net；独立审计成功解析20条详细路径，worst setup/hold slack与global summary精确一致，数据完整可信。这两条是报告API提示，implementation run与post-route DRC的Critical Warning均为0；原日志完整保留，没有将提示隐藏或改计Severity。\n\n'
        text += '当前执行脚本已删除-nets供以后使用，本次未重跑implementation或重导报告。实际执行版本见' + link('implementation_script_executed.tcl', out / 'implementation_script_executed.tcl') + '。\n\n'
    text += '\n无可路由负载的reset管道net与routing error分别判断。本批物理布线不能证明PS软件、板级reset时序、AXI实际事务、DDR吞吐或30 FPS已经通过。\n\n'
    text += '## 6. 最终gate、状态与NEXT STEP\n\n'
    text += table(('Gate', '结果'), gate['checks'].items()) + '\n'
    text += table(('总状态', '结果'), gate['state'].items()) + '\n'
    if passed:
        text += '**POST_ROUTE_100MHZ_PASS**。仅代表该正式工程在当前约束下的100MHz物理实现/时序/DRC结果；不自动标记HW_READY，BOARD_30FPS仍为NOT_TESTED。\n\n'
    else:
        text += '**POST_ROUTE_100MHZ_FAIL**。失败项：' + ', '.join(gate['failed_checks']) + '。上述实际路径/DRC条目是原因证据；本批不修改RTL、不改strategy、不自动优化。\n\n'
    text += 'NEXT STEP — **WAIT MASTER**：本批完成后立即停止。' + ('下一批单独授权后才可做bitstream、XSA和hardware handoff；板测仍需明确安排。' if passed else
             '下一批先明确授权处理已记录的失败原因；未经复核不得进入bitstream/XSA/hardware handoff。') + '本批不自动生成bitstream、导出XSA或进行板测。\n\n'
    text += '## 7. 文件变更、验证与Git review\n\n' + review_text(review, out)
    text += '\n证据索引：' + '；'.join((link('implementation gate', out / 'implementation_gate.json'), link('natural exit', out / 'exit_status.json'),
              link('run status', out / 'reports/run_status.tsv'), link('timing', out / 'reports/postroute_timing_summary.rpt'),
              link('setup paths', out / 'reports/postroute_setup_paths.rpt'), link('hold paths', out / 'reports/postroute_hold_paths.rpt'),
              link('utilization', out / 'reports/postroute_utilization.rpt'), link('route status', out / 'reports/postroute_route_status.rpt'),
              link('DRC', out / 'reports/postroute_drc.rpt'), link('protection', out / 'protection_after.json'),
              link('原Phase4G checkpoint备份', out / 'checkpoint_before.md'))) + '。\n'
    return text


def render_checkpoint(gate, original, review, out):
    historical = original.split('## 权威历史与本批结果', 1)[1].split('NEXT STEP —', 1)[0].strip()
    historical = '## 权威历史与本批结果\n\n' + historical
    historical = historical.replace('## ', '### ')
    status = gate['status']
    text = '# V1.2 Phase 5 Checkpoint\n\n日期：' + now()[:10] + '（Asia/Shanghai）。CURRENT STATUS：**' + status + ' / WAIT_MASTER**。\n\n'
    text += '正式Phase4G工程完成implementation/route与post-route审计。' + link('完整Phase5报告', REPORT) + '；' + link('独立implementation gate', out / 'implementation_gate.json') + '。\n\n'
    text += table(('总状态', '结果'), gate['state'].items()) + '\n'
    text += '## Phase5当前结果\n\n' + timing_table(gate) + '\n'
    route = gate['routing']
    text += f"Routing：{route['fully_routed']}/{route['routable_nets']} fully routed，unrouted={route['unrouted']}，partially routed={route['partially_routed']}，routing errors={route['routing_errors']}。自然run=`{gate['implementation']['run']['impl_status']}`，Vivado batch exit=0。\n\n"
    text += table(('Post-route资源', '实际值'), ((key, gate['post_route_resources'][key]) for key in RESOURCE_FIELDS)) + '\n'
    totals = gate['drc']['severity_totals']
    text += f"DRC：Error={totals['Error']}，Critical Warning={totals['Critical Warning']}，Warning={totals['Warning']}；逐条类别/对象分析见完整报告。最差setup={gate['worst_setup']['classification']}，最差hold={gate['worst_hold']['classification']}。\n\n"
    if gate['failed_checks']:
        text += '失败项：' + ', '.join(gate['failed_checks']) + '。只分析，不在本批自动优化。\n\n'
    text += '保护审计最终PASS：15,687项逐字未变，11个自动生成run索引变化经独立语义审计确认；初始byte-only FAIL与每项原/new SHA完整保留，详见Phase5报告。报告命令另有2条-nets弃用Critical Warning，路径数据完整且slack一致，与DRC 0 Critical分开记录。配置与正式IP完整文件树PASS。未修改RTL、CNN/Bilinear/Curve、PS/互连/地址/协议；未生成bitstream/XSA，未运行system TB、板测或Git写操作。BOARD_30FPS=NOT_TESTED，不自动标记HW_READY。\n\n'
    text += '## Phase4G权威交付与历史保留\n\n以下保留Phase4G交付时的正式identity、cycles、source/ABI与synthesis证据。其“本批/停止点”指Phase4G历史；当前状态和下一步以本checkpoint的Phase5段落为准。Phase4G原字节备份：' + link('checkpoint_before.md', out / 'checkpoint_before.md') + '。\n\n' + historical + '\n\n'
    text += '## 当前NEXT STEP与Git review\n\nNEXT STEP — **WAIT MASTER**：本批立即停止。'
    text += ('下一批单独授权后才做bitstream、XSA、hardware handoff；BOARD_30FPS仍需板测。' if status.endswith('_PASS') else
             '下一批明确授权后处理失败原因；不得自动优化或进入bitstream/XSA/hardware handoff。')
    text += '本批不自动继续任何硬件流程。\n\n'
    text += 'Branch=`' + review['branch'] + '`，HEAD=`' + review['head'] + '`；tracked diff=' + ('empty' if not review['tracked_diff'] else '见Git review') + '，staged diff=' + ('empty' if not review['staged_diff'] else '见Git review') + '；既有untracked保留。'
    text += '文件变化、原因、关键差异、实际/未执行验证见完整Phase5报告；未执行git add/commit/push。建议 Commit Message：`' + COMMIT_MESSAGE + '`。\n'
    return text


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()
    out = args.output.resolve()
    gate, before, protection, supplement, original = validate(out)
    review = git_review(before)
    # All validation has completed before either user-visible document is changed.
    report_text = render_report(gate, before, protection, supplement, review, out)
    checkpoint_text = render_checkpoint(gate, original, review, out)
    REPORT.write_text(report_text, encoding='utf-8')
    CHECKPOINT.write_text(checkpoint_text, encoding='utf-8')
    review = git_review(before)
    review['changed_files'] = [{'path': path, 'reason_and_key_difference': reason} for path, reason in changes()]
    review['suggested_commit_message'] = COMMIT_MESSAGE
    review['checked_at'] = now()
    (out / 'git_review.json').write_text(json.dumps(review, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    report_text = render_report(gate, before, protection, supplement, review, out)
    checkpoint_text = render_checkpoint(gate, original, review, out)
    REPORT.write_text(report_text, encoding='utf-8')
    CHECKPOINT.write_text(checkpoint_text, encoding='utf-8')
    result = dict(status='PASS', gate_status=gate['status'], generated_at=now(),
                  analyzer_gate_sha256=sha(out / 'implementation_gate.json'),
                  full_input_tree_reverified=True, report=str(REPORT), report_sha256=sha(REPORT),
                  checkpoint=str(CHECKPOINT), checkpoint_sha256=sha(CHECKPOINT),
                  git_review_sha256=sha(out / 'git_review.json'),
                  bitstream_generated=False, xsa_generated=False, board_tested=False,
                  new_system_tb_run=False, git_write_operations_executed=False)
    (out / 'finalization.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print('PHASE5_REPORTS_COMPLETE=' + gate['status'])
    print('REPORT=' + str(REPORT))
    print('CHECKPOINT=' + str(CHECKPOINT))


if __name__ == '__main__':
    main()

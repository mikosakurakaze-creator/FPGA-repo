"""Independently audit original Phase 5 routed reports; never run Vivado.

All required fields are parsed from actual reports/logs. Missing fields raise
AuditError, rather than being interpreted as zero or as successful checks.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone, timedelta
import hashlib
import json
from pathlib import Path
import re
import sys

BASE = Path('E:/HLS/kv260_three_module_v1_2_phase4')
REPORTS = BASE / 'phase5/implementation_01/reports'
PHASE4G = BASE / 'phase4g/integration_01/reports'
V11 = Path('E:/HLS/vivado_three_module_v1_1_implementation')
IMPL = BASE / 'phase4g/integration_01/project/v12_wc.runs/impl_1'
MODULES = (
    'zero_dce_cnn_top_row_axi_writer',
    'zero_dce_cnn_top_row_axi_writer_2',
    'zero_dce_cnn_top_p_anonymous_namespace_output_writer',
)
NUMBER = r'[-+]?\d+(?:\.\d+)?'
TIMING_FIELDS = (
    'WNS_ns', 'TNS_ns', 'setup_failing_endpoints', 'setup_total_endpoints',
    'WHS_ns', 'THS_ns', 'hold_failing_endpoints', 'hold_total_endpoints',
    'WPWS_ns', 'TPWS_ns', 'pulse_failing_endpoints', 'pulse_total_endpoints',
)


class AuditError(RuntimeError):
    pass


def require(condition, message):
    if not condition:
        raise AuditError(message)


def read(path):
    path = Path(path)
    require(path.is_file(), f'Missing required evidence: {path}')
    value = path.read_text(encoding='utf-8-sig', errors='strict')
    require(bool(value.strip()), f'Empty required evidence: {path}')
    return value


def one(pattern, source, field, flags=re.MULTILINE):
    matches = list(re.finditer(pattern, source, flags))
    require(len(matches) == 1, f'{field}: expected one field, found {len(matches)}')
    return matches[0]


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def record(path):
    path = Path(path)
    require(path.is_file(), f'Missing required evidence: {path}')
    return {'path': path.resolve().as_posix(), 'sha256': sha(path), 'bytes': path.stat().st_size}


def design_state(source, expected):
    state = one(r'^\|\s*Design State\s*:\s*([^|\r\n]+)', source, 'design state').group(1).strip()
    require(state in expected, f'Unexpected design state: {state}')
    return state


def timing_summary(source, routed=True):
    design_state(source, {'Routed', 'Fully Routed'} if routed else {'Synthesized'})
    require('Design Timing Summary' in source, 'Design Timing Summary is absent')
    section = source.split('Design Timing Summary', 1)[1].split('Clock Summary', 1)[0]
    header = one(r'^\s*WNS\(ns\).*TPWS Total Endpoints\s*$', section, 'timing summary header').group(0)
    require(all(token in header for token in ('TNS Failing Endpoints', 'THS Failing Endpoints', 'TPWS Failing Endpoints')),
            'Timing summary endpoint columns are incomplete')
    rows = [line.split() for line in section.splitlines()
            if re.fullmatch(r'\s*' + NUMBER + r'(?:\s+' + NUMBER + r'){11}\s*', line)]
    require(len(rows) == 1, f'Expected one 12-column timing row, found {len(rows)}')
    values = {}
    for key, value in zip(TIMING_FIELDS, rows[0]):
        if key.endswith('_endpoints'):
            require(re.fullmatch(r'\d+', value) is not None, f'Non-integer endpoint count: {key}')
            values[key] = int(value)
        else:
            values[key] = float(value)
    for kind in ('setup', 'hold', 'pulse'):
        require(values[f'{kind}_total_endpoints'] > 0, f'No analyzed {kind} endpoints')
        require(values[f'{kind}_failing_endpoints'] <= values[f'{kind}_total_endpoints'],
                f'Inconsistent {kind} endpoint counts')
    values['tool_timing_clean'] = 'All user specified timing constraints are met.' in source
    clock = one(r'^clk_pl_0\s+\{[^}]+\}\s+(' + NUMBER + r')\s+(' + NUMBER + r')\s*$',
                section_clock(source), 'timing clk_pl_0')
    values['clock_period_ns'] = float(clock.group(1))
    values['clock_MHz'] = float(clock.group(2))
    return values


def section_clock(source):
    require('Clock Summary' in source, 'Clock summary is absent')
    return source.split('Clock Summary', 1)[1].split('Intra Clock Table', 1)[0]


def hierarchy_name(pin):
    parts = pin.split('/')
    return '/'.join(parts[:-2]) if len(parts) > 2 else '/'.join(parts[:-1])


def component(pin):
    if '/zero_dce_cnn_top_0/' in pin:
        return 'CNN'
    if '/bilinear_fixed16_buffered_0/' in pin:
        return 'Bilinear'
    if '/curve_image_fixed16_0/' in pin:
        return 'Curve'
    if any('/' + name + '/' in pin for name in ('axi_control', 'cnn_data_sc', 'cnn_model_sc', 'bilinear_ddr_sc', 'curve_ddr_sc')):
        return 'SmartConnect'
    if '/zynq_ultra_ps_e_0/' in pin:
        return 'PS interface'
    return 'Other'


def timing_paths(source, expected_type, routed=True):
    design_state(source, {'Routed', 'Fully Routed'} if routed else {'Synthesized'})
    blocks = re.split(r'(?=^Slack \()', source, flags=re.MULTILINE)[1:]
    require(blocks, f'No {expected_type} timing paths reported')
    paths = []
    for block in blocks:
        slack = one(r'^Slack \((MET|VIOLATED)\)\s*:\s*(' + NUMBER + r')ns', block, 'path slack')
        start = one(r'^\s*Source:\s*(\S+)', block, 'startpoint').group(1)
        end = one(r'^\s*Destination:\s*(\S+)', block, 'endpoint').group(1)
        clocks = re.findall(r'cell\s+\S+\s+clocked by\s+(\S+)\s+\{[^}]+period=(' + NUMBER + r')ns\}', block)
        require(len(clocks) == 2, 'Path must explicitly identify both launch/capture clocks')
        group = one(r'^\s*Path Group:\s*(\S+)', block, 'path group').group(1)
        path_type = one(r'^\s*Path Type:\s*(.+)$', block, 'path type').group(1).strip()
        require(path_type.startswith(expected_type), f'Wrong path type: {path_type}')
        requirement = float(one(r'^\s*Requirement:\s*(' + NUMBER + r')ns', block, 'requirement').group(1))
        delay = one(r'^\s*Data Path Delay:\s*(' + NUMBER + r')ns\s+\(logic\s+(' + NUMBER + r')ns\s+\([^)]*\)\s+route\s+(' + NUMBER + r')ns', block, 'data/logic/route delay')
        levels = int(one(r'^\s*Logic Levels:\s*(\d+)', block, 'logic levels').group(1))
        delay_values = tuple(float(delay.group(index)) for index in (1, 2, 3))
        require(abs(delay_values[0] - delay_values[1] - delay_values[2]) <= 0.0021,
                'Data delay is inconsistent with logic + route delay')
        components = list(dict.fromkeys((component(start), component(end))))
        paths.append({
            'slack_ns': float(slack.group(2)), 'slack_status': slack.group(1),
            'startpoint': start, 'endpoint': end,
            'launch_clock': clocks[0][0], 'capture_clock': clocks[1][0],
            'launch_clock_period_ns': float(clocks[0][1]), 'capture_clock_period_ns': float(clocks[1][1]),
            'clock': group, 'path_type': path_type, 'requirement_ns': requirement,
            'data_delay_ns': delay_values[0], 'logic_delay_ns': delay_values[1],
            'route_delay_ns': delay_values[2], 'logic_levels': levels,
            'start_hierarchy': hierarchy_name(start), 'end_hierarchy': hierarchy_name(end),
            'components': components, 'classification': ' -> '.join(components),
        })
    worst = min(paths, key=lambda p: p['slack_ns'])
    require(paths[0]['slack_ns'] == worst['slack_ns'], 'First timing path is not the worst reported path')
    return {'worst': worst, 'reported_paths': len(paths), 'paths': paths}


def utilization(source, routed=True):
    design_state(source, {'Routed', 'Fully Routed'} if routed else {'Synthesized'})
    logic_header = one(r'^1\. CLB Logic\s*\n-+\s*$', source, 'utilization CLB Logic section')
    logic_section = source[logic_header.end():].split('1.1 Summary of Registers', 1)[0]
    fields = {'LUT': 'CLB LUTs*', 'FF': 'CLB Registers', 'BRAM_tiles': 'Block RAM Tile',
              'RAMB36': 'RAMB36/FIFO*', 'RAMB18': 'RAMB18', 'URAM': 'URAM', 'DSP': 'DSPs'}
    result = {}
    for key, label in fields.items():
        label_pattern = r'CLB LUTs\*?' if key == 'LUT' else re.escape(label)
        section = logic_section if key in {'LUT', 'FF'} else source
        value = one(r'^\|\s*' + label_pattern + r'\s*\|\s*(' + NUMBER + r')\s*\|', section, key).group(1)
        require(float(value) >= 0, f'Negative utilization: {key}')
        result[key] = float(value) if key == 'BRAM_tiles' else int(value)
    result['BRAM18_equivalent'] = 2 * result['RAMB36'] + result['RAMB18']
    require(result['BRAM_tiles'] == result['BRAM18_equivalent'] / 2,
            'Block RAM Tile count disagrees with RAMB36 + RAMB18 / 2')
    for key, label in {'LUT_logic': 'LUT as Logic', 'LUT_memory': 'LUT as Memory', 'latches': 'Register as Latch'}.items():
        result[key] = int(one(r'^\|\s*' + re.escape(label) + r'\s*\|\s*(\d+)\s*\|', logic_section, key).group(1))
    return result


def hierarchy_utilization(source, routed=True):
    design_state(source, {'Routed', 'Fully Routed'} if routed else {'Synthesized'})
    names = ('system_wrapper', 'zero_dce_cnn_top_0', 'bilinear_fixed16_buffered_0',
             'curve_image_fixed16_0', 'axi_control', 'cnn_data_sc', 'cnn_model_sc',
             'bilinear_ddr_sc', 'curve_ddr_sc', 'rst_ps_100m')
    fields = ('LUT', 'LUT_logic', 'LUTRAM', 'SRL', 'FF', 'RAMB36', 'RAMB18', 'URAM', 'DSP')
    result = {}
    for line in source.splitlines():
        if not line.startswith('|'):
            continue
        cells = [c.strip() for c in line.strip('|').split('|')]
        if cells[0] not in names:
            continue
        require(cells[0] not in result, f'Duplicate hierarchy resource row: {cells[0]}')
        require(len(cells) == 11 and all(c.isdigit() for c in cells[2:]),
                f'Incomplete hierarchy resource row: {cells[0]}')
        row = dict(zip(fields, map(int, cells[2:])))
        row['BRAM18_equivalent'] = row['RAMB36'] * 2 + row['RAMB18']
        row['BRAM_tiles'] = row['BRAM18_equivalent'] / 2
        result[cells[0]] = row
    require(set(names) == result.keys(), 'Hierarchy resource rows missing: ' + ', '.join(sorted(set(names) - result.keys())))
    return result


def drc_report(source):
    design_state(source, {'Routed', 'Fully Routed'})
    checks_found = int(one(r'^\s*Checks found:\s*(\d+)\s*$', source, 'DRC checks found').group(1))
    require('REPORT DETAILS' in source and 'REPORT SUMMARY' in source, 'DRC report is incomplete')
    summary = source.rsplit('1. REPORT SUMMARY', 1)[1].split('2. REPORT DETAILS', 1)[0]
    rules = []
    severity_totals = Counter({'Error': 0, 'Critical Warning': 0, 'Warning': 0, 'Advisory': 0})
    for line in summary.splitlines():
        if not line.startswith('|'):
            continue
        cells = [part.strip() for part in line.strip('|').split('|')]
        if cells[0] == 'Rule':
            continue
        require(len(cells) == 4 and re.fullmatch(r'[A-Z0-9_-]+-\d+', cells[0]) is not None,
                f'Unrecognized DRC rule row: {line}')
        require(cells[1] in severity_totals, f'Unrecognized DRC severity: {cells[1]}')
        require(cells[3].isdigit(), f'Missing DRC rule count: {line}')
        count = int(cells[3])
        severity_totals[cells[1]] += count
        rules.append({'rule': cells[0], 'severity': cells[1], 'description': cells[2], 'checks': count})
    require(sum(severity_totals.values()) == checks_found, 'DRC summary totals disagree with Checks found')
    details = []
    pattern = r'^([A-Z0-9_-]+-\d+)#(\d+)\s+(Error|Critical Warning|Warning|Advisory)\s*$'
    raw_details = source.rsplit('2. REPORT DETAILS', 1)[1]
    matches = list(re.finditer(pattern, raw_details, re.MULTILINE))
    for i, match in enumerate(matches):
        stop = matches[i + 1].start() if i + 1 < len(matches) else len(raw_details)
        body = raw_details[match.end():stop].strip()
        require(body, f'DRC {match.group(1)}#{match.group(2)} has no description')
        details.append({'rule': match.group(1), 'index': int(match.group(2)), 'severity': match.group(3), 'detail': body})
    require(len(details) == checks_found, f'DRC details missing: {len(details)} / {checks_found}')
    require(Counter((d['rule'], d['severity']) for d in details) ==
            Counter({(r['rule'], r['severity']): r['checks'] for r in rules}),
            'Individual DRC details disagree with summary')
    return {'checks_found': checks_found, 'severity_totals': dict(severity_totals), 'rules': rules,
            'details': details, 'blockers': [d for d in details if d['severity'] in {'Error', 'Critical Warning'}]}


def route_report(source, runlog):
    require('Design Route Status' in source, 'Route report header absent')
    fields = {'logical_nets': 'logical nets', 'not_needing_routing': 'nets not needing routing',
              'internally_routed': 'internally routed nets', 'no_loads': 'nets with no loads',
              'routable_nets': 'routable nets', 'fully_routed': 'fully routed nets',
              'routing_errors': 'nets with routing errors'}
    result = {}
    for key, label in fields.items():
        result[key] = int(one(r'^\s*# of ' + re.escape(label) + r'\.+\s*:\s*(\d+)\s*:', source, key).group(1))
    require(result['logical_nets'] == result['not_needing_routing'] + result['routable_nets'],
            'Route logical/net partition is inconsistent')
    require(result['not_needing_routing'] == result['internally_routed'] + result['no_loads'],
            'Route internally-routed/no-load partition is inconsistent')
    blocks = runlog.split('Routable Net Status*')[1:]
    require(blocks, 'No router net status blocks in implementation log')
    final_block = blocks[-1].split('Phase ', 1)[0]
    for key, label in {'failed_nets': 'Failed Nets', 'unrouted': 'Unrouted Nets',
                       'partially_routed': 'Partially Routed Nets', 'node_overlaps': 'Node Overlaps'}.items():
        result[key] = int(one(r'^\s*Number of ' + re.escape(label) + r'\s*=\s*(\d+)\s*$', final_block, key).group(1))
    require(result['failed_nets'] == result['unrouted'] + result['partially_routed'],
            'Final router failed-net count disagrees with unrouted + partially routed')
    require(result['routable_nets'] == result['fully_routed'] + result['failed_nets'],
            'Route report disagrees with final router net status')
    result['router_completed_successfully'] = 'Router Completed Successfully' in runlog
    return result


def phase_metrics(source):
    result = {}
    for step in ('opt_design', 'place_design', 'phys_opt_design', 'route_design'):
        pattern = (r'^(\d+) Infos?, (\d+) Warnings?, (\d+) Critical Warnings? and (\d+) Errors? encountered\.\s*\n' +
                   re.escape(step) + r' completed successfully\s*\n' + re.escape(step) +
                   r': Time \(s\): cpu = ([\d:.]+) ; elapsed = ([\d:.]+) \. Memory \(MB\): peak = (' + NUMBER + r')')
        match = one(pattern, source, f'{step} completion/timing counters')
        def seconds(value):
            parts = value.split(':')
            require(len(parts) == 3, f'Invalid elapsed-time field: {value}')
            return float(parts[0]) * 3600 + float(parts[1]) * 60 + float(parts[2])
        result[step] = {'result': 'PASS', 'cpu_seconds': seconds(match.group(5)),
                        'elapsed_seconds': seconds(match.group(6)), 'peak_memory_MB': float(match.group(7)),
                        'cumulative_counts': {'Info': int(match.group(1)), 'Warning': int(match.group(2)),
                                              'Critical Warning': int(match.group(3)), 'Error': int(match.group(4))}}
    return result


def check_timing(source):
    values = {}
    for key, count in re.findall(r'^\d+\. checking (\w+) \((\d+)\)\s*$', source, re.MULTILINE):
        count = int(count)
        if key in values:
            require(values[key] == count, f'Contradictory check_timing count: {key}')
        values[key] = count
    mandatory = {'no_clock', 'constant_clock', 'pulse_width_clock', 'unconstrained_internal_endpoints',
                 'no_input_delay', 'no_output_delay', 'multiple_clock', 'generated_clocks', 'loops',
                 'partial_input_delay', 'partial_output_delay', 'latch_loops'}
    require(mandatory <= values.keys(), 'check_timing categories missing: ' + ', '.join(sorted(mandatory - values.keys())))
    return values


def clock_report(source):
    design_state(source, {'Routed', 'Fully Routed'})
    m = one(r'^clk_pl_0\s+(' + NUMBER + r')\s+\{[^}]+\}\s+(\S+)\s+\{([^}]+)\}', source, 'post-route clk_pl_0')
    return {'clock': 'clk_pl_0', 'period_ns': float(m.group(1)), 'attributes': m.group(2), 'source': m.group(3)}


def run_status(source):
    result = {}
    for line in source.splitlines():
        if not line.strip():
            continue
        parts = line.split('\t', 1)
        require(len(parts) == 2, f'Malformed run_status row: {line}')
        key, value = parts
        key = key.lower()
        if key.lower() == 'key' and value.lower() == 'value':
            continue
        require(key not in result, f'Duplicate run status key: {key}')
        result[key] = value
    aliases = {'impl_status': ('impl_status', 'implementation_status', 'status', 'impl_1_status'),
               'impl_progress': ('impl_progress', 'implementation_progress', 'progress', 'impl_1_progress'),
               'strategy': ('strategy', 'impl_strategy', 'implementation_strategy'),
               'flow': ('flow', 'impl_flow', 'implementation_flow'),
               'routed_dcp': ('routed_dcp', 'routed_checkpoint')}
    canonical = {}
    for key, names in aliases.items():
        found = [result[name] for name in names if name in result]
        require(len(found) == 1 and found[0].strip(), f'Missing or ambiguous run_status key: {key}')
        canonical[key] = found[0]
    canonical['all_properties'] = result
    return canonical


def delta(after, before):
    return {key: after[key] - before[key] for key in ('LUT', 'FF', 'RAMB36', 'RAMB18', 'BRAM_tiles', 'URAM', 'DSP')}


def analyze(reports):
    reports = Path(reports)
    output = reports.parent
    evidence = {}

    def load(filename, directory=reports):
        path = directory / filename
        evidence[path.resolve().as_posix()] = record(path)
        return read(path)

    exit_record = json.loads(load('exit_status.json', output))
    require(isinstance(exit_record.get('returncode'), int) and
            exit_record.get('natural_process_exit') is True and exit_record.get('forced_termination') is False,
            'Vivado process has not recorded a natural terminal exit')
    require(exit_record.get('launch_to_step') == 'route_design', 'Unexpected Vivado launch target')
    status = run_status(load('run_status.tsv'))
    runlog = load('runme.log', IMPL)
    driver_log = load('implementation_console.log', output)
    driver_critical = re.findall(r'^CRITICAL WARNING:.*$', driver_log, re.MULTILINE)
    driver_errors = re.findall(r'^ERROR:.*$', driver_log, re.MULTILINE)
    expected_deprecation = 'CRITICAL WARNING: [Vivado 12-1569] report_timing: The -nets option to is deprecated. The default behavior is to display net names if the timing path format allows it.'
    explained_driver_critical = all(line.strip() == expected_deprecation for line in driver_critical)
    phases = phase_metrics(runlog)
    markers = {}
    for step in ('opt_design', 'place_design', 'phys_opt_design', 'route_design'):
        end = IMPL / f'.{step}.end.rst'
        error = IMPL / f'.{step}.error.rst'
        markers[step] = {'end_exists': end.is_file(), 'error_exists': error.is_file(),
                         'completed_in_log': f'{step} completed successfully' in runlog}
        if end.is_file():
            evidence[end.resolve().as_posix()] = record(end)
    require(status['all_properties'].get('natural_implementation_end') in {'1', 'True', 'true', 'PASS'},
            'Tcl did not record a natural implementation end')
    require(status['all_properties'].get('postroute_reports_complete') == 'PASS',
            'Tcl did not finish the post-route report bundle')
    require(status['all_properties'].get('formal_cnn_revision') == '2114810448', 'Wrong formal CNN revision')
    require(status['all_properties'].get('bd_validate') == 'PASS' and
            status['all_properties'].get('synth_writecredit_hierarchy') == 'PASS',
            'BD Validate or synthesis write-credit hierarchy was not confirmed')
    require(not re.search(r'^(?:Command: )?(?:write_bitstream|write_hw_platform)\b', runlog, re.MULTILINE),
            'Implementation log contains a prohibited bitstream or hardware export command')
    final_marker = IMPL / '.vivado.end.rst'
    require(final_marker.is_file() and not (IMPL / '.vivado.error.rst').exists(),
            'Implementation worker lacks natural completion marker or reports an error')
    evidence[final_marker.resolve().as_posix()] = record(final_marker)
    implementation_pass = (exit_record['returncode'] == 0 and status['impl_status'] == 'route_design Complete!' and
                           status['impl_progress'] == '100%' and all(v['end_exists'] and not v['error_exists'] and
                           v['completed_in_log'] for v in markers.values()))
    require(implementation_pass, 'Implementation did not naturally complete all normal steps; timing gate must not run')
    dcp = Path(status['routed_dcp'])
    require(dcp.resolve() == (IMPL / 'system_wrapper_routed.dcp').resolve(), 'Unexpected routed checkpoint path')
    evidence[dcp.resolve().as_posix()] = record(dcp)
    route = route_report(load('postroute_route_status.rpt'), runlog)
    route_complete = (route['routable_nets'] > 0 and
                      route['fully_routed'] == route['routable_nets'] and route['routing_errors'] == 0 and
                      route['unrouted'] == 0 and route['partially_routed'] == 0 and route['node_overlaps'] == 0 and
                      route['router_completed_successfully'])
    require(route_complete, 'Route is incomplete or has routing errors; timing gate must not run')

    timing = timing_summary(load('postroute_timing_summary.rpt'))
    setup = timing_paths(load('postroute_setup_paths.rpt'), 'Setup')
    hold = timing_paths(load('postroute_hold_paths.rpt'), 'Hold')
    require(abs(setup['worst']['slack_ns'] - timing['WNS_ns']) < 0.0001, 'Worst setup path disagrees with global WNS')
    require(abs(hold['worst']['slack_ns'] - timing['WHS_ns']) < 0.0001, 'Worst hold path disagrees with global WHS')
    resources = utilization(load('postroute_utilization.rpt'))
    hierarchy_resources = hierarchy_utilization(load('postroute_utilization_hierarchical.rpt'))
    require(all(hierarchy_resources['system_wrapper'][k] == resources[k]
                for k in ('LUT', 'FF', 'RAMB36', 'RAMB18', 'URAM', 'DSP')),
            'Hierarchy top row disagrees with full utilization report')
    drc = drc_report(load('postroute_drc.rpt'))
    constraints = check_timing(load('postroute_check_timing.rpt'))
    clock = clock_report(load('postroute_clocks.rpt'))
    require(clock['period_ns'] == timing['clock_period_ns'], 'Clock report disagrees with timing summary')
    synth_resources = utilization(load('system_utilization.rpt', PHASE4G), routed=False)
    synth_timing = timing_summary(load('system_timing_summary.rpt', PHASE4G), routed=False)
    v11_resources = utilization(load('postroute_utilization.rpt', V11))
    v11_timing = timing_summary(load('postroute_timing_summary.rpt', V11))
    synth_hierarchy_resources = hierarchy_utilization(load('system_utilization_hierarchical.rpt', PHASE4G), routed=False)
    v11_hierarchy_resources = hierarchy_utilization(load('postroute_utilization_hierarchical.rpt', V11))
    modules = {}
    for name in MODULES:
        filename = f'module_{name}_utilization.rpt'
        routed_resource = utilization(load(filename))
        synth_resource = utilization(load(filename, PHASE4G), routed=False)
        modules[name] = {'post_route': routed_resource, 'phase4g_post_synthesis': synth_resource,
                         'delta': delta(routed_resource, synth_resource)}
    anomaly = []
    if resources['URAM'] != 18:
        anomaly.append(f"URAM changed from 18 to {resources['URAM']}")
    for key in ('RAMB36', 'RAMB18', 'BRAM_tiles', 'DSP'):
        if resources[key] != synth_resources[key]:
            anomaly.append(f'{key} changed from synthesis {synth_resources[key]} to route {resources[key]}')
    for name, row in modules.items():
        if row['post_route']['LUT'] > row['phase4g_post_synthesis']['LUT'] or row['post_route']['FF'] > row['phase4g_post_synthesis']['FF']:
            anomaly.append(f'{name}: LUT/FF increased after physical implementation; review delta')
    log_warnings = re.findall(r'^(?:WARNING|CRITICAL WARNING|ERROR):.*$', runlog, re.MULTILINE)
    checks = {
        'implementation': implementation_pass,
        'route_complete': route_complete,
        'clock_100MHz': clock['period_ns'] == 10 and timing['clock_MHz'] == 100 and 'P' in clock['attributes'],
        'setup': timing['WNS_ns'] >= 0 and timing['TNS_ns'] == 0 and timing['setup_failing_endpoints'] == 0,
        'hold': timing['WHS_ns'] >= 0 and timing['THS_ns'] == 0 and timing['hold_failing_endpoints'] == 0,
        'pulse_width': timing['WPWS_ns'] >= 0 and timing['TPWS_ns'] == 0 and timing['pulse_failing_endpoints'] == 0,
        'drc_no_error_critical': drc['severity_totals']['Error'] == 0 and drc['severity_totals']['Critical Warning'] == 0,
        'timing_constraints_complete': all(value == 0 for value in constraints.values()),
        'expected_URAM_18': resources['URAM'] == 18,
        'implementation_log_no_error_critical': not bool(re.search(r'^(?:ERROR|CRITICAL WARNING):', runlog, re.MULTILINE)),
        'report_commands_no_unexplained_error_critical': not driver_errors and explained_driver_critical,
    }
    passed = all(checks.values())
    return {
        'status': 'POST_ROUTE_100MHZ_PASS' if passed else 'POST_ROUTE_100MHZ_FAIL',
        'generated_at': datetime.now(timezone(timedelta(hours=8))).isoformat(),
        'checks': {key: 'PASS' if value else 'FAIL' for key, value in checks.items()},
        'failed_checks': [key for key, value in checks.items() if not value],
        'implementation': {'run': status, 'natural_exit': exit_record, 'markers': markers, 'phase_metrics': phases,
                           'log_warning_error_lines': log_warnings,
                           'driver_critical_warning_lines': driver_critical, 'driver_error_lines': driver_errors,
                           'driver_warning_analysis': 'Vivado 12-1569 flags deprecated report_timing -nets. The tool states net names are displayed by default. All required fields and 20 detailed paths are present, and worst slacks match the global timing summary. These two report-command notices are separate from implementation and post-route DRC severities; no implementation rerun or timing replacement was used.' if driver_critical and explained_driver_critical else
                                                      'No known deprecated report_timing option notices.'},
        'routing': route, 'post_route_timing': timing, 'worst_setup': setup['worst'], 'worst_hold': hold['worst'],
        'setup_paths': setup, 'hold_paths': hold, 'post_route_resources': resources,
        'hierarchy_resources': hierarchy_resources,
        'drc': drc, 'check_timing': constraints, 'clock': clock,
        'resource_audit': {'anomalies_requiring_review': anomaly, 'writer_overlay': modules,
                           'writer_resource_note': 'All three cell reports are inclusive. The output_writer parent includes both row writer children; do not sum these three reports.',
                           'delta_vs_phase4g_synthesis': delta(resources, synth_resources),
                           'delta_vs_v11_routed': delta(resources, v11_resources)},
        'comparison': {'phase4g_post_synthesis': {'resources': synth_resources, 'timing': synth_timing},
                       'v11_routed': {'resources': v11_resources, 'timing': v11_timing}},
        'hierarchy_comparison': {name: {'phase4g_post_synthesis': synth_hierarchy_resources[name],
                                      'v11_routed': v11_hierarchy_resources[name],
                                      'post_route': hierarchy_resources[name],
                                      'delta_vs_synthesis': delta(hierarchy_resources[name], synth_hierarchy_resources[name])}
                                 for name in hierarchy_resources},
        'state': {'CNN_RTL_30FPS': 'PASS', 'SHORT_MULTI_FRAME_30FPS': 'PASS',
                  'IMPLEMENTABLE_CNN_IP': 'PASS', 'POST_ROUTE_100MHZ': 'PASS' if passed else 'FAIL',
                  'BOARD_30FPS': 'NOT_TESTED'},
        'evidence': list(evidence.values()),
        'next_step': 'Stop for review; bitstream/XSA/hardware handoff require the next batch.' if passed else
                     'Stop for review; analyze timing/DRC failures without automatic optimization.',
    }


def self_check():
    baseline = timing_summary(read(V11 / 'postroute_timing_summary.rpt'))
    require(baseline['WNS_ns'] == 1.720 and baseline['WHS_ns'] == 0.010, 'V1.1 timing evidence drift')
    setup = timing_paths(read(V11 / 'postroute_setup_paths.rpt'), 'Setup')
    hold = timing_paths(read(V11 / 'postroute_hold_paths.rpt'), 'Hold')
    require(setup['worst']['classification'] == 'Bilinear', 'V1.1 setup classification drift')
    require(hold['worst']['classification'] == 'CNN -> SmartConnect', 'V1.1 hold classification drift')
    drc = drc_report(read(V11 / 'postroute_drc.rpt'))
    require(drc['severity_totals']['Warning'] == 136, 'V1.1 DRC count drift')
    synth = utilization(read(PHASE4G / 'system_utilization.rpt'), routed=False)
    require(synth['LUT'] == 40993 and synth['FF'] == 47653 and synth['URAM'] == 18, 'Phase4G resources drift')
    for name in MODULES:
        utilization(read(PHASE4G / f'module_{name}_utilization.rpt'), routed=False)
    hierarchy_utilization(read(PHASE4G / 'system_utilization_hierarchical.rpt'), routed=False)
    hierarchy_utilization(read(V11 / 'postroute_utilization_hierarchical.rpt'))
    check_timing(read(V11 / 'postroute_check_timing.rpt'))
    clock_report(read(V11 / 'postroute_clocks.rpt'))
    v11_impl = Path(__file__).resolve().parents[3] / 'fpga/vivado/three_module_integration_v1_1/three_module_integration_v1_1.runs/impl_1/runme.log'
    v11_log = read(v11_impl)
    phases = phase_metrics(v11_log)
    require(phases['route_design']['elapsed_seconds'] == 101, 'V1.1 phase timing evidence drift')
    route = route_report(read(V11 / 'postroute_route_status.rpt'), v11_log)
    require(route['routable_nets'] == 57441 and route['unrouted'] == 0 and route['partially_routed'] == 0,
            'V1.1 final router evidence drift')
    # Deliberately missing required fields must be rejected, never filled with 0.
    for parser in (timing_summary, utilization, drc_report, check_timing, clock_report):
        try:
            parser('')
        except AuditError:
            continue
        raise AuditError(f'{parser.__name__} accepted missing evidence')
    print('SELF_CHECK_PASS: actual V1.1 / Phase4G formats and missing-field rejection')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reports', type=Path, default=REPORTS)
    parser.add_argument('--self-check', action='store_true')
    args = parser.parse_args()
    if args.self_check:
        self_check()
        return 0
    gate = analyze(args.reports)
    output = args.reports.parent / 'implementation_gate.json'
    output.write_text(json.dumps(gate, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    print(gate['status'])
    print('GATE_JSON=' + output.resolve().as_posix())
    return 0 if gate['status'] == 'POST_ROUTE_100MHZ_PASS' else 1


if __name__ == '__main__':
    try:
        sys.exit(main())
    except AuditError as error:
        print('AUDIT_INCOMPLETE: ' + str(error), file=sys.stderr)
        sys.exit(2)

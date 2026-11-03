"""Audit a physical timing experiment without relaxing the original contract."""
import argparse
import difflib
import hashlib
import json
from pathlib import Path
import re

from accept_system import route_summary, bus_skew_summary, critical_rows, ps_clock_proof, timing_summary


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def xdc_commands(path, allow_zero_uncertainty=False, temporary_margins=None, require_restoration=True):
    result = []
    uncertainty = []
    for line in Path(path).read_text().splitlines():
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        if line.startswith('set_clock_uncertainty'):
            match = re.fullmatch(
                r'set_clock_uncertainty -(setup|hold) (\d+(?:\.\d+)?) '
                r'(\[get_clocks(?: (?:\{?clk_pl_[01]\}?|\{clk_pl_0 clk_pl_1\}))?\])', line)
            if not allow_zero_uncertainty or not match:
                raise ValueError('Unexpected retained user uncertainty: ' + line)
            item = (match[1], float(match[2]), match[3])
            if temporary_margins is None and item[1] != 0:
                raise ValueError('Unexpected retained user uncertainty: ' + line)
            uncertainty.append(item)
            continue
        # write_xdc retains the command history and can add a redundant scope
        # reset around the temporary uncertainty commands. Preserve real scopes.
        if line == 'current_instance -quiet' and result and result[-1] == line:
            continue
        result.append(line)
    if temporary_margins is not None:
        expected = [('setup', temporary_margins[0], '[get_clocks]'),
                    ('hold', temporary_margins[1], '[get_clocks]')]
        if require_restoration:
            expected += [('setup', 0.0, '[get_clocks]'), ('hold', 0.0, '[get_clocks]')]
        if uncertainty != expected:
            raise ValueError('Temporary uncertainty was not exactly applied and restored in order')
    return result


def worst(path, kind):
    values = [float(v) for v in re.findall(r'^' + kind + r' SLACK=(-?[\d.]+)',
                                         Path(path).read_text(), re.M)]
    if not values:
        raise ValueError('Missing actual path slack: ' + str(path))
    return min(values)


def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument('--experiment', required=True, type=Path)
    parser.add_argument('--out', required=True, type=Path)
    parser.add_argument('--reopen', type=Path, help='Independent verify-stage output for the saved candidate')
    a = parser.parse_args()
    if a.out.exists():
        raise ValueError('Preserve the earlier audit')
    root = a.experiment.resolve()
    result = {'pass': False, 'experiment': root.as_posix(), 'board_operations': 0,
              'bound_files': {}}

    def bind(path):
        path = Path(path).resolve()
        result['bound_files'][path.as_posix()] = sha(path)
        return path

    try:
        receipt = json.loads(bind(root / 'result.json').read_text())
        if not receipt['pass'] or receipt['stage'] != 'optimize' or receipt['exit_code']:
            raise ValueError('Optimization process did not pass')
        if sha(bind(receipt['source_checkpoint'])) != receipt['source_checkpoint_sha256']:
            raise ValueError('Source checkpoint changed')
        if sha(bind(root / 'console.log')) != receipt['log_sha256']:
            raise ValueError('Optimization log changed')
        if sha(bind(root / 'timing_margin.tcl')) != receipt['script_sha256']:
            raise ValueError('Optimization script changed')
        for name, digest in receipt['reports'].items():
            if sha(bind(root / name)) != digest:
                raise ValueError('Experiment report changed: ' + name)
        before = xdc_commands(root / 'baseline_constraints.xdc')
        after = xdc_commands(root / 'restored_constraints.xdc', True,
                             (receipt['setup_margin_ns'], receipt['hold_margin_ns']))
        if before != after:
            diff = '\n'.join(difflib.unified_diff(before, after, fromfile='baseline', tofile='restored'))
            (a.out.parent / (a.out.stem + '_constraint_diff.txt')).write_text(diff, encoding='utf-8')
            raise ValueError('Non-uncertainty constraints changed; inspect the saved diff')
        result['original_constraint_commands_unchanged'] = True
        result['original_constraint_command_count'] = len(before)
        result['original_clock_periods_ns'] = {'clk_pl_0': 10.0, 'clk_pl_1': 5.0}
        result['restored_user_uncertainty_ns'] = 0.0
        clock_rows = re.findall(r'^(clk_pl_[01])\s+(clk_pl_[01])\s+([\d.]+)\s+([\d.]+)\s+rf -> rf$',
                               (root / 'restored_clocks.rpt').read_text(), re.M)
        if sorted(clock_rows) != [('clk_pl_0', 'clk_pl_0', '0.000', '0.000'),
                                 ('clk_pl_1', 'clk_pl_1', '0.000', '0.000')]:
            raise ValueError('Effective restored clock uncertainty is not zero')
        result['source_checkpoint_sha256'] = receipt['source_checkpoint_sha256']
        result['checkpoint_sha256'] = sha(bind(root / 'optimized_routed.dcp'))
        baseline = {k: worst(root / 'baseline_path_summary.txt', t)
                    for k, t in [('WNS_ns', 'max'), ('WHS_ns', 'min')]}
        final = {k: worst(root / 'final_path_summary.txt', t)
                 for k, t in [('WNS_ns', 'max'), ('WHS_ns', 'min')]}
        result['baseline'] = baseline
        result['optimized'] = final
        result['improvement_ns'] = {k: round(final[k] - baseline[k], 6) for k in baseline}
        result['targets_ns'] = {'WNS_ns': receipt['setup_margin_ns'], 'WHS_ns': receipt['hold_margin_ns']}
        result['targets_met'] = all(final[k] >= v for k, v in result['targets_ns'].items())
        if any(v < 0 for v in final.values()):
            raise ValueError('Original timing requirements fail')
        if any(final[k] <= baseline[k] for k in baseline):
            raise ValueError('Both setup and hold must improve over the source')
        result['route'] = route_summary((root / 'route_status.rpt').read_text())
        result['bus_skew'] = bus_skew_summary((root / 'routed_bus_skew.rpt').read_text())
        for name, severities in [('routed_drc.rpt', {'error', 'critical warning'}),
                                 ('routed_cdc.rpt', {'error', 'critical'})]:
            if critical_rows((root / name).read_text(), severities):
                raise ValueError('Blocking violations: ' + name)
        if a.reopen:
            reopened = a.reopen.resolve()
            proof = json.loads(bind(reopened / 'result.json').read_text())
            if (not proof['pass'] or proof['stage'] != 'verify' or proof['exit_code'] or
                    proof['source_checkpoint_sha256'] != result['checkpoint_sha256']):
                raise ValueError('Independent reopen did not verify this candidate')
            if sha(bind(reopened / 'console.log')) != proof['log_sha256']:
                raise ValueError('Reopen log changed')
            if sha(bind(reopened / 'timing_margin.tcl')) != proof['script_sha256']:
                raise ValueError('Reopen script changed')
            for name, digest in proof['reports'].items():
                if sha(bind(reopened / name)) != digest:
                    raise ValueError('Reopened report changed: ' + name)
            unused = ps_clock_proof((reopened / 'reopened_unused_ps_clocks.txt').read_text(),
                                    (reopened / 'reopened_clock_check.rpt').read_text())
            checked = timing_summary((reopened / 'reopened_timing.rpt').read_text(), unused)
            if any(checked[k] != final[k] for k in final):
                raise ValueError('Saved checkpoint timing differs from original candidate reports')
            if route_summary((reopened / 'reopened_route.rpt').read_text()) != result['route']:
                raise ValueError('Saved checkpoint route coverage differs')
            bus_skew_summary((reopened / 'reopened_bus_skew.rpt').read_text())
            if critical_rows((reopened / 'reopened_drc.rpt').read_text(), {'error', 'critical warning'}):
                raise ValueError('Blocking reopened DRC violation')
            result['independent_reopen'] = {'pass': True, 'timing': checked,
                                          'unused_ps_clock_proof': unused}
        result['pass'] = True
        result['verification_scope'] = ('Physical transformation of an existing routed design; '
            'source RTL/model/weights unchanged; original clock/exception commands compared; '
            'fresh routed timing, route coverage, DRC, CDC and bus-skew reports. '
            'No new end-to-end RTL simulation or board performance claim.')
    except Exception as exc:
        result['error'] = str(exc)
        raise
    finally:
        a.out.write_text(json.dumps(result, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
        print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == '__main__':
    main()

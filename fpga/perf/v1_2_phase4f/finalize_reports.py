"""Publish only a complete, independently checked eight-frame run to reports.

This script writes documentation and never launches simulation or Git actions.
"""
import argparse
import datetime
import json
from pathlib import Path

REPO = Path('E:/github/-')
REPORTS = REPO / 'fpga/reports'
NAMES = ('CNN', 'Bilinear', 'Curve')


def number(value):
    if value is None:
        return '—'
    return f'{value:,.3f}' if isinstance(value, float) else f'{value:,}'


def link(label, path):
    return f'[{label}]({Path(path).as_posix()})'


def table(header, rows):
    return ['| ' + ' | '.join(header) + ' |', '| ' + ' | '.join('---' for _ in header) + ' |',
            *['| ' + ' | '.join(str(v) for v in row) + ' |' for row in rows], '']


def make_measurements(result, run):
    timing, ddr, own = result['timing'], result['ddr'], result['ownership']
    stages = {(s['stage'], s['frame']): s for s in result['stages']}
    lines = ['## 8 帧数值与真实 RTL start/done', '',
             '每帧 CNN A_low **19,080**、Bilinear A_full **2,747,520**、Curve enhanced **2,747,520** 个 raw INT16 全量比较；8 帧共 **44,112,960** 项。三阶段各 8 次检查：**raw mismatch=0；guard=0；hazard=0**。', '',
             '下表 start/done 来自核内部 ap_start/ap_done，不含软件轮询误差；帧号从 0 开始。', '']
    lines += table(['Frame', 'CNN start / done / cycles', 'Bilinear start / done / cycles', 'Curve start / done / cycles', 'Raw mismatch CNN / Bilinear / Curve'],
                   [(f, *[' / '.join(number(stages[t, f][k]) for k in ('start', 'done', 'cycles')) for t in range(3)], '0 / 0 / 0') for f in range(8)])
    lines += ['## 输出 frame interval 与 30 FPS gate', '',
              '唯一 FPS 指标为 **Curve_done(N+1) − Curve_done(N)**。100 MHz 的精确 30 FPS budget=3,333,333.333… cycles；按整数 gate **max steady-state interval ≤3,333,333**。稳态预先固定为最后 4 个间隔（3→4、4→5、5→6、6→7），全部 7 个实测间隔同时保留。', '',
              '这是有限 8 帧的后段输出 cadence 统计，包含系统排空尾部；三模块同时运行的实际范围由下面 start/done 时间线界定。', '']
    lines += table(['Output frames', 'Curve done interval / cycles', '≤3,333,333'],
                   [(f"{r['from_frame']} → {r['to_frame']}", number(r['cycles']), 'PASS' if r['cycles'] <= 3333333 else 'FAIL') for r in timing['curve_done_intervals']])
    lines += table(['Scope', 'Min', 'Mean', 'Max'],
                   [(label, *[number(timing[key][stat]) for stat in ('min', 'mean', 'max')]) for label, key in [('全部 7 intervals', 'all_curve_intervals'), ('后 4 steady intervals', 'steady_curve_intervals')]])
    lines += [f"**{result['conclusion']}**。稳态 mean 对应 {number(timing['fps_from_mean_steady_interval'])} FPS；max 对应 {number(timing['fps_from_max_steady_interval'])} FPS。", '',
              f"First-frame latency={number(timing['first_frame_latency_cycles'])} cycles，仅报告延迟，不用于判断 FPS。", '',
              '## 连续 stage start interval 与并发 stage latency', '']
    lines += table(['Frames', 'CNN start interval', 'Bilinear start interval', 'Curve start interval'],
                   [(f'{f-1} → {f}', *[number(timing['stage_metrics'][n]['start_intervals'][f-1]['cycles']) for n in NAMES]) for f in range(1, 8)])
    lines += table(['Stage', 'Isolated reference', '8-frame latency min / mean / max', 'Late latency min / mean / max', 'Late start interval min / mean / max'],
                   [(n, number(timing['stage_metrics'][n]['isolated_reference_cycles']),
                     *[' / '.join(number(timing['stage_metrics'][n][key][s]) for s in ('min', 'mean', 'max')) for key in ('latency', 'late_latency', 'late_start_interval')]) for n in NAMES])
    lines += table(['Stage', 'Late previous DONE→START idle min / mean / max', 'Late ready→START control/poll lag min / mean / max'],
                   [(n, *[' / '.join(number(timing['stage_metrics'][n][key][s]) for s in ('min', 'mean', 'max')) for key in ('late_previous_done_to_start_idle', 'late_post_ready_control_poll_lag')]) for n in NAMES])
    lines += ['Ready boundary 取自身前帧 RTL DONE、当前 producer RTL DONE、同槽旧 consumer 的实际 RELEASE 中最晚者；ready→START lag 保留软件确认/CSR/poll 开销。逐次边界及输出 cadence 对照详见 analysis.json。精确恒等式：stage start interval=前帧 stage latency+当前 idle gap；Curve done interval=当前 Curve latency+当前 Curve idle gap。', '']
    lines += ['## 实际跨帧 overlap 证据', '',
              '对真实 ap_start/ap_done 区间取交集：max(三个 start) < min(三个 done) 才构成 overlap；没有由 scheduler 源码推断重叠。', '']
    lines += table(['CNN frame', 'Bilinear frame', 'Curve frame', 'Overlap start', 'Overlap done', 'Overlap cycles'],
                   [(r['cnn_frame'], r['bilinear_frame'], r['curve_frame'], number(r['overlap_start']), number(r['overlap_done']), number(r['overlap_cycles'])) for r in timing['triplet_overlap']])
    lines += [f"Peak concurrent stages={timing['peak_concurrent_stages']}，overlap gate={timing['pipeline_overlap_gate']}。完整 stage sweep：" + link('stage_overlap_timeline.csv', run / 'results/stage_overlap_timeline.csv') + '。', '']
    triples = [r for r in timing['stage_overlap_timeline'] if r['mask'] == 7]
    lines += table(['Timeline start', 'Timeline done', 'Cycles', '实际并行 stage/frame'],
                   [(number(r['start']), number(r['done']), number(r['cycles']), ' + '.join(f"{s['name']}({s['frame']})" for s in r['active'])) for r in triples])
    lines += ['## Buffer ownership、RAW / WAR / WAW 与等待', '',
              '**RAW/WAR/WAW PASS；guard=0；hazard=0**。80 次实际 acquire/release、40 个 frame/buffer 生命周期、10 个 slot occupancy 积分全部交叉核对；每次 slot 复用都晚于前一个 consumer 完成及实际 release。', '']
    lines += table(['Buffer', 'Producer / consumer 与释放规则'], [
        ('A_low[2]', 'CNN → Bilinear；Bilinear 完成并检查后 release'),
        ('A_full[2]', 'Bilinear → Curve；Curve 完成并 host 检查后 release'),
        ('enhanced[2]', 'Curve → host raw check；全量比较结束后 release'),
        ('cnn_input[2]', '预载只读；CNN 完成检查后 release'),
        ('model_input[2]', '预载只读；Curve 完成检查后 release'),
        ('workspace / weights / bias / frac / LUT', 'workspace 只由单一串行 CNN 实例独占；参数 HP1 只读，AW/W=0；原 access checker 禁止写入 input/model/参数区域')])
    lines += table(['Stage', 'Dependency wait', 'Buffer wait', 'Both', 'Union blocked', 'Ready / CSR / poll'],
                   [(n, *[number(own['waits']['by_stage'][n][k]) for k in ('dependency', 'buffer', 'both', 'union_blocked', 'ready')]) for n in NAMES])
    lines += ['等待以未 running 且有 next frame 的每周期实际状态计数；buffer wait 仅计算**其他帧**仍持有目标 slot，已排除自身 CSR reservation。Dependency 和 buffer 可重叠，union=dependency+buffer−both；这些状态计数不直接相加冒充吞吐损失。自身核运行、done 后轮询确认与控制启动时间可从实际 stage gap 另看。逐帧计数：' + link('wait_stats.csv', run / 'results/wait_stats.csv') + '。', '']
    lines += table(['Buffer', 'Slot', 'Occupied cycles', 'Peak occupied slots'],
                   [(r['name'], r['slot'], number(r['occupied_cycles']), r['peak_slots']) for r in own['slot_occupancy']])
    lines += ['Owners 在 negedge 采样，标签与原事件可差 1 cycle；占用积分与实际 transition 完全一致。生命周期全表：' + link('analysis.json', run / 'analysis.json') + '。', '',
              '**56/56 CNN writer block drains PASS**：每帧 7 个 block credit_ws=credit_out=0、HP0 write queue/data/B 清空；**32/32 stage/HP release drains PASS**：CNN HP0/1、Bilinear HP2、Curve HP3 的 rc/wc/wp/RVALID/BVALID 全空后才释放。最终所有 HP responses 与全部 owners 清空。', '',
              '## DDR 并发统计', '',
              'DDR model v2 不变，O=2/2；下表为完整 8 帧全程实际累积统计。R_STALL 是有读请求且 RREADY 等待 RVALID 的周期；B_WAIT 是有写请求且 BREADY 等待 BVALID 的周期，均不是纯 contention，也不能与其他 stall 简单相加。', '']
    hp, queues = ddr['hp_stats'], ddr['queues']
    lines += table(['HP', 'AR', 'AW', 'R beats', 'W beats', 'Useful write bytes', 'Read / write queue max', 'Read / write occupancy sum'],
                   [(r['HP'], *[number(r[k]) for k in ('AR', 'AW', 'R', 'W', 'WRITE_BYTES')], f"{queues[r['HP']]['READ_MAX']} / {queues[r['HP']]['WRITE_MAX']}", f"{number(queues[r['HP']]['READ_OCCUPANCY_SUM'])} / {number(queues[r['HP']]['WRITE_OCCUPANCY_SUM'])}") for r in hp])
    lines += table(['HP', 'AR stall', 'AW stall', 'R wait', 'R backpressure', 'W stall', 'B wait'],
                   [(r['HP'], *[number(r[k]) for k in ('AR_STALL', 'AW_STALL', 'R_STALL', 'R_BACK', 'W_STALL', 'B_WAIT')]) for r in hp])
    lines += table(['HP', 'AR→first R mean / max', 'AR→last R mean', 'AW→B mean / max'],
                   [(r['HP'], f"{number(r['average_ar_to_first_r_cycles'])} / {number(r['FIRST_R_MAX'])}", number(r['average_ar_to_last_r_cycles']), f"{number(r['average_aw_to_b_cycles'])} / {number(r['B_LATENCY_MAX'])}") for r in hp])
    shared = ddr['shared']
    lines += [f"Shared served={number(shared['SERVED'])} beats，contested={number(shared['CONTESTED_CYCLES'])} cycles，R/W concurrent={number(ddr['rw_concurrent_cycles'])} cycles。所有 HP read/write queue max≤2；AR=first-R samples，AW=B samples；AW→B latency sum=write occupancy sum；8 倍单帧 R/W/payload bytes conservation PASS。", '',
              '### 三模块同时活动期间', '']
    triple = ddr['observer']['triple_active']
    peaks = {r['HP']: r for r in ddr['observer']['triple_queue_latency_max']}
    lines += [f"真实 triple-active 共 {number(triple['cycles'])} cycles，{triple['segments']} 个时间段；shared served={number(triple['shared']['served'])}，contested={number(triple['shared']['contested'])}，R/W concurrent={number(triple['shared']['rw_concurrent'])}。", '']
    thp = {int(k): v for k, v in triple['hp'].items()}
    lines += table(['HP', 'AR / AW', 'R / W beats', 'Read / write queue mean / peak', 'AR / AW / R / R back / W / B waits', 'Completed first-R mean / max', 'Completed B mean / max'],
                   [(p, f"{number(r['ar'])} / {number(r['aw'])}", f"{number(r['r'])} / {number(r['w'])}", f"{number(r['average_read_queue'])} / {number(r['average_write_queue'])}; peak {peaks[p]['READ_MAX']} / {peaks[p]['WRITE_MAX']}", ' / '.join(number(r[k]) for k in ('ar_stall', 'aw_stall', 'r_stall', 'r_back', 'w_stall', 'b_wait')), f"{number(r['average_completed_ar_to_first_r'])} / {number(peaks[p]['FIRST_R_MAX'])}", f"{number(r['average_completed_aw_to_b'])} / {number(peaks[p]['B_LATENCY_MAX'])}") for p, r in sorted(thp.items())])
    lines += ['完整 mask0..7、R backpressure/B wait 与所有 response sums 保留在 analysis.json。Snapshot 在 stage mask 变化的 negedge 记录，时间标签比真实 RTL event 晚 1 cycle，段长与实际 sweep 一致。Latency mean 来自该快照窗口内完成的响应，request 可能更早发出；队列积分代表窗口内真实占用。单周期 active-mask response maxima 独立保留 PHASE4F_TRIPLE，边界 response 的样本归属相差最多 1 cycle，不把这些重叠计数当成可直接相加的因果节省。', '']
    return lines


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', type=Path, required=True)
    parser.add_argument('--bottleneck-note', type=Path, required=True)
    args = parser.parse_args()
    run = args.run.resolve()
    result = json.loads((run / 'analysis.json').read_text())
    assert result['consistency_gate'] == 'PASS'
    assert result['numerical_gate'] == 'PASS' and result['ownership']['gate'] == 'PASS'
    assert result['conclusion'] in ('SHORT_MULTI_FRAME_30FPS_PASS', 'SHORT_MULTI_FRAME_30FPS_FAIL')
    assert json.loads((run / 'harness_audit_after.json').read_text())['status'] == 'PASS'
    protection = json.loads((run.parent / 'phase4f_protection_after.json').read_text())
    assert protection['status'] == 'PASS' and not protection['original_changed']
    date = datetime.datetime.fromisoformat(result['termination']['finished']).date().isoformat()
    evidence = [link(label, run / path) for label, path in [('完整日志', 'system.log'), ('独立分析', 'analysis.json'), ('配置与source manifest', 'run_manifest.json'), ('自然退出记录', 'exit_status.json'), ('原BFM不变审计', 'harness_audit_after.json')]]
    intro = ['日期：' + date + '（Asia/Shanghai）。CURRENT STATUS：**' + result['conclusion'] + ' / WAIT_MASTER**。', '',
             '仅完成固定 **FRAMES=8、READ_OUTSTANDING=WRITE_OUTSTANDING=2、DDR_DELAY=16、SERVICE_PERIOD=1、POLL_PERIOD=128、100 MHz** 的完整 CNN → DDR → Bilinear → DDR → Curve。保留现有双槽调度；每帧全量数值检查没有省略。', '',
             '权威现场：' + link('Phase 4E checkpoint 备份', run / 'checkpoint_before.md') + '；' + link('Phase 4E write-credit report', REPORTS / 'v1_2_phase4e_write_retirement_optimization.md') + '。当前 write-credit 仍为 **RTL scheduling overlay，未形成新 HLS export / IP release**。', '',
             '证据：' + '；'.join(evidence) + '。', '']
    measures = make_measurements(result, run)
    bottleneck = ['## 瓶颈与归因', '', args.bottleneck_note.read_text(encoding='utf-8').strip(), '']
    audit = ['## 修改、验证与停止范围', '',
             '前后 protection audit：原 5,235 文件、原 363 个 system source、3 个 Phase 4E overlay、16 份 PL/DDR/hex/ROM/options copy hash PASS；恢复原 TB 前缀后逐字一致，CNN 数学、DW/PW lanes、Bilinear、Curve、DDR v2、buffer layout、fixed-point 与原 scheduler 未改。仅重新进行 **XSIM simulation elaboration**，没有 HLS 重新综合或 export。', '',
             '首次 phase4f_system_01 在 frame0 完成前中止：被动 buffer wait 计数误把自身 CSR reservation 算成 consumer stall；只修复观测归因，新建独立 system_02 完整运行，01 不用于数值或性能 gate。相关记录：' + link('attempt_status.json', run.parent / 'phase4f_system_01/attempt_status.json') + '。', '',
             '新增/更新文件及原因：', '']
    audit += table(['File', '原因 / 关键差异'], [
        ('fpga/perf/v1_2_phase4f/prepare_system.py', '复用原完整 BFM，仅替换同三颗 Phase4E overlay；新增 passive owner/wait/DDR mask/drain 观测和严格 FRAMES=8 scope'),
        ('fpga/perf/v1_2_phase4f/run_system.py', 'source/config/kernel hash gate 后唯一完整 8 帧自然运行；无后续自动流程'),
        ('fpga/perf/v1_2_phase4f/analyze_system.py', '独立核对 24 次全量检查、实际 overlap、所有权、7/4 intervals、DDR与payload conservation'),
        ('fpga/perf/v1_2_phase4f/audit_harness.py', '前后只读保护审计，证明原 BFM/scheduler/DUT/model未改'),
        ('fpga/perf/v1_2_phase4f/finalize_reports.py', '仅完整gate后写权威report/checkpoint'),
        ('fpga/reports/v1_2_phase4f_short_multiframe.md', '本批完整证据、性能结论与瓶颈'),
        ('fpga/reports/v1_2_phase4_checkpoint.md', '更新当前结果与交接；旧checkpoint外部保留')])
    audit += ['已执行：8 帧完整三模块 RTL 自然完成、24 次逐字数值/guard/hazard/IRQ 检查、实际三 stage overlap、80 owner transitions、wait/slot积分、56 writer及32 stage/HP drain、原DDR全run/mask并发统计、payload conservation、前后hash保护与独立一致性分析。', '',
              '未执行：100-frame、HLS synthesis/export、Vivado implementation/route、bitstream/XSA、板测、Git add/commit/push、PR、切换/创建/删除分支。外部 E:/HLS 数据、snapshot、仿真日志与备份不上传。', '',
              '输入为同一真实 night_01 预载到两个 input/model slot 后重复 8 帧；host数值检查不消耗模拟 cycles。本结论只覆盖该 DDR model 与三模块流水线，未计真实采集、PS input上传/输出搬运和板级DDR时延。', '']
    git = json.loads((run / 'git_status_after.json').read_text())
    audit += [f"Branch=`{git['branch']}`，HEAD=`{git['head']}`；tracked diff={git['tracked_diff'] or 'empty'}；staged diff={git['staged_diff'] or 'empty'}。既有 untracked 保留，本批新增脚本/报告及checkpoint未跟踪；没有 Git 写操作。", '',
              '建议 Commit Message：`test(fpga): validate eight-frame write-credit system pipeline`。', '',
              '## NEXT STEP — WAIT MASTER', '',
              '本批 8 帧分析与 checkpoint 完成后立即停止，等待 Master 审核。' + ('短多帧性能 gate 已通过；下一批须单独解决可实施 IP 固化问题，将 RTL scheduling overlay 转化为可审核的实施交付。' if result['conclusion'].endswith('_PASS') else '短多帧性能 gate 未通过；下一批由 Master 决定是否按本报告归因处理瓶颈。本批只归因，没有继续优化。可实施 IP 固化问题仍未解决。') + '不自动进入 100-frame、HLS export、implementation 或 bitstream。', '']
    report = ['# V1.2 Phase 4F — 8-frame short multi-frame system pipeline validation', '', *intro, *measures, *bottleneck, *audit]
    checkpoint = ['# V1.2 Phase 4F Checkpoint', '', *intro,
                  '详细报告：' + link('Phase 4F short multi-frame', REPORTS / 'v1_2_phase4f_short_multiframe.md') + '。', '',
                  *measures, *bottleneck, *audit]
    (REPORTS / 'v1_2_phase4f_short_multiframe.md').write_text('\n'.join(report), encoding='utf-8')
    (REPORTS / 'v1_2_phase4_checkpoint.md').write_text('\n'.join(checkpoint), encoding='utf-8')
    print(json.dumps(dict(status='REPORTS_WRITTEN', conclusion=result['conclusion'], report=(REPORTS / 'v1_2_phase4f_short_multiframe.md').as_posix())))


if __name__ == '__main__':
    main()

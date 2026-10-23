"""Replay an immutable board mismatch fixture against exported RTL or its netlist.

Run through run_windows_desktop.py. Never loads or resets physical hardware.
"""
import argparse
import ast
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import struct
import subprocess
from diagnostic_boundary import wrapper, verilog_name
from physical_system_repro import build_physical_path


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


p = argparse.ArgumentParser(description=__doc__)
p.add_argument('--fixture', type=Path, required=True)
p.add_argument('--rtl', type=Path, required=True)
p.add_argument('--netlist', type=Path)
p.add_argument('--physical-system', type=Path, help='full-system routed functional netlist; preserve original parent connectivity')
p.add_argument('--physical-kind', choices=('post_route_functional', 'post_opt_functional', 'diagnostic_modified_functional'), default='post_route_functional', help='identify the supplied full-system export honestly')
p.add_argument('--netlist-kind', choices=('post_synthesis_functional', 'post_route_functional'), default='post_synthesis_functional')
p.add_argument('--output', type=Path, required=True)
p.add_argument('--vivado', type=Path, required=True)
p.add_argument('--no-stalls', action='store_true')
p.add_argument('--continuous-reads', action='store_true', help='allow back-to-back read data beats instead of the original mandatory gap')
p.add_argument('--trace-stages', action='store_true', help='record each spatial-stage output packet before its FIFO')
p.add_argument('--task1-vectors', type=Path, help='append verified 8x8 task1 and return-to-task0 cases from an existing independent RTL run')
a = p.parse_args()
if a.netlist and a.netlist_kind == 'post_route_functional':
    p.error('Use --physical-system for routed replay, not a subcell export')
root = Path(__file__).resolve().parents[1]
out = a.output.resolve()
out.mkdir(parents=True, exist_ok=False)
fixture = a.fixture.resolve()
fixture_manifest = json.loads((fixture / 'manifest.json').read_text())
for name, entry in fixture_manifest.items():
    if sha(fixture / name) != entry['sha256'] or (fixture / name).stat().st_size != entry['bytes']:
        raise RuntimeError('Fixture identity failed: ' + name)
names = ('input_q14_nchw_8x8.bin', 'expected_q14_nchw_8x8.bin', 'weather_smoke_frame_0_q14.bin')
for dest, name in zip(('input', 'golden', 'board'), names):
    data = (fixture / name).read_bytes()
    if len(data) != 384:
        raise RuntimeError('Require precisely the supplied 8x8 fixture')
    for seq in (0, 1):
        (out / f'{dest}_{seq}.hex').write_text(''.join(f'{n:04x}\n' for n in struct.unpack('<192H', data)))

case_count = 4 if a.task1_vectors else 2
extra_identity = None
if a.task1_vectors:
    previous = json.loads((a.task1_vectors / 'run.json').read_text())
    if not previous.get('pass') or previous.get('verification_kind') != 'independent_axi_rtl':
        raise RuntimeError('Additional task1 vectors require a previously passed independent RTL run')
    for name, expected in previous['rtl_sha256'].items():
        if sha(a.rtl / name) != expected:
            raise RuntimeError('Additional vector RTL identity differs: ' + name)
    extra_identity = {'run_sha256': sha(a.task1_vectors / 'run.json')}
    for dest in ('input', 'golden'):
        source = a.task1_vectors / f'{dest}_1.hex'
        tokens = source.read_text().split()
        if len(tokens) != 192 or any(not re.fullmatch('[0-9a-fA-F]{4}', t) for t in tokens):
            raise RuntimeError('Require complete known-valued task1 8x8 vectors')
        shutil.copy2(source, out / f'{dest}_2.hex')
        shutil.copy2(out / f'{dest}_0.hex', out / f'{dest}_3.hex')
        extra_identity[source.name] = sha(source)
    # Task1 has no board capture. The TB comparison for case2 is disabled below.
    shutil.copy2(out / 'board_0.hex', out / 'board_2.hex')
    shutil.copy2(out / 'board_0.hex', out / 'board_3.hex')
top = (a.rtl / 'weather_frame_top.v').read_text()
parameters = dict(re.findall(r'^parameter\s+(\w+)\s*=\s*([^;]+);', top, re.M))


def integer_expression(expression):
    def visit(node):
        if isinstance(node, ast.Constant) and isinstance(node.value, int):
            return node.value
        if isinstance(node, ast.Name) and node.id in parameters:
            return integer_expression(parameters[node.id])
        if isinstance(node, ast.BinOp):
            left, right = visit(node.left), visit(node.right)
            if isinstance(node.op, ast.Add): return left + right
            if isinstance(node.op, ast.Sub): return left - right
            if isinstance(node.op, ast.Mult): return left * right
            if isinstance(node.op, ast.Div) and right and left % right == 0:
                return left // right
        raise RuntimeError('Unsupported Verilog width expression: ' + expression)
    return visit(ast.parse(expression.strip(), mode='eval').body)


ports = []
interface = {}
for direction, width, name in re.findall(r'^(input|output)\s+(\[[^\]]+\])?\s*(\w+)\s*;', top, re.M):
    if width:
        msb, lsb = width.strip('[]').split(':')
        bits = integer_expression(msb) - integer_expression(lsb) + 1
        if integer_expression(lsb) != 0 or bits < 1:
            raise RuntimeError('Unsupported port range: ' + name)
        width = f'[{bits - 1}:0]' if bits > 1 else ''
    ports.append((name, 'logic ' + width + ' ' + name + ';'))
    interface[name] = (direction, width)
if len(ports) != 110:
    raise RuntimeError('Unexpected top port set')
tb = (root / 'system/rtl_memory_test.sv').read_text()
declarations = '\n'.join(v for _, v in ports)
physical_report = None
if a.physical_system:
    if a.netlist:
        raise RuntimeError('Physical parent replay is a separate mode')
    a.netlist = out / 'core_netlist.v'
    a.netlist_kind = a.physical_kind
    physical_report = build_physical_path(a.physical_system, a.netlist, interface)
    declarations = '\n'.join('logic ' + width + ' ' + name + ';' for name, (_, width) in interface.items())
tb = tb.replace('@PORTS@', declarations)
# A ready/valid X is not a handshake. This matters especially at optimized
# physical boundaries; Verilog while(!X) can otherwise silently advance.
for signal in ('s_axi_CTRL_AWREADY', 's_axi_CTRL_WREADY', 's_axi_CTRL_BVALID',
               's_axi_CTRL_ARREADY', 's_axi_CTRL_RVALID'):
    tb = tb.replace('while(!' + signal + ')', "while(" + signal + "!==1'b1)")
tb = tb.replace('#600000000;', '#500000;')  # two fixed 8x8 frames, not 720p
connected = [(name, name) for name, _ in ports]
if a.netlist:
    netlist_top, netlist_ports = wrapper(a.netlist)
    connected = [(name, name) for name in netlist_ports if name in interface]
    if set(netlist_ports) != {name for name, _ in connected}:
        raise RuntimeError('Netlist wrapper adds unknown ports: ' + str(set(netlist_ports) - {name for name, _ in connected}))
tb = tb.replace('@CONNECTIONS@', ',\n'.join('.' + verilog_name(k) + '(' + signal + ')' for k, signal in connected))
tb = tb.replace('IN_BASE=64\'h10000000, OUT_BASE=64\'h20000000',
                'IN_BASE=64\'d44589120, OUT_BASE=64\'d42479680')
tb = tb.replace('integer i,start_cycle,rb,wb;', 'integer i,start_cycle,rb,wb,fd,bad,board_bad;')
tb = tb.replace('golden[0:DEPTH-1];', 'golden[0:DEPTH-1], board[0:DEPTH-1];')
tb = tb.replace('        csr_write(\'h18,IN_BASE[31:0]);',
                '        file_name=$sformatf("board_%0d.hex",index);$readmemh(file_name,board,0,active_n-1);\n'
                '        csr_write(\'h18,IN_BASE[31:0]);')
start = tb.index('        for(i=0;i<active_n;i=i+1)\n')
end = tb.index('        for(i=active_n;', start)
tb = tb[:start] + '''        file_name=$sformatf("actual_%0d.hex",index);fd=$fopen(file_name,"w");
        bad=0;board_bad=0;
        for(i=0;i<active_n;i=i+1)begin
            $fdisplay(fd,"%04h",output_mem[i]);
            if(output_mem[i]!==golden[i])bad=bad+1;
            if(output_mem[i]!==board[i])board_bad=board_bad+1;
        end
        $fclose(fd);
        $display("BOARD_REPRO case=%0d golden_mismatch=%0d board_mismatch=%0d",index,bad,board_bad);
''' + tb[end:]
start = tb.index('    frame(0,0,8,8);')
end = tb.index('\nend\ninitial begin', start)
tb = tb[:start] + '''    frame(0,0,8,8);frame(1,0,8,8);
    $display("BOARD_REPRO_COMPLETED frames=2");$finish;''' + tb[end:]
if a.task1_vectors:
    tb = tb.replace('frame(0,0,8,8);frame(1,0,8,8);',
                    'frame(0,0,8,8);frame(1,0,8,8);frame(2,1,8,8);frame(3,0,8,8);')
    tb = tb.replace('BOARD_REPRO_COMPLETED frames=2', 'BOARD_REPRO_COMPLETED frames=4')
    tb = tb.replace('if(output_mem[i]!==board[i])', 'if(index!=2 && output_mem[i]!==board[i])')
    tb = tb.replace('$display("BOARD_REPRO case=%0d golden_mismatch=%0d board_mismatch=%0d",index,bad,board_bad);',
                    'if(index==2)$display("BOARD_REPRO case=%0d golden_mismatch=%0d board_capture=unavailable",index,bad);\n'
                    '        else $display("BOARD_REPRO case=%0d golden_mismatch=%0d board_mismatch=%0d",index,bad,board_bad);')
tb = tb.replace('WEATHER_RTL_FRAME_PASS', 'WEATHER_AXI_FRAME_COMPLETED')
if a.netlist:
    tb = tb.replace('weather_frame_top dut', netlist_top + ' dut')
    start = tb.index('always @(posedge ap_clk)if(ap_rst_n && dut.ap_done')
    end = tb.index('// Unused AXI inputs', start)
    tb = tb[:start] + tb[end:]
    tb = tb.replace('dut.ap_CS_fsm', "32'h0")
if a.physical_system:
    control_width = int(re.fullmatch(r'\[(\d+):0\]', interface['s_axi_CTRL_WDATA'][1])[1]) + 1
    if control_width != 128 or interface['s_axi_CTRL_RDATA'][1] != '[127:0]':
        raise RuntimeError('Control lane adapter currently requires actual 128-bit HPM')
    tb = tb.replace('s_axi_CTRL_AWADDR=addr;', "s_axi_CTRL_AWADDR=40'h00A0030000+addr;")
    tb = tb.replace('s_axi_CTRL_ARADDR=addr;', "s_axi_CTRL_ARADDR=40'h00A0030000+addr;")
    tb = tb.replace('s_axi_CTRL_WDATA=data;', "s_axi_CTRL_WDATA={96'b0,data}<<((addr&15)*8);s_axi_CTRL_WSTRB=16'h000f<<(addr&15);")
    tb = tb.replace('data=s_axi_CTRL_RDATA;', 'data=s_axi_CTRL_RDATA>>((addr&15)*8);')
    tb = tb.replace('rd_size<=m_axi_gmem_in_ARSIZE;rd_busy<=1;',
                    'rd_size<=m_axi_gmem_in_ARSIZE;rd_busy<=1;m_axi_gmem_in_RID<=m_axi_gmem_in_ARID;')
    tb = tb.replace('wr_size<=m_axi_gmem_out_AWSIZE;wr_busy<=1;',
                    'wr_size<=m_axi_gmem_out_AWSIZE;wr_busy<=1;m_axi_gmem_out_BID<=m_axi_gmem_out_AWID;')
    tb = tb.replace(',m_axi_gmem_in_RID=0', '').replace(',m_axi_gmem_out_BID=0', '')
    tb = tb.replace('    repeat(10)@(negedge ap_clk);\n    frame(',
                    '    repeat(300)@(negedge ap_clk);\n    frame(')
if a.no_stalls:
    tb = tb.replace('active_case>=7 || ', '1 || ')
    tb = tb.replace('b_delay<=active_case>=7 ? 0 : 5+cycle%13', 'b_delay<=0')
if a.trace_stages:
    if a.netlist:
        raise RuntimeError('Netlist stage buses may be optimized; refusing guessed reconstruction. Use exported RTL traces.')
    hierarchy = 'dut.' + ('inst.' if a.netlist else '') + 'grp_frame_fu_160.'
    trace = []
    for stage in range(6):
        packet = hierarchy + f'spatial_{stage}_U0_s{stage + 1}_din'
        trace.append(f'integer trace_fd{stage};\ninitial trace_fd{stage}=$fopen("stage_{stage}.txt","w");\n'
            f'always @(posedge ap_clk)if(ap_rst_n && {hierarchy}spatial_{stage}_U0_s{stage + 1}_write && '
            f'{hierarchy}s{stage + 1}_full_n) $fdisplay(trace_fd{stage},"%0d %044h",active_case,{packet});')
    tb = tb.replace('\nendmodule', '\n' + '\n'.join(trace) + '\nendmodule')
if a.continuous_reads:
    before = '''            if(rd_left==1)rd_busy<=0;'''
    after = '''            if(rd_left==1)rd_busy<=0;
            else begin
                ri=((((rd_addr>>rd_size)+1)<<rd_size)-IN_BASE)>>2;
                ri=ri*2;
                if(ri<0 || ri+1>=DEPTH || ri>=((active_n+1)/2)*2)
                    $fatal(1,"continuous input beat outside frame");
                m_axi_gmem_in_RDATA<={input_mem[ri+1],input_mem[ri]};
                m_axi_gmem_in_RLAST<=rd_left==2;
                m_axi_gmem_in_RVALID<=1;
            end'''
    if tb.count(before) != 1:
        raise RuntimeError('Read-model template changed')
    tb = tb.replace(before, after)
if a.physical_system:
    tb = tb.replace('m_axi_gmem_in_ARSIZE>2', 'm_axi_gmem_in_ARSIZE>4')
    tb = tb.replace('m_axi_gmem_out_AWSIZE>2', 'm_axi_gmem_out_AWSIZE>4')
    tb = tb.replace('ri=((rd_addr-IN_BASE)>>2)*2;', 'ri=((rd_addr-IN_BASE)>>4)*8;')
    tb = tb.replace('ri=((((rd_addr>>rd_size)+1)<<rd_size)-IN_BASE)>>2;\n                ri=ri*2;',
                    'ri=((((rd_addr>>rd_size)+1)<<rd_size)-IN_BASE)>>4;\n                ri=ri*8;')
    tb = tb.replace('ri+1>=DEPTH', 'ri+7>=DEPTH')
    tb = tb.replace('ri>=((active_n+1)/2)*2', 'ri>=((active_n+7)/8)*8')
    tb = tb.replace('{input_mem[ri+1],input_mem[ri]}',
                    '{input_mem[ri+7],input_mem[ri+6],input_mem[ri+5],input_mem[ri+4],input_mem[ri+3],input_mem[ri+2],input_mem[ri+1],input_mem[ri]}')
    tb = tb.replace('lane<4;', 'lane<16;')
    tb = tb.replace('((wr_addr-OUT_BASE)>>2)*4+lane', '((wr_addr-OUT_BASE)>>4)*16+lane')
    tb = tb.replace('reg [36:0] saved_w;', 'reg [144:0] saved_w;')
    tb = tb.replace('\nendmodule', '''
integer axi_fd;
initial axi_fd=$fopen("ddr_transactions.txt","w");
always @(posedge ap_clk)if(ap_rst_n)begin
    if(m_axi_gmem_in_ARVALID && m_axi_gmem_in_ARREADY)
        $fdisplay(axi_fd,"AR %0d %h %0d %0d",active_case,m_axi_gmem_in_ARADDR,m_axi_gmem_in_ARLEN,m_axi_gmem_in_ARSIZE);
    if(m_axi_gmem_in_RVALID && m_axi_gmem_in_RREADY)
        $fdisplay(axi_fd,"R %0d %032h %0d",active_case,m_axi_gmem_in_RDATA,m_axi_gmem_in_RLAST);
    if(m_axi_gmem_out_AWVALID && m_axi_gmem_out_AWREADY)
        $fdisplay(axi_fd,"AW %0d %h %0d %0d",active_case,m_axi_gmem_out_AWADDR,m_axi_gmem_out_AWLEN,m_axi_gmem_out_AWSIZE);
    if(m_axi_gmem_out_WVALID && m_axi_gmem_out_WREADY)
        $fdisplay(axi_fd,"W %0d %032h %h %0d",active_case,m_axi_gmem_out_WDATA,m_axi_gmem_out_WSTRB,m_axi_gmem_out_WLAST);
end
endmodule''')
(out / 'weather_rtl_test.sv').write_text(tb)
if a.netlist:
    if a.netlist.resolve() != (out / 'core_netlist.v').resolve():
        shutil.copy2(a.netlist, out / 'core_netlist.v')
    if not physical_report or not physical_report['includes_glbl']:
        shutil.copy2(a.vivado / 'data/verilog/src/glbl.v', out / 'glbl.v')
else:
    for f in a.rtl.iterdir():
        if f.is_file():
            shutil.copy2(f, out / f.name)
project = ''.join('verilog xil_defaultlib "' + f.name + '"\n' for f in sorted(out.glob('*.v')))
project += 'sv xil_defaultlib "weather_rtl_test.sv"\n'
(out / 'rtl.prj').write_text(project)
(out / 'run.tcl').write_text('run all\nquit\n')
tops = 'xil_defaultlib.weather_rtl_test' + (' xil_defaultlib.glbl' if a.netlist else '')
(out / 'simulate.cmd').write_text('@echo off\nsetlocal\nset "PROCESSOR_ARCHITECTURE=AMD64"\n'
    'call "' + str(a.vivado / 'settings64.bat') + '"\n'
    'call "' + str(a.vivado / 'bin/xelab.bat') + '" ' + tops
    + ' -prj rtl.prj -L unisims_ver -L unimacro_ver -L secureip -L xpm -relax -mt 2 -s weather_board_repro\n'
    'if errorlevel 1 exit /b 1\ncall "' + str(a.vivado / 'bin/xsim.bat')
    + '" weather_board_repro -tclbatch run.tcl\nexit /b %errorlevel%\n')
report = {'fixture_sha256': {name: sha(fixture / name) for name in names},
          'kind': a.netlist_kind if a.netlist else 'exported_rtl',
          'rtl_sha256': {f.name: sha(f) for f in a.rtl.iterdir() if f.suffix in ('.v', '.dat')},
          'netlist_sha256': sha(a.netlist) if a.netlist else None, 'stalls': not a.no_stalls}
report.update({'continuous_reads': a.continuous_reads,
               'additional_task1_vectors': extra_identity,
               'scope': 'core AXI ports with independent 32-bit memory; excludes actual SmartConnect and PS DDR',
               'testbench_sha256': sha(out / 'weather_rtl_test.sv'),
               'runner_sha256': sha(Path(__file__)),
               'template_sha256': sha(root / 'system/rtl_memory_test.sv')})
if a.physical_system:
    report['scope'] = a.physical_kind + ' weather/control/reset and HP0/HP3 parent wiring; PS hard block replaced by independent memory/control stimulus; other PL masters idle; no SDF'
    report['full_system_netlist_sha256'] = sha(a.physical_system)
    report['physical_boundary'] = physical_report
report['helper_sha256'] = {name: sha(root / 'tools' / name) for name in ('diagnostic_boundary.py', 'physical_system_repro.py')}
snapshots = out / 'executed_sources'
snapshots.mkdir()
for source in (Path(__file__), root / 'tools/diagnostic_boundary.py',
               root / 'tools/physical_system_repro.py', root / 'system/rtl_memory_test.sv'):
    shutil.copy2(source, snapshots / source.name)
report['executed_source_sha256'] = {path.name: sha(path) for path in snapshots.iterdir()}
print('BOARD_REPRO_START ' + str(out), flush=True)
with (out / 'simulation.log').open('wb') as log:
    result = subprocess.run([os.environ.get('COMSPEC', 'cmd.exe'), '/d', '/c', str(out / 'simulate.cmd')],
                            cwd=out, stdout=log, stderr=subprocess.STDOUT)
log = (out / 'simulation.log').read_text(errors='replace')
report['completed'] = result.returncode == 0 and f'BOARD_REPRO_COMPLETED frames={case_count}' in log and 'Fatal:' not in log
report['frames'] = []
for seq in range(case_count):
    actual = out / f'actual_{seq}.hex'
    if not actual.exists():
        continue
    tokens = actual.read_text().split()
    if len(tokens) != 192:
        report['frames'].append({'seq': seq, 'scalar_count': len(tokens), 'error': 'incomplete_frame'})
        continue
    if any(not re.fullmatch(r'[0-9a-fA-FxXzZ]{4}', token) for token in tokens):
        report['frames'].append({'seq': seq, 'error': 'invalid_scalar_encoding'})
        continue
    if any(re.search('[xz]', t, re.I) for t in tokens):
        report['frames'].append({'seq': seq, 'unknown_values': sum(bool(re.search('[xz]', t, re.I)) for t in tokens)})
        continue
    data = struct.pack('<' + str(len(tokens)) + 'H', *(int(t, 16) for t in tokens))
    (out / f'actual_{seq}.bin').write_bytes(data)
    x = struct.unpack('<192h', data)
    frame = {'seq': seq, 'sha256': hashlib.sha256(data).hexdigest()}
    expected = [int(token, 16) for token in (out / f'golden_{seq}.hex').read_text().split()]
    frame['golden_mismatch'] = sum((u & 65535) != v for u, v in zip(x, expected))
    frame['task'] = 1 if seq == 2 else 0
    if seq == 2:
        frame['board_comparison'] = 'no_task1_board_capture_available'
    else:
        expected_board = struct.unpack('<192h', (fixture / names[2]).read_bytes())
        frame['board_mismatch'] = sum(u != v for u, v in zip(x, expected_board))
    report['frames'].append(frame)
report['simulation_log_sha256'] = sha(out / 'simulation.log')
report['pass'] = report['completed'] and len(report['frames']) == case_count and all(
    frame.get('golden_mismatch') == 0 for frame in report['frames'])
(out / 'run.json').write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps({k: v for k, v in report.items() if k not in ('rtl_sha256', 'physical_boundary')}, indent=2), flush=True)
raise SystemExit(0 if report['pass'] else 1)

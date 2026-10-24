"""Replay actual full-system wiring, replacing only PS stimulus and idle cores.

Adapted from the reviewed legacy diagnostic method. Original netlist retained
verbatim; no synthesized primitive or SmartConnect datapath is rewritten.
"""
from pathlib import Path
import re


def build_path(source,target,interface,core='griddehaze_frame_top_0',selected=4,top_name='diagnostic_grid_path'):
    text=Path(source).read_text(encoding='utf-8')
    modules={m[1]:m[0] for m in re.finditer(r'\bmodule\s+(\w+)\b.*?\bendmodule',text,re.S)}
    parent=re.sub(r'\(\*.*?\*\)','',modules['system'],flags=re.S)
    lines=re.findall(r'^\s*wire\s+[^;]+;',parent,re.M)
    wires={}
    for line in lines:
        m=re.fullmatch(r'\s*wire\s+(\[\d+:\d+\])?\s*(\\\S+|\w+)\s*;',line)
        if not m:raise RuntimeError('unparsed parent wire '+line)
        wires[m[2]]=tuple(map(int,m[1].strip('[]').split(':'))) if m[1] else None
    def instance(name):
        m=re.search(r'^\s*(\w+)\s+'+re.escape(name)+r'\s*\((.*?)\);',parent,re.M|re.S)
        if not m:raise RuntimeError('physical instance absent '+name)
        return m[1],dict(re.findall(r'\.(\\\S+|\w+)\s*\(([^()]*)\)',m[2])),m[0]
    if core not in ['griddehaze_frame_top_0','weather_frame_top_0'] or selected not in [3,4]:raise ValueError('Unsupported replay selection')
    names=[core,'cnn_data_sc','curve_ddr_sc','rst_ps_100m','axi_control']
    # Before opt_design, the reset lock source is a real constant IP instance.
    # Routed exports can fold it into the reset module. Preserve the instance
    # when present; an undriven DCM_LOCKED would prevent all CSR transactions.
    if re.search(r'^\s*\w+\s+const_locked\s*\(',parent,re.M):
        constant_module,constant_ports,_=instance('const_locked')
        constant_body=re.sub(r'\(\*.*?\*\)','',modules[constant_module],flags=re.S)
        if re.search(r'^\s*input\b',constant_body,re.M):raise RuntimeError('Reset constant unexpectedly has inputs')
        names.append('const_locked')
    cells={n:instance(n) for n in names};ps_module,ps,_=instance('zynq_ultra_ps_e_0')
    def declarations(module):
        body=re.sub(r'\(\*.*?\*\)','',modules[module],flags=re.S)
        return {n:(d,w or '') for d,w,n in re.findall(r'^\s*(input|output)\s+(\[\d+:\d+\])?\s*(\w+)\s*;',body,re.M)}
    ps_ports=declarations(ps_module)
    def ps_field(name):
        if core=='weather_frame_top_0':
            if name.startswith('s_axi_CTRL_'):return 'maxigp0_'+name[len('s_axi_CTRL_'):].lower()
            if name.startswith('m_axi_gmem_'):
                bundle,field=name[len('m_axi_gmem_'):].split('_',1)
                return 'saxigp'+('2' if bundle=='in' else '5')+'_'+field.lower()
        if name.startswith('s_axi_control_'):return 'maxigp0_'+name[len('s_axi_control_'):].lower()
        for bundle,hp in [('feature_mem','5'),('parameter_mem','2')]:
            prefix='m_axi_'+bundle+'_'
            if name.startswith(prefix):return 'saxigp'+hp+'_'+name[len(prefix):].lower()
        return None
    for name,(direction,width) in list(interface.items()):
        field=ps_field(name)
        if field in ps:
            actual_direction,actual_width=ps_ports[field]
            if direction==actual_direction:raise RuntimeError('PS direction mismatch '+name)
            interface[name]=(direction,actual_width)
    clock=cells[core][1]['ap_clk']
    if any(cells[n][1]['aclk']!=clock for n in ['cnn_data_sc','curve_ddr_sc','axi_control']):raise RuntimeError('different interconnect clock')
    if any(ps[n]!=clock for n in ['maxihpm0_fpd_aclk','saxihp0_fpd_aclk','saxihp3_fpd_aclk']):raise RuntimeError('different PS clock')
    if re.search(r'^\s*assign\b',parent,re.M):raise RuntimeError('parent assignments need explicit replay')
    statements=[];adaptations=[]
    def bitname(n,i):return n+(' ' if n.startswith('\\') else '')+'['+str(i)+']'
    def bits(expression):
        e=expression.strip()
        if e.startswith('{') and e.endswith('}'):return [b for part in e[1:-1].split(',') for b in bits(part)]
        if re.fullmatch(r"1'b[01]",e):return [None]
        if e in wires:
            w=wires[e]
            return [e+(' ' if e.startswith('\\') else '')] if w is None else [bitname(e,i) for i in range(w[0],w[1]-1,-1)]
        m=re.fullmatch(r'(.+?)\[(\d+)(?::(\d+))?\]',e)
        if m and m[1] in wires:return [bitname(m[1],i) for i in range(int(m[2]),int(m[3] or m[2])-1,-1)]
        raise RuntimeError('unparsed expression '+e)
    def drive(expression,value,reason):
        destinations=bits(expression);signal='stimulus_'+str(len(adaptations))
        statements.extend([f'wire [{len(destinations)-1}:0] {signal};',f'assign {signal}={value};'])
        for i,destination in enumerate(reversed(destinations)):
            if destination is not None:statements.append(f'assign {destination}={signal}[{i}];')
        adaptations.append(dict(target=expression,value=value,reason=reason))
    drive(clock,'ap_clk','replace PS PL0 clock')
    drive(cells['rst_ps_100m'][1]['ext_reset_in'],'ap_rst_n','replace PS PL reset')
    used=set()
    for name,(direction,width) in interface.items():
        if name in ['ap_clk','ap_rst_n']:continue
        if name=='interrupt':statements.append("assign interrupt=1'b0;");continue
        field=ps_field(name)
        if field is None:raise RuntimeError('unknown boundary '+name)
        if field not in ps:
            if direction=='output':statements.append('assign '+name+'=0;')
            continue
        used.add(field)
        if direction=='input':drive(ps[field],name,'PS response or control replaced')
        else:statements.append('assign '+name+'='+ps[field]+';')
    for field in ['arlen','awlen','arid','awid','arburst','awburst','arsize','awsize','wlast']:
        n='maxigp0_'+field
        if n in used:raise RuntimeError('duplicate control field '+n)
        value='1' if field in ['arburst','awburst','wlast'] else '2' if field in ['arsize','awsize'] else '0'
        if n in ps:drive(ps[n],value,'single beat 32-bit PS control')
    for name in ['cnn_data_sc','curve_ddr_sc']:
        module,ports,_=cells[name]
        for port,(direction,width) in declarations(module).items():
            if direction=='input' and re.fullmatch(r'S0[0-4]_AXI_\w+',port) and not port.startswith(f'S0{selected}_'):
                drive(ports[port],'-1' if port.endswith(('rready','bready')) else '0','other PL masters idle')
    module,ports,_=cells['axi_control']
    for port,(direction,width) in declarations(module).items():
        if direction=='input' and re.fullmatch(r'M0[0-4]_AXI_\w+',port) and not port.startswith(f'M0{selected}_'):drive(ports[port],'0','unaddressed control targets idle')
    declarations_text='\n'.join(d+' '+w+' '+n+';' for n,(d,w) in interface.items())
    shim='module '+top_name+'('+','.join(interface)+');\n'+declarations_text+'\n'+'\n'.join(lines+statements+[cells[n][2] for n in names])+'\nendmodule\n'
    Path(target).write_text('`timescale 1ps/1ps\n'+shim+'\n'+text,encoding='utf-8')
    return dict(retained_instances=names,ps_boundary=interface,adaptations=adaptations,
                scope='actual parent wiring and SmartConnect; PS replaced, old cores idle, no SDF')

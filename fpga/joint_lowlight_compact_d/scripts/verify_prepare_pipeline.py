"""Bind full-frame prepare numeric/RTL and transport evidence to the new design."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import xml.etree.ElementTree as ET

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
    p=argparse.ArgumentParser(__doc__)
    p.add_argument('--build',required=True,type=Path)
    p.add_argument('--native',required=True,type=Path)
    p.add_argument('--cosim',required=True,type=Path)
    a=p.parse_args();out=a.build/'prepare_pipeline_acceptance.json'
    if out.exists():raise ValueError('Preserve previous validation')
    result={'pass':False,'board_operations':0,'whole_system_fps_verified':False,'bound_files':{}}
    def bind(f,expected=None):
        digest=sha(f)
        if expected is not None and digest!=expected:raise ValueError('Evidence changed: '+str(f))
        result['bound_files'][f.resolve().as_posix()]=digest
        return f.read_text(errors='replace')
    try:
        for folder,stage,frames in ((a.native,'native',3),(a.cosim,'cosim',1)):
            record=json.loads(bind(folder/'result.json'))
            if not record['pass'] or record['stage']!=stage:raise ValueError('Prepare test failed: '+stage)
            for relative,digest in record['source_sha256'].items():bind(folder/relative,digest)
            for name in ('joint_adapters.cpp','joint_adapters.hpp'):
                if sha(a.build/'source'/name)!=record['source_sha256'][name]:raise ValueError('Integrated source differs from '+stage)
                bind(a.build/'source'/name)
            for step in record['steps']:
                if step['exit_code']:raise ValueError('Nonzero test process')
                bind(folder/(step['name']+'.log'),step['log_sha256'])
            text=bind(folder/('native.log' if stage=='native' else 'cosim.log'))
            if f'PREPARE_ALL_PASS frames={frames} invalid=1' not in text:raise ValueError('Incomplete scalar comparison')
            if stage=='cosim':
                reuse=record.get('reused_synthesis')
                if reuse:
                    origin=Path(reuse['result']);bind(origin,reuse['result_sha256'])
                    synthesis_log=bind(origin.parent/'synth.log',reuse['log_sha256'])
                else:synthesis_log=bind(folder/'synth.log')
                for port,length,kind in (('gmem_rgb',171720,'reads'),('gmem_i',48,'writes'),('gmem_d',48,'writes'),('gmem_cnn',2385,'writes')):
                    pattern=f"burst {kind} of length {length} and bit width 128"
                    if not any(pattern in line and "bundle '"+port+"'" in line for line in synthesis_log.splitlines()):
                        raise ValueError('Required inferred burst absent: '+port)
                for relative,digest in record['reports'].items():bind(folder/relative,digest)
                reports=list((folder/'prepare/hls/sim/report').rglob('*cosim.rpt'))
                if len(reports)!=1 or not re.search(r'Verilog\s*\|\s*Pass',bind(reports[0])):raise ValueError('RTL result is not Pass')
                performance=ET.parse(folder/'prepare/hls/syn/report/joint_rgb8_prepare_csynth.xml').getroot()
                latency=int(performance.findtext('.//SummaryOfOverallLatency/Worst-caseLatency'))
                if latency>3333300:raise ValueError('Prepare synthesis budget exceeded')
                result['hls_estimated_cycles']=latency
                result['hls_estimated_ms_at_actual_clock']=latency*1000/99999001
                result['cosim_report']=reports[0].resolve().as_posix()
                ip=a.build/'prepare/hls/impl/ip'
                bind(ip/'component.xml',record['component_sha256'])
                for name,digest in record['ip_zips'].items():bind(ip/name,digest)
                for name in ('convert_tiles_Pipeline_pixels_in_group_csynth.xml','read_rgb_Pipeline_read_frame_csynth.xml','write_small_Pipeline_write_small_frame_csynth.xml'):
                    r=ET.parse(folder/'prepare/hls/syn/report'/name).getroot()
                    if r.findtext('.//SummaryOfLoopLatency/*/PipelineII')!='1':raise ValueError('II=1 missing: '+name)
        lines=bind(a.build/'reports/prepare_transport_audit.txt').splitlines()
        if len(lines)!=14 or any(not line.endswith(' DATA_WIDTH=128') for line in lines):raise ValueError('Prepare path narrowed')
        result.update(pass_=True,source_sha256=sha(a.build/'source/joint_adapters.cpp'),
                      native_compared_scalars=16542360,rtl_valid_frames=1,invalid_configurations=1,
                      simulation_only_prepare_budget_pass=True)
        result['pass']=True;result.pop('pass_')
    except Exception as e:result['error']=str(e);raise
    finally:
        out.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
        print(json.dumps(result,indent=2))
if __name__=='__main__':main()

"""Read-only input audit and evidence capture for authorized Phase 6."""
import sys
sys.dont_write_bytecode = True
import datetime, hashlib, json, shutil, subprocess
from pathlib import Path
import xml.etree.ElementTree as ET

REPO = Path('E:/github/-')
BASE = Path('E:/HLS/kv260_three_module_v1_2_phase4')
P5 = BASE / 'phase5/implementation_01'
OUT = Path(__file__).resolve().parent
PROJECT = BASE / 'phase4g/integration_01/project'
IMPL = PROJECT / 'v12_wc.runs/impl_1'
TZ = datetime.timezone(datetime.timedelta(hours=8))

def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda: f.read(1024*1024), b''): h.update(b)
    return h.hexdigest()
def save(name, value):
    (OUT/name).write_text(json.dumps(value, indent=2)+'\n', encoding='utf-8')
def stamp(): return datetime.datetime.now(TZ).isoformat()
def git(*args): return subprocess.check_output(['git', *args], cwd=REPO, text=True).strip()
def config():
    r=ET.parse(PROJECT/'v12_wc.xpr').getroot()
    return {tag: ET.tostring(r.find(tag), encoding='unicode') for tag in ('Configuration','FileSets')}
def tree(path):
    return {p.relative_to(path).as_posix():sha(p) for p in sorted(path.rglob('*')) if p.is_file()}

def prepare():
    if (OUT/'protection_before.json').exists(): raise RuntimeError('Do not overwrite evidence')
    (OUT/'reports').mkdir(exist_ok=True)
    gate=json.loads((P5/'implementation_gate.json').read_text())
    assert gate['status']=='POST_ROUTE_100MHZ_PASS' and not gate['failed_checks']
    assert gate['state']['POST_ROUTE_100MHZ']=='PASS' and gate['state']['BOARD_30FPS']=='NOT_TESTED'
    evidence_bad=[e['path'] for e in gate['evidence'] if sha(e['path'])!=e['sha256']]
    assert not evidence_bad, evidence_bad
    before=json.loads((P5/'protection_before.json').read_text())
    after=json.loads((P5/'protection_after.json').read_text())
    assert after['status']=='PASS' and not after['changed']
    records=dict(before['files'])
    for e in after['expected_generated_run_metadata_changes']: records[e['path']]=e['after_sha256']
    supplement=json.loads((P5/'supplement_protection_before.json').read_text())
    assert json.loads((P5/'supplement_protection.json').read_text())['status']=='PASS'
    for p,v in supplement['files'].items(): records[p]=v['sha256'] if isinstance(v,dict) else v
    bad=[p for p,h in records.items() if not Path(p).is_file() or sha(p)!=h]
    assert not bad, bad
    sys.path.insert(0,str(REPO/'fpga/perf/v1_2_phase4g'))
    from run_integration import verify_inputs
    verify_inputs(BASE/'phase4g/integration_01')
    assert config()==before['project_configuration']
    # Protect historical evidence and immutable route/synthesis outputs.
    for p in P5.rglob('*'):
        if p.is_file(): records[p.as_posix()]=sha(p)
    for e in gate['evidence']:
        p=Path(e['path'])
        if p.parent!=IMPL or p.suffix=='.dcp' or p.name.startswith(('.opt_', '.place_', '.phys_opt_', '.route_')):
            records[p.as_posix()]=sha(p)
    for p in IMPL.glob('*.dcp'): records[p.as_posix()]=sha(p)
    # Save original run logs/index bytes before permitted bookkeeping updates.
    backups={}
    for p in PROJECT.glob('v12_wc.runs/*/gen_run.xml'):
        dst=OUT/'run_indexes_before'/p.parent.name/'gen_run.xml'
        dst.parent.mkdir(parents=True,exist_ok=True); shutil.copyfile(p,dst)
        backups[p.as_posix()]=dst.as_posix()
    for name in ('runme.log','system_wrapper.tcl','gen_run.xml'):
        if (IMPL/name).exists(): shutil.copyfile(IMPL/name,OUT/('impl_before_'+name))
    shutil.copyfile(PROJECT/'v12_wc.xpr',OUT/'project_before.xpr')
    shutil.copyfile(REPO/'fpga/reports/v1_2_phase4_checkpoint.md',OUT/'checkpoint_before.md')
    for name in ('vivado_three_module_v1_2_implementation.md','v1_2_phase4g_implementable_cnn_ip.md','v1_2_phase4f_short_multiframe.md'):
        p=REPO/'fpga/reports'/name; records[p.as_posix()]=sha(p)
    input_trees={}
    for p in (BASE/'phase4g/ip_primary_05', BASE/'phase4g/integration_01/stable_ip_repo', PROJECT/'v12_wc.srcs', PROJECT/'v12_wc.gen'):
        input_trees[p.as_posix()]=tree(p)
    markers={p.name:{'sha256':sha(p),'mtime_ns':p.stat().st_mtime_ns} for p in IMPL.glob('.*.end.rst') if not p.name.startswith(('.vivado','.write_bitstream'))}
    save('protection_before.json',dict(status='PASS',checked_at=stamp(),files=records,count=len(records),
         input_trees=input_trees,project_configuration=config(),run_index_backups=backups,route_stage_markers=markers,
         routed_dcp_sha256=sha(IMPL/'system_wrapper_routed.dcp'),phase5_evidence_count=len(gate['evidence']),
         git={k:git(*a) for k,a in [('branch',('branch','--show-current')),('head',('rev-parse','HEAD')),('tracked_diff',('diff','--stat')),('staged_diff',('diff','--cached','--stat')),('status',('status','--short','--untracked-files=all'))]}))
    print('PHASE6_PREFLIGHT=PASS FILES='+str(len(records)),flush=True)

def after():
    before=json.loads((OUT/'protection_before.json').read_text())
    changed=[p for p,h in before['files'].items() if not Path(p).is_file() or sha(p)!=h]
    metadata=[]; unresolved=[]
    for p in changed:
        if p not in before['run_index_backups']: unresolved.append(p); continue
        old=ET.parse(before['run_index_backups'][p]).getroot(); new=ET.parse(p).getroot()
        # Synthesis indexes must be exactly semantically identical, ignoring whitespace only.
        def canonical(node): return (node.tag,sorted(node.attrib.items()),(node.text or '').strip(),tuple(canonical(c) for c in node))
        strict_same=canonical(old)==canonical(new)
        block_order_before=[c.attrib for c in old if c.tag=='BlockFileSet']
        block_order_after=[c.attrib for c in new if c.tag=='BlockFileSet']
        # BlockFileSet nodes are named references, not an ordered HDL compile list.
        # Accept only permutation of these exact references; every other node and
        # attribute remains in its original order and must be exactly equal.
        def named_reference_canonical(node):
            children=list(node)
            blocks=sorted((canonical(c) for c in children if c.tag=='BlockFileSet'),key=repr)
            others=tuple(canonical(c) for c in children if c.tag!='BlockFileSet')
            return node.tag,sorted(node.attrib.items()),(node.text or '').strip(),others,tuple(blocks)
        same=strict_same or named_reference_canonical(old)==named_reference_canonical(new)
        metadata.append(dict(path=p,before_sha256=before['files'][p],after_sha256=sha(p),xml_semantically_equal=same,strict_xml_order_equal=strict_same,only_named_BlockFileSet_reference_order_changed=not strict_same and same,block_order_before=block_order_before,block_order_after=block_order_after,original_bytes=before['run_index_backups'][p]))
        if not same: unresolved.append(p)
    tree_same={p:tree(Path(p))==v for p,v in before['input_trees'].items()}
    marker_same=all((IMPL/n).stat().st_mtime_ns==v['mtime_ns'] and sha(IMPL/n)==v['sha256'] for n,v in before['route_stage_markers'].items())
    git_same=all(git(*a)==before['git'][k] for k,a in [('branch',('branch','--show-current')),('head',('rev-parse','HEAD')),('tracked_diff',('diff','--stat')),('staged_diff',('diff','--cached','--stat'))])
    ok=not unresolved and all(tree_same.values()) and marker_same and git_same and config()==before['project_configuration']
    result=dict(status='PASS' if ok else 'FAIL',checked_at=stamp(),count=len(before['files']),raw_changed=changed,unresolved_changes=unresolved,
      generated_synthesis_index_audit=metadata,input_trees_unchanged=tree_same,route_stage_markers_unchanged=marker_same,
      routed_dcp_unchanged=sha(IMPL/'system_wrapper_routed.dcp')==before['routed_dcp_sha256'],project_configuration_unchanged=config()==before['project_configuration'],git_unchanged=git_same)
    save('protection_after.json',result); print('PHASE6_PROTECTION_AFTER='+result['status'],flush=True)
    assert ok, 'Protection audit failed; retained evidence requires review'

if __name__=='__main__':
    after() if '--after' in sys.argv else prepare()

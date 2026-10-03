"""Prepare fresh packaged-IP writer probe and CNN-only single-frame snapshots."""
import argparse
import json
import re
import shutil
from pathlib import Path

from sanity_sources import BASE, CONFIG, ROOT, compile_gate, legacy, sha, source_gate


def batch_prefix(run):
    return ('@echo off\nset "PROCESSOR_ARCHITECTURE=AMD64"\n'
            'call "E:\\Xilinx\\2025.2\\Vivado\\settings64.bat"\n'
            f'cd /d "{run}"\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ip-root', required=True, type=Path)
    parser.add_argument('--out-root', type=Path, default=ROOT / 'phase4g')
    parser.add_argument('--suffix', default='')
    args = parser.parse_args()
    assert not args.suffix or re.fullmatch(r'_[A-Za-z0-9_]+', args.suffix), 'unsafe output suffix'
    gate = source_gate(args.ip_root)
    root = args.out_root.resolve()
    root.mkdir(parents=True, exist_ok=True)
    assert not (root / ('writer_probe' + args.suffix)).exists() and not (root / ('cnn_single' + args.suffix)).exists(), 'refuse existing sanity output'
    packaged = [Path(x['path']) for x in gate['filesets']['simulation'] if Path(x['path']).suffix in ('.v', '.sv')]
    by_name = {p.name: p for p in packaged}
    probe = root / ('writer_probe' + args.suffix)
    probe.mkdir()
    old_probe = legacy('run_writer_probe')
    old_probe.FROZEN = by_name['zero_dce_cnn_top.v'].parent
    (probe / 'writer_probe.sv').write_text(old_probe.make_tb())
    files = packaged + [old_probe.DDR, probe / 'writer_probe.sv']
    compiled = compile_gate(files, gate)
    (probe / 'probe.prj').write_text('\n'.join(('sv' if p.suffix == '.sv' else 'verilog') + ' xil_defaultlib "' + p.as_posix() + '"' for p in files) + '\nnosort\n')
    (probe / 'sources.f').write_text('\n'.join('"' + p.as_posix() + '"' for p in files) + '\n')
    (probe / 'build.cmd').write_text(batch_prefix(probe) + 'call xelab -prj probe.prj xil_defaultlib.writer_probe -s writer_probe -mt 4 -log compile.log\nexit /b %errorlevel%\n')
    (probe / 'run.tcl').write_text('run all\nquit\n')
    probe_manifest = dict(status='PREPARED_NOT_RUN', package_source_gate=gate, compile_order=compiled,
                          ddr_sha256=sha(old_probe.DDR), reference_helper_sha256=sha(Path(old_probe.__file__)),
                          generated_tb_sha256=sha(probe / 'writer_probe.sv'),
                          config=dict(READ_OUTSTANDING=2, WRITE_OUTSTANDING=2, DDR_DELAY=16, SERVICE_PERIOD=1),
                          scope='Packaged IP only, four bounded b1/b7 aligned and 4KB/halfword stress scenarios; no old RTL run.')
    (probe / 'run_manifest.json').write_text(json.dumps(probe_manifest, indent=2))

    frozen = json.loads((BASE / 'source_manifest.json').read_text())
    for item in frozen['source_files']:
        assert sha(item['path']) == item['sha256'], item['path']
    for name, key in [('shared_axi_ddr.sv', 'ddr_model_sha256'), ('phase4_pl.v', 'pl_wrapper_sha256'), ('system_tb.sv', 'generated_tb_sha256')]:
        assert sha(BASE / name) == frozen[key]
    assert sha(BASE / 'shared_ddr.hex') == '5e675d404a1d5ceaea5088ba87e4197a134cbb851a8d2c45312dc13427579f0c'
    run = root / ('cnn_single' + args.suffix)
    run.mkdir()
    (run / 'results').mkdir()
    for p in BASE.iterdir():
        if p.is_file() and (p.suffix in ('.hex', '.dat') or p.name in ('phase4_pl.v', 'shared_axi_ddr.sv', 'xelab_options.txt')):
            shutil.copy2(p, run / p.name)
    # Redirect only the old CNN include directory. All other options and the
    # protected original options file remain byte-for-byte unchanged.
    old_cnn_dirs = {Path(x['path']).parent.as_posix() for x in frozen['source_files']
                    if Path(x['path']).name.startswith('zero_dce_cnn_top')}
    assert len(old_cnn_dirs) == 1
    old_cnn_dir = next(iter(old_cnn_dirs))
    formal_cnn_dir = by_name['zero_dce_cnn_top.v'].parent.as_posix()
    original_options_bytes = (BASE / 'xelab_options.txt').read_bytes()
    original_options = original_options_bytes.decode('utf-8')
    assert original_options.count('"' + old_cnn_dir + '"') == 1
    options = original_options.replace('"' + old_cnn_dir + '"', '"' + formal_cnn_dir + '"')
    assert options.replace('"' + formal_cnn_dir + '"', '"' + old_cnn_dir + '"') == original_options
    options_bytes = original_options_bytes.replace(('"' + old_cnn_dir + '"').encode(),
                                                    ('"' + formal_cnn_dir + '"').encode())
    assert options_bytes.decode('utf-8') == options
    (run / 'xelab_options.txt').write_bytes(options_bytes)
    include_dirs = [Path(p).resolve() for p in re.findall(r'-i\s+"([^"]+)"', options)]
    assert Path(formal_cnn_dir).resolve() in include_dirs
    assert Path(old_cnn_dir).resolve() not in include_dirs and not re.search(r'(?:^|\s)-y(?:\s|$)', options)
    for directory in include_dirs:
        for name in ('zero_dce_cnn_top_row_axi_writer.v', 'zero_dce_cnn_top_row_axi_writer_2.v',
                     'zero_dce_cnn_top_p_anonymous_namespace_output_writer.v'):
            candidate = directory / name
            if candidate.is_file():
                assert candidate.resolve() == by_name[name].resolve(), ('old writer include-directory shadow', candidate)
    declared = json.loads((args.ip_root / 'source_manifest.json').read_text())
    header_sets = [{x['path']: x['sha256'] for x in declared['filesets'][name] if Path(x['path']).suffix == '.vh'}
                   for name in ('xilinx_verilogsynthesis_view_fileset', 'xilinx_verilogbehavioralsimulation_view_fileset')]
    assert header_sets[0] == header_sets[1] and len(header_sets[0]) == 2
    header_sources = []
    for relative, digest in header_sets[0].items():
        path = (args.ip_root / relative).resolve()
        assert sha(path) == digest
        candidates = [directory / path.name for directory in include_dirs if (directory / path.name).is_file()]
        assert candidates == [path], ('ambiguous CNN header include search', path.name, candidates)
        assert not (run / path.name).exists()
        header_sources.append(dict(path=path.as_posix(), relative=relative, sha256=digest, resolved_include=path.as_posix()))
    source_search = dict(status='PASS', original_options_path=(BASE / 'xelab_options.txt').as_posix(),
                         original_options_sha256=sha(BASE / 'xelab_options.txt'),
                         generated_options_sha256=sha(run / 'xelab_options.txt'),
                         substitutions=[dict(original=old_cnn_dir, formal=formal_cnn_dir, count=1)],
                         all_other_options_byte_identical=True,
                         explicit_include_dirs=[p.as_posix() for p in include_dirs],
                         no_old_cnn_include_dir=True, no_old_module_search_dir=True,
                         header_sources=header_sources,
                         shared_hdl_composition=dict(verilog=139, verilog_headers=2, memory_initialization=9))
    (run / 'header_include_audit.json').write_text(json.dumps(source_search, indent=2))
    for item in gate['filesets']['simulation']:
        p = Path(item['path'])
        if p.suffix == '.dat':
            assert (run / p.name).is_file() and sha(run / p.name) == item['sha256'], ('package ROM differs', p.name)
    project = (BASE / 'system.prj').read_text().replace(BASE.as_posix(), run.as_posix())
    substitutions = []
    all_replacements = []
    for item in frozen['source_files']:
        old = Path(item['path'])
        if old.name.startswith('zero_dce_cnn_top'):
            assert old.name in by_name
            new = by_name[old.name]
            assert project.count('"' + old.as_posix() + '"') == 1
            project = project.replace('"' + old.as_posix() + '"', '"' + new.as_posix() + '"')
            record = dict(original=old.as_posix(), original_sha256=item['sha256'], candidate=new.as_posix(), candidate_sha256=sha(new))
            all_replacements.append(record)
            if item['sha256'] != sha(new):
                substitutions.append(record)
    assert len(all_replacements) == len(packaged) and len(substitutions) == 3
    (run / 'system.prj').write_text(project)
    files = [Path(p) for p in re.findall(r'^\w+\s+\w+\s+"([^"]+)"', project, re.M)]
    old_prepare = legacy('prepare_system')
    tb = (BASE / 'system_tb.sv').read_text()
    anchor = '            if(m==0) input_owner[slot]=-1;'
    assert tb.count(anchor) == 1 and tb.endswith('endmodule\n')
    tb = tb.replace(anchor, anchor + '\n            if(m==0) phase4g_finish();')
    append, busmap, funcmap = old_prepare.observer()
    append += '''\n  // PHASE4G: final all-HP response check before the original Phase4E finish.
  task phase4g_finish;
    begin
      for(integer h=0;h<4;h=h+1) begin
        if(ddr.rc[h]!=0 || ddr.wc[h]!=0 || ddr.wp[h]!=0 || ddr.rvalid[h] || ddr.bvalid[h]) $fatal(1,"PHASE4G final responses not drained");
        $display("PHASE4G_ALL_RESPONSES_DRAIN HP=%0d RC=%0d WC=%0d WP=%0d RVALID=%0d BVALID=%0d",h,ddr.rc[h],ddr.wc[h],ddr.wp[h],ddr.rvalid[h],ddr.bvalid[h]);
      end
      phase4e_finish();
    end
  endtask
'''
    (run / 'observer_append.sv').write_text(append)
    (run / 'system_tb.sv').write_text(tb[:-len('endmodule\n')] + append + 'endmodule\n')
    compiled = compile_gate(files, gate)
    (run / 'run.tcl').write_text('run all\nquit\n')
    elaboration = 'call xelab --relax --mt 2 -prj system.prj -f xelab_options.txt xil_defaultlib.phase4_system_tb xil_defaultlib.glbl -s phase4e_system -log elaborate.log\nexit /b %errorlevel%\n'
    (run / 'elaborate.cmd').write_text(batch_prefix(run) + elaboration)
    simulation = (f'call xsim phase4e_system -tclbatch run.tcl -log system.log -testplusarg "OUTPUT_DIR={run.as_posix()}/results" ' +
                  ' '.join(f'-testplusarg "{k}={v}"' for k, v in CONFIG.items()) + '\nexit /b %errorlevel%\n')
    (run / 'simulate.cmd').write_text(batch_prefix(run) + simulation)
    protected = {p.name: sha(p) for p in run.iterdir() if p.is_file() and (p.suffix in ('.hex', '.dat') or p.name in ('phase4_pl.v', 'shared_axi_ddr.sv', 'xelab_options.txt'))}
    manifest = dict(status='PREPARED_NOT_RUN', config=CONFIG, reference=BASE.as_posix(),
                    substitutions=substitutions, original_source_manifest=frozen, all_cnn_source_replacements=all_replacements,
                    package_source_gate=gate, compile_order=compiled, protected_copies=protected,
                    bus_map=busmap, function_map=funcmap, original_tb_sha256=sha(BASE / 'system_tb.sv'),
                    generated_tb_sha256=sha(run / 'system_tb.sv'), reference_prepare_sha256=sha(Path(old_prepare.__file__)),
                    source_search_audit=source_search, source_search_audit_sha256=sha(run / 'header_include_audit.json'),
                    scope='CNN only, original Phase4E BFM numerical/guard/hazard/IRQ gate. No Bilinear/Curve start. All DUT CNN sources are packaged IP simulation sources.',
                    source_scope='All 139 CNN RTL references replaced with released fileset sources; only three hashes differ from frozen r4.')
    (run / 'run_manifest.json').write_text(json.dumps(manifest, indent=2))
    print(json.dumps(dict(status='PACKAGED_SANITY_PREPARED', root=root.as_posix(), cnn_packaged_rtl_count=len(packaged), changed_rtl_count=3)))


if __name__ == '__main__':
    main()

"""Run a bounded Phase6 batch and record its natural exit; no timeouts/retries."""
import datetime, json, os, subprocess, sys
from pathlib import Path
OUT=Path(__file__).resolve().parent
TZ=datetime.timezone(datetime.timedelta(hours=8))
def stamp(): return datetime.datetime.now(TZ).isoformat()
stage=sys.argv[1]
assert stage in ('bitstream','export_xsa')
assert not (OUT/(stage+'_exit_status.json')).exists(), 'Do not overwrite natural-exit evidence'
runner=OUT/(stage+'.cmd')
runner.write_text('\n'.join(['@echo off','setlocal','set "PROCESSOR_ARCHITECTURE=AMD64"',
  'call "E:\\Xilinx\\2025.2\\data\\settings64.bat" || exit /b 1',
  'call "E:\\Xilinx\\2025.2\\Vivado\\bin\\vivado.bat" -mode batch -notrace -source "'+str(OUT/(stage+'.tcl'))+'" -log "'+str(OUT/(stage+'_vivado.log'))+'" -journal "'+str(OUT/(stage+'_vivado.jou'))+'" -tclargs "'+str(OUT)+'"',
  'exit /b %ERRORLEVEL%','']),encoding='utf-8')
started=stamp(); print('PHASE6_'+stage.upper()+'_START='+started,flush=True)
with (OUT/(stage+'_console.log')).open('wb') as f:
    result=subprocess.run(['cmd.exe','/d','/c',str(runner)],cwd=OUT,env={**os.environ,'PROCESSOR_ARCHITECTURE':'AMD64'},stdout=f,stderr=subprocess.STDOUT)
(OUT/(stage+'_exit_status.json')).write_text(json.dumps(dict(returncode=result.returncode,started_at=started,ended_at=stamp(),natural_process_exit=True,forced_termination=False),indent=2)+'\n')
print('PHASE6_'+stage.upper()+'_EXIT='+str(result.returncode),flush=True)
sys.exit(result.returncode)

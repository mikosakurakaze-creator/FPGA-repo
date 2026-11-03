"""Run available controller/report regressions using packaged files only."""
import os,shutil,subprocess,sys,tempfile,json,argparse
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--out',type=Path,required=True);a=ap.parse_args();assert not a.out.exists();a.out.mkdir(parents=True)
    with tempfile.TemporaryDirectory(prefix='kv260_host_') as d:
        d=Path(d);shutil.copytree(ROOT/'hardware/runtime',d/'runtime');shutil.copytree(ROOT/'hardware/source/tests',d/'tests');shutil.copytree(ROOT/'hardware/source/scripts',d/'scripts')
        env=os.environ.copy();env['PYTHONPATH']=str(d/'runtime')+os.pathsep+str(d/'scripts')
        cmd=[sys.executable,'-B','-m','unittest','discover','-s',str(d/'tests'),'-p','test_*.py','-v']
        with (a.out/'host_tests.log').open('wb') as f:p=subprocess.run(cmd,cwd=d,env=env,stdout=f,stderr=subprocess.STDOUT)
        (a.out/'host_tests.json').write_text(json.dumps(dict(exit_code=p.returncode,scope='controller and report parser host regressions; no hardware access'),indent=2))
        print('HOST_TEST_EXIT',p.returncode)
        raise SystemExit(p.returncode)
if __name__=='__main__':main()

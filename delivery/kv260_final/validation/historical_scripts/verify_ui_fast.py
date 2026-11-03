import os,sys
from pathlib import Path
base=Path('/home/ubuntu/traffic_hdmi');os.chdir(base)
s=(base/'app.py').read_text();s=s[:s.index('import fcntl,sys')]
exec(compile(s,str(base/'app.py'),'exec'))
app=App();app.verify_no_loop=True;app.show_all();state={'phase':'start'};begin=time.perf_counter()
def tick():
 try:
  if state['phase']=='start':
   app.person.set_active(False);app.car.set_active(False);app.set_input('/home/ubuntu/Videos/展示视频_雨夜交通_8秒.avi');app.run(None);state['phase']='processing';return True
  if state['phase']=='processing' and not app.busy:
   jobs=sorted(OUTPUT.glob('*/job.json'));j=json.loads(jobs[-1].read_text());assert j['status']=='completed',j;assert j['frames']==192,j;state['processing']=j;app.play_video(None);state['phase']='playing';state['mark']=time.perf_counter();return True
  if state['phase']=='playing' and time.perf_counter()-state['mark']>2:
   app.toggle_pause(None);state['index']=app.video_index;state['mark']=time.perf_counter();state['phase']='paused';return True
  if state['phase']=='paused' and time.perf_counter()-state['mark']>2:
   assert app.video_index==state['index'],(app.video_index,state['index']);app.toggle_pause(None);state['phase']='resumed';return True
  if state['phase']=='resumed' and not app.busy:
   m=json.loads((BASE/'video_playback_test.json').read_text());assert m['error'] is None and m['frames']==192,m;state['pause_resume_pass']=True;state['phase']='pass';state['total_seconds']=time.perf_counter()-begin;(BASE/'fast_ui_validation.json').write_text(json.dumps(state,ensure_ascii=False,indent=2));print('UI_FAST_PASS',state['processing']['active_fps'],flush=True);Gtk.main_quit();return False
 except Exception as e:
  state.update(phase='failed',error=str(e));(BASE/'fast_ui_validation.json').write_text(json.dumps(state,ensure_ascii=False,indent=2));traceback.print_exc();Gtk.main_quit();return False
 return True
GLib.timeout_add(200,tick);Gtk.main()

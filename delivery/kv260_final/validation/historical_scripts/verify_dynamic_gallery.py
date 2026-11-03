import os,sys,json,time
from pathlib import Path
base=Path('/home/ubuntu/traffic_hdmi');os.chdir(base)
s=(base/'app.py').read_text();s=s[:s.index('import fcntl,sys')];exec(compile(s,str(base/'app.py'),'exec'))
app=App();app.verify_no_loop=True;app.show_all();state={'phase':'start','clips':[]};ids=[m['id'] for m in app.video_gallery if m['id']!='original_rain'];ids=[sys.argv[1]] if len(sys.argv)>1 and not sys.argv[1].startswith('--') else ids;assert ids;position=0
# Test each clip, including pausing with real detections on screen.
def tick():
 global position
 try:
  if state['phase']=='start':
   app.video_choice.set_active_id(ids[position]);app.play_video(None);state['phase']='playing';state['mark']=time.perf_counter();return True
  if state['phase']=='playing' and time.perf_counter()-state['mark']>2:
   app.toggle_pause(None);state['index']=app.video_index;state['boxes']=json.dumps(app.compare.overlays);state['mark']=time.perf_counter();state['phase']='paused';return True
  if state['phase']=='paused' and time.perf_counter()-state['mark']>1:
   assert app.video_index==state['index'];assert json.dumps(app.compare.overlays)==state['boxes'];app.boxes_toggle.set_active(False);assert not app.compare.show_overlays;app.boxes_toggle.set_active(True);assert app.compare.show_overlays;app.toggle_pause(None);state['phase']='resumed';return True
  if state['phase']=='resumed' and not app.busy:
   result=json.loads((BASE/'video_playback_test.json').read_text());assert result['error'] is None and result['frames']==144,result
   cache=app.video_detection_rows;assert len(cache)==144;counts=[sum(d['score']>=.25 for d in r['detections']) for r in cache];assert max(counts)>0
   for i,r in enumerate(cache,1):assert r['frame']==i
   state['clips'].append({'id':ids[position],'frames':144,'pause_frame':state['index'],'pause_resume_pass':True,'counts':sorted(set(counts))});position+=1
   if position<len(ids):state['phase']='start';return True
   state['phase']='pass';(BASE/'dynamic_gallery_validation.json').write_text(json.dumps(state,indent=2));print('DYNAMIC_GALLERY_PASS',state['clips'],flush=True);Gtk.main_quit();return False
 except Exception as e:
  state.update(phase='failed',error=str(e));(BASE/'dynamic_gallery_validation.json').write_text(json.dumps(state,indent=2));traceback.print_exc();Gtk.main_quit();return False
 return True
GLib.timeout_add(100,tick);Gtk.main()

if "--launch" in sys.argv:
 import subprocess
 log=open(BASE/"app.log","w");subprocess.Popen([sys.executable,str(BASE/"app.py"),"--show-video"],stdout=log,stderr=log,start_new_session=True)

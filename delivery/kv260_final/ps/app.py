import gi,json,time,threading,traceback,subprocess
from pathlib import Path
gi.require_version('Gtk','3.0');from gi.repository import Gtk,Gdk,GdkPixbuf,GLib
from PIL import Image
from engine import Engine,VideoReader,VideoWriter,BASE
from compare_view import CompareView
OUTPUT=BASE/'results';OUTPUT.mkdir(exist_ok=True)
class App(Gtk.Window):
 def __init__(self):
  super().__init__(title='交通视觉实验平台 · KV260');self.set_default_size(1024,720);self.busy=False;self.stop=threading.Event();self.paused=threading.Event();self.engine=Engine();self.input=None;self.paths=[None,None];self.close_requested=False;self.connect('delete-event',self.on_close)
  css=Gtk.CssProvider();css.load_from_data(b'window {background:#edf2f7;} button {padding:5px;} .title {font-size:21px;font-weight:bold;color:#17354d;} .panel {background:white;padding:10px;}');Gtk.StyleContext.add_provider_for_screen(Gdk.Screen.get_default(),css,600)
  root=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=8);root.set_border_width(12);self.add(root)
  title=Gtk.Label(label='交通视觉实验平台');title.get_style_context().add_class('title');root.pack_start(title,False,False,0)
  self.device=Gtk.Label();root.pack_start(self.device,False,False,0);tabs=Gtk.Notebook();root.pack_start(tabs,True,True,0)
  page=Gtk.Box(spacing=12);tabs.append_page(page,Gtk.Label(label='处理工作台'))
  side=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=5);side.set_size_request(205,-1);side.set_hexpand(False);side.get_style_context().add_class('panel');page.pack_start(side,False,False,0);self.controls=[]
  for label,cb in [('打开图片 / 视频',self.choose)]:
   b=Gtk.Button(label=label);b.connect('clicked',cb);side.pack_start(b,False,False,0);self.controls.append(b)
  videos=Gtk.Box(spacing=4);self.video_choice=Gtk.ComboBoxText();self.video_choice.set_hexpand(False)
  self.video_gallery=json.loads((BASE/'video_gallery.json').read_text()) if (BASE/'video_gallery.json').exists() else []
  for info in self.video_gallery:self.video_choice.append(info['id'],info['title'])
  self.video_choice.set_active_id('night_street' if any(m['id']=='night_street' for m in self.video_gallery) else 'original_rain');videos.pack_start(self.video_choice,True,True,0);play=Gtk.Button(label='播放');play.connect('clicked',self.play_video);videos.pack_start(play,False,False,0);side.pack_start(videos,False,False,0);self.controls.extend([self.video_choice,play])
  self.filename=Gtk.Label(label='尚未选择输入');self.filename.set_line_wrap(True);self.filename.set_max_width_chars(22);side.pack_start(self.filename,False,False,0)
  self.person=Gtk.CheckButton(label='行人检测');self.car=Gtk.CheckButton(label='车辆检测')
  for b in [self.person,self.car]:b.set_active(True);side.pack_start(b,False,False,0);self.controls.append(b)
  self.branch=Gtk.ComboBoxText()
  for k,v in [('fused','最终融合'),('lowlight','低照度单通路'),('d','去雨雾通路'),('original','原图检测')]:self.branch.append(k,v)
  self.branch.set_active_id('fused');side.pack_start(self.branch,False,False,0);self.controls.append(self.branch)
  side.pack_start(Gtk.Label(label='检测置信度'),False,False,0);self.threshold=Gtk.SpinButton.new_with_range(.05,.95,.05);self.threshold.set_value(.25);self.threshold.set_digits(2);side.pack_start(self.threshold,False,False,0);self.controls.append(self.threshold)
  b=Gtk.Button(label='开始处理');b.connect('clicked',self.run);side.pack_start(b,False,False,0);self.controls.append(b)
  self.pause_button=Gtk.Button(label='暂停播放');self.pause_button.set_sensitive(False);self.pause_button.connect('clicked',self.toggle_pause);side.pack_start(self.pause_button,False,False,0)
  self.cancel=Gtk.Button(label='安全停止');self.cancel.set_sensitive(False);self.cancel.connect('clicked',lambda b:self.request_stop());side.pack_start(self.cancel,False,False,0)
  b=Gtk.Button(label='打开结果目录');b.connect('clicked',lambda b:subprocess.Popen(['xdg-open',str(OUTPUT)]));side.pack_start(b,False,False,0)
  right=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=8);page.pack_start(right,True,True,0)
  heading=Gtk.Box();heading.pack_start(Gtk.Label(label='左侧：原图'),False,False,0);heading.pack_end(Gtk.Label(label='右侧：增强结果'),False,False,0);self.boxes_toggle=Gtk.CheckButton(label='车辆框');self.boxes_toggle.set_active(True);self.boxes_toggle.connect('toggled',self.toggle_boxes);heading.pack_start(self.boxes_toggle,True,False,0);right.pack_start(heading,False,False,0)
  self.compare=CompareView();right.pack_start(self.compare,True,True,0)
  right.pack_start(Gtk.Label(label='左右拖动分隔线对比 · 双击居中'),False,False,0)
  self.status=Gtk.Label(label='就绪。图片与视频均在板端执行。首次检测需初始化模型。');self.status.set_line_wrap(True);right.pack_start(self.status,False,False,0);self.stats=Gtk.Label(label='行人 — | 车辆 —');right.pack_start(self.stats,False,False,0)
  box=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=10);box.set_border_width(16);tabs.append_page(box,Gtk.Label(label='任务记录'));self.history=Gtk.TextView();self.history.set_editable(False);scroll=Gtk.ScrolledWindow();scroll.add(self.history);box.pack_start(scroll,True,True,0);b=Gtk.Button(label='刷新记录');b.connect('clicked',lambda b:self.refresh_history());box.pack_start(b,False,False,0)
  self.connect('size-allocate',lambda *a:self.render());GLib.timeout_add_seconds(2,self.health);self.health();self.refresh_history()
 def toggle_boxes(self,b):
  self.compare.show_overlays=b.get_active();self.compare.queue_draw()
 def health(self):
  try:p='%.2f W'%(int(Path('/sys/class/hwmon/hwmon2/power1_input').read_text())/1e6)
  except Exception:p='不可用'
  self.device.set_text(('硬件服务已启动' if (BASE/'hardware.sock').exists() else '硬件服务未启动')+' · SOM '+p+' · 板端本地运行');return True
 def render(self):
  try:self.compare.load(self.paths)
  except Exception as e:self.status.set_text('预览失败：'+str(e))
 def restore_last(self):
  try:
   jobs=sorted(OUTPUT.glob('*/job.json'),reverse=True)
   for path in jobs:
    j=json.loads(path.read_text());folder=path.parent
    if j['status']=='completed' and (folder/'detected.png').is_file():
     self.input=Path(j['input']);self.filename.set_text(self.input.name);self.branch.set_active_id(j['branch']);self.paths=[folder/'original.png',folder/'detected.png'];self.render();self.status.set_text('拖动分隔线查看对比');break
  except Exception as e:self.status.set_text(str(e))
  return False
 def set_input(self,path):
  self.compare.overlays=[]
  self.compare.live=False
  self.input=Path(path);self.filename.set_text(self.input.name)
  try:Image.open(path).verify();self.paths=[path,None];self.render()
  except Exception:self.paths=[None,None];self.render()
  self.status.set_text('已选择 '+self.input.name)
 def choose(self,b):
  d=Gtk.FileChooserDialog(title='选择板端图片或视频',parent=self,action=Gtk.FileChooserAction.OPEN);d.add_buttons('取消',Gtk.ResponseType.CANCEL,'打开',Gtk.ResponseType.OK);f=Gtk.FileFilter();f.set_name('图片与视频')
  for pat in ['*.png','*.jpg','*.jpeg','*.mp4','*.avi','*.mkv','*.mov','*.webm']:f.add_pattern(pat)
  d.add_filter(f)
  if d.run()==Gtk.ResponseType.OK:self.set_input(d.get_filename())
  d.destroy()

 def play_video(self,b):
  if self.busy:return
  if not self.video_gallery:self.status.set_text('展示视频正在准备');return
  info=next(m for m in self.video_gallery if m['id']==self.video_choice.get_active_id());self.video_meta=info;self.input=Path(info['source']);self.filename.set_text(self.input.name)
  self.paused.clear();self.pause_button.set_label('暂停播放');self.pause_button.set_sensitive(True)
  cache=Path(info.get('detections_file',str(BASE/'video_detections.json')));self.video_detection_rows=json.loads(cache.read_text())['frames'] if cache.is_file() else []
  self.person.set_active(False);self.car.set_active(True)
  self.busy=True;self.stop.clear();self.compare.live=True;self.compare.ratio=.5;[c.set_sensitive(False) for c in self.controls];self.cancel.set_sensitive(True);self.status.set_text('视频播放中 · 可左右拖动对比');threading.Thread(target=self.video_worker,daemon=True).start()
 def video_frame(self,a,b,done,index):
  if self.stop.is_set():done.set();return False
  if self.paused.is_set():GLib.timeout_add(50,self.video_frame,a,b,done,index);return False
  self.video_index=index
  rows=self.video_detection_rows[index-1]['detections'] if index<=len(self.video_detection_rows) else None
  self.compare.overlays=[r for r in rows if r['score']>=self.threshold.get_value()] if rows is not None else []
  try:
   self.compare.pix=[GdkPixbuf.Pixbuf.new_from_bytes(GLib.Bytes.new(im.tobytes()),GdkPixbuf.Colorspace.RGB,False,8,im.width,im.height,im.width*3) for im in [a,b]];self.compare.queue_draw();self.stats.set_text('播放位置 %.2f / %.2f 秒 · 帧 %d/%d · 车辆 %s'%(index/self.video_meta['fps'],self.video_meta['duration_seconds'],index,self.video_meta['frames'],str(len(self.compare.overlays)) if rows is not None else '—'))
  finally:done.set()
  return False
 def video_worker(self):
  readers=[];error=None
  try:
   m=self.video_meta;readers=[VideoReader(m['source']),VideoReader(m['enhanced'])];streams=[r.frames(self.stop) for r in readers];start=time.perf_counter()
   for index,((a,ta),(b,tb)) in enumerate(zip(*streams),1):
    wait_start=time.perf_counter()
    if not self.wait_pause():break
    frame_start=time.perf_counter()
    if ta is not None and tb is not None and abs(ta-tb)>.002:raise RuntimeError('视频帧时间不同步')
    done=threading.Event();GLib.idle_add(self.video_frame,a,b,done,index)
    while not done.wait(.1):
     if self.stop.is_set():break
    self.stop.wait(max(0,1/m['fps']-(time.perf_counter()-frame_start)))
  except Exception as e:error=str(e)
  finally:
   for r in readers:
    if r.pipe is not None:r.pipe.set_state(__import__('engine').Gst.State.NULL)
   (BASE/'video_playback_test.json').write_text(json.dumps({'error':error,'frames':locals().get('index',0),'stopped':self.stop.is_set()}))
   GLib.idle_add(self.video_finish,error)
 def video_finish(self,error):
  self.pause_button.set_sensitive(False);self.paused.clear();self.pause_button.set_label('暂停播放')
  self.busy=False;[c.set_sensitive(True) for c in self.controls];self.cancel.set_sensitive(False);self.status.set_text('播放失败：'+error if error else '已停止' if self.stop.is_set() else '播放完成')
  if self.close_requested:Gtk.main_quit()
  elif not error and not self.stop.is_set() and not getattr(self,'verify_no_loop',False):GLib.timeout_add(1000,lambda:(self.play_video(None),False)[1])
  return False
 def sample(self,weather):
  import numpy as np
  image=Image.fromarray(np.frombuffer((BASE.parent/'hardware/golden/rgb.u8').read_bytes(),dtype=np.uint8).reshape(720,1272,3));path=BASE/'golden_input.png';image.save(path);self.set_input(path)
 def toggle_pause(self,b):
  if not self.busy:return
  if self.paused.is_set():self.paused.clear();self.pause_button.set_label('暂停播放');self.status.set_text('继续运行')
  else:self.paused.set();self.pause_button.set_label('继续播放');self.status.set_text('已暂停 · 可拖动对比')
 def wait_pause(self):
  while self.paused.is_set() and not self.stop.is_set():self.stop.wait(.05)
  return not self.stop.is_set()
 def request_stop(self):self.stop.set();self.paused.clear();self.cancel.set_sensitive(False);self.status.set_text('正在结束当前批次并保存…')
 def on_close(self,*args):
  if self.busy:self.close_requested=True;self.request_stop();return True
  Gtk.main_quit();return False
 def refresh_history(self):
  rows=[]
  for p in sorted(OUTPUT.glob('*/job.json'),reverse=True):
   try:j=json.loads(p.read_text());rows.append(j['id']+'  '+j['status']+'  '+str(j.get('frames',0))+' 帧  '+j['input'])
   except Exception:pass
  self.history.get_buffer().set_text('\n'.join(rows) or '尚无任务')
 def run(self,b):
  self.compare.live=False
  if self.busy:return
  if not self.input:self.status.set_text('请先选择图片或视频');return
  tasks=[]
  if self.person.get_active():tasks.append('pedestrian')
  if self.car.get_active():tasks.append('vehicle')
  self.paused.clear();self.pause_button.set_sensitive(True);self.pause_button.set_label('暂停播放')
  config={'id':str(time.time_ns()),'input':str(self.input),'branch':self.branch.get_active_id(),'tasks':tasks,'threshold':self.threshold.get_value(),'status':'processing','frames':0};self.busy=True;self.stop.clear();[c.set_sensitive(False) for c in self.controls];self.cancel.set_sensitive(True);self.status.set_text('准备中。首次模型初始化需要较长时间。');threading.Thread(target=self.work,args=(config,),daemon=True).start()
 def update(self,original,result,meta,count,elapsed):
  old=self.paths;self.paths=[original,result];self.render()
  for path in old:
   if path and Path(path).name.startswith('preview_') and path not in self.paths:Path(path).unlink(missing_ok=True)
  det=meta['detections'];self.status.set_text('已完成 %d 帧 · 结果已保存'%count);self.stats.set_text('行人 %d | 车辆 %d'%(sum(d['class']=='pedestrian' for d in det),sum(d['class']=='vehicle' for d in det)));return False
 def update_memory(self,original,result,meta,count,elapsed):
  self.compare.overlays=[]
  self.compare.live=True;self.compare.pix=[GdkPixbuf.Pixbuf.new_from_bytes(GLib.Bytes.new(im.tobytes()),GdkPixbuf.Colorspace.RGB,False,8,im.width,im.height,im.width*3) for im in [original,result]];self.compare.queue_draw();det=meta['detections'];self.status.set_text('处理中 · %d 帧'%count if not self.paused.is_set() else '已暂停 · 可拖动对比');self.stats.set_text('行人 %d | 车辆 %d'%(sum(d['class']=='pedestrian' for d in det),sum(d['class']=='vehicle' for d in det)));return False
 def work(self,j):
  import itertools
  folder=OUTPUT/j['id'];folder.mkdir();writer=None;frames=None;video=False;last=None;begin=time.perf_counter();paused_time=0
  try:
   video=Path(j['input']).suffix.lower() in ['.mp4','.avi','.mkv','.mov','.webm'];reader=VideoReader(j['input']) if video else None;frames=reader.frames(self.stop) if video else iter([(Image.open(j['input']).convert('RGB'),None)]);(folder/'job.json').write_text(json.dumps(j,ensure_ascii=False));iterator=iter(frames)
   with (folder/'frames.jsonl').open('w') as record:
    while not self.stop.is_set():
     wait=time.perf_counter()
     if not self.wait_pause():break
     paused_time+=time.perf_counter()-wait
     chunk=list(itertools.islice(iterator,6 if video else 1))
     if not chunk:break
     results=self.engine.batch([x[0] for x in chunk],j['branch'],j['tasks'],j['threshold'])
     for (image,pts),(result,draw,meta) in zip(chunk,results):
      wait=time.perf_counter()
      if not self.wait_pause():break
      paused_time+=time.perf_counter()-wait
      j['frames']+=1;meta.update(frame_id=j['frames'],source_seconds=pts);record.write(json.dumps(meta)+'\n')
      if video:
       if writer is None:writer=VideoWriter(folder/'annotated.avi',draw.width,draw.height,reader.fps)
       writer.push(draw)
      last=(image,result,draw,meta)
     record.flush()
     if last:GLib.idle_add(self.update_memory,last[0],last[2],last[3],j['frames'],time.perf_counter()-begin-paused_time)
   j['status']='stopped' if self.stop.is_set() else 'completed'
  except Exception as e:j.update(status='failed',error=str(e));(folder/'error.log').write_text(traceback.format_exc())
  finally:
   if video and hasattr(frames,'close'):frames.close()
   if writer:
    try:writer.close()
    except Exception as e:j.update(status='failed',error=str(e))
   if last:last[0].save(folder/'original.png');last[1].save(folder/'enhanced.png');last[2].save(folder/'detected.png')
   j['elapsed_seconds']=time.perf_counter()-begin;j['paused_seconds']=paused_time;j['active_fps']=j['frames']/max(.001,j['elapsed_seconds']-paused_time);j['batch_size']=6 if video else 1;(folder/'job.json').write_text(json.dumps(j,ensure_ascii=False,indent=2));GLib.idle_add(self.finish,j)
 def finish(self,j):
  self.pause_button.set_sensitive(False);self.paused.clear();self.pause_button.set_label('暂停播放')
  self.busy=False;[c.set_sensitive(True) for c in self.controls];self.cancel.set_sensitive(False);self.refresh_history();self.status.set_text({'completed':'处理完成','stopped':'已安全停止','failed':'处理失败'}.get(j['status'],j['status'])+' · '+str(j['frames'])+' 帧'+(' · '+j.get('error','') if j['status']=='failed' else ''))
  if self.close_requested:Gtk.main_quit()
  return False
import fcntl,sys
instance_lock=open(BASE/'gui.lock','a')
try:fcntl.flock(instance_lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
except BlockingIOError:sys.exit(0)
app=App();app.show_all();GLib.idle_add(app.restore_last)
if '--show-video' in sys.argv:GLib.timeout_add(1500,lambda:(app.play_video(None),False)[1])
import sys
if '--self-test' in sys.argv:
 def start_test():
  if '--video-self-test' in sys.argv:app.set_input(BASE/'test_input.avi')
  else:app.sample('rain')
  app.run(None);return False
 def check_test():
  if app.busy:return True
  if app.input is None:return True
  (BASE/'gui_test.json').write_text(json.dumps({'status':app.status.get_text(),'stats':app.stats.get_text()}))
  window=Gdk.get_default_root_window();Gdk.pixbuf_get_from_window(window,0,0,window.get_width(),window.get_height()).savev(str(BASE/'gui_test.png'),'png',[],[])
  return False
 GLib.timeout_add(1000,start_test);GLib.timeout_add_seconds(3,check_test)
Gtk.main()

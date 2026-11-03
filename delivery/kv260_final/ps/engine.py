import sys,json,time,socket,struct,threading
from pathlib import Path
BASE=Path(__file__).resolve().parent;sys.path.insert(0,str(BASE/'deps'))
import numpy as np
from PIL import Image,ImageOps,ImageDraw
import gi
gi.require_version('Gst','1.0')
from gi.repository import Gst
Gst.init(None)
def recv(c,n):
 b=bytearray()
 while len(b)<n:
  part=c.recv(n-len(b))
  if not part:raise RuntimeError('硬件服务连接中断')
  b.extend(part)
 return bytes(b)
class Engine:
 def __init__(self):self.session=None
 def detect(self,image,tasks,threshold):
  if not tasks:return [],0
  import onnxruntime as ort
  if self.session is None:
   opt=ort.SessionOptions();opt.intra_op_num_threads=2;opt.inter_op_num_threads=1
   cache=BASE/'ssd_optimized.onnx'
   if not cache.exists():opt.optimized_model_filepath=str(cache)
   else:opt.graph_optimization_level=ort.GraphOptimizationLevel.ORT_DISABLE_ALL
   self.session=ort.InferenceSession(str(cache if cache.exists() else BASE/'hdmi_runtime_assets/ssd_mobilenet.onnx'),opt,providers=['CPUExecutionProvider'])
  start=time.perf_counter();small=image.resize((300,300),Image.BILINEAR)
  results=self.session.run(None,{self.session.get_inputs()[0].name:np.asarray(small,dtype=np.uint8)[None]});out=dict(zip([x.name for x in self.session.get_outputs()],results));rows=[]
  for box,cls,score in zip(out['detection_boxes'][0],out['detection_classes'][0],out['detection_scores'][0]):
   label='pedestrian' if int(cls)==1 else 'vehicle' if int(cls) in [2,3,4,6,8] else None
   if label in tasks and float(score)>=threshold:
    y0,x0,y1,x1=map(float,box);rows.append({'class':label,'score':float(score),'box':[max(0,x0*image.width),max(0,y0*image.height),min(image.width,x1*image.width),min(image.height,y1*image.height)]})
  return rows,(time.perf_counter()-start)*1000
 def frame(self,image,branch,tasks,threshold):
  return self.batch([image],branch,tasks,threshold)[0]
 def batch(self,images,branch,tasks,threshold):
  if not 1<=len(images)<=6:raise ValueError('Batch size must be 1..6')
  begin=time.perf_counter();images=[ImageOps.exif_transpose(im).convert('RGB') for im in images];results=[];meta={'hardware_ms':0,'build':None}
  if branch=='original':results=[im.copy() for im in images]
  else:
   raw=[];boxes=[]
   for image in images:
    w,h=image.size;scale=min(1272/w,720/h);nw,nh=max(1,round(w*scale)),max(1,round(h*scale));left=(1272-nw)//2;top=(720-nh)//2
    canvas=Image.new('RGB',(1272,720));canvas.paste(image.resize((nw,nh),Image.BILINEAR),(left,top));raw.append(canvas.tobytes());boxes.append((left,top,left+nw,top+nh))
   with socket.socket(socket.AF_UNIX) as c:
    c.settimeout(150);c.connect(str(BASE/'hardware.sock'));c.sendall(bytes([{'lowlight':0,'d':1,'fused':2}[branch],len(images)])+b''.join(raw));meta=json.loads(recv(c,struct.unpack('!I',recv(c,4))[0]))
    if not meta['ok']:raise RuntimeError(meta['error'])
    data=recv(c,meta['bytes'])
   for i,image in enumerate(images):results.append(Image.frombytes('RGB',(1272,720),data[i*2747520:(i+1)*2747520]).crop(boxes[i]).resize(image.size,Image.BILINEAR))
  output=[]
  for image,result in zip(images,results):
   rows,ms=self.detect(result,tasks,threshold);annotated=result.copy();draw=ImageDraw.Draw(annotated);w=image.width
   for row in rows:
    color='#00c9ac' if row['class']=='pedestrian' else '#ff9e40';draw.rectangle(row['box'],outline=color,width=max(2,w//400));draw.text((row['box'][0],max(0,row['box'][1]-14)),row['class']+' %.2f'%row['score'],fill=color)
   output.append((result,annotated,{'detections':rows,'hardware_ms':meta['hardware_ms']/len(images),'batch_hardware_ms':meta['hardware_ms'],'batch_frames':len(images),'detect_ms':ms,'total_ms':(time.perf_counter()-begin)*1000,'build':meta.get('build'),'detector':'SSD-MobileNetV1 ONNX CPU' if tasks else None}))
  return output
class VideoReader:
 def __init__(self,path):
  self.pipe=Gst.parse_launch('uridecodebin uri="'+Path(path).resolve().as_uri()+'" name=d d. ! queue max-size-buffers=2 ! video/x-raw,format=I420 ! videoconvert ! video/x-raw,format=RGB ! appsink name=sink max-buffers=1 drop=false sync=false')
  self.sink=self.pipe.get_by_name('sink');self.pipe.set_state(Gst.State.PLAYING);self.pipe.get_state(10*Gst.SECOND);self.fps=25
 def frames(self,stop):
  bus=self.pipe.get_bus()
  try:
   while not stop.is_set():
    sample=self.sink.emit('try-pull-sample',Gst.SECOND)
    if sample:
     caps=sample.get_caps().get_structure(0);w=caps.get_value('width');h=caps.get_value('height');ok,num,den=caps.get_fraction('framerate');self.fps=num/den if ok and num else 25
     b=sample.get_buffer();data=b.extract_dup(0,b.get_size());yield Image.frombytes('RGB',(w,h),data,'raw','RGB',len(data)//h),b.pts/Gst.SECOND if b.pts!=Gst.CLOCK_TIME_NONE else None
    elif self.sink.get_property('eos'):
     msg=bus.pop_filtered(Gst.MessageType.ERROR)
     if msg:raise RuntimeError(str(msg.parse_error()[0]))
     break
    else:
     msg=bus.pop_filtered(Gst.MessageType.ERROR)
     if msg:raise RuntimeError(str(msg.parse_error()[0]))
  finally:self.pipe.set_state(Gst.State.NULL)
class VideoWriter:
 def __init__(self,path,w,h,fps):
  from fractions import Fraction
  f=Fraction(fps).limit_denominator(1001);self.step=int(Gst.SECOND/fps);self.index=0
  self.pipe=Gst.parse_launch('appsrc name=source format=time is-live=false block=true max-bytes=16777216 caps="video/x-raw,format=RGB,width=%d,height=%d,framerate=%d/%d" ! queue max-size-buffers=2 ! videoconvert ! video/x-raw,format=I420 ! jpegenc quality=85 ! avimux ! filesink location="%s"'%(w,h,f.numerator,f.denominator,path))
  self.source=self.pipe.get_by_name('source');self.pipe.set_state(Gst.State.PLAYING)
 def push(self,image):
  # Gst RGB rows have four-byte alignment.
  a=np.asarray(image);stride=(image.width*3+3)//4*4;data=np.zeros((image.height,stride),dtype=np.uint8);data[:,:image.width*3]=a.reshape(image.height,-1)
  b=Gst.Buffer.new_wrapped(data.tobytes());b.pts=self.index*self.step;b.duration=self.step;self.index+=1
  if self.source.emit('push-buffer',b)!=Gst.FlowReturn.OK:raise RuntimeError('视频编码失败')
 def close(self):
  self.source.emit('end-of-stream');msg=self.pipe.get_bus().timed_pop_filtered(20*Gst.SECOND,Gst.MessageType.EOS|Gst.MessageType.ERROR);self.pipe.set_state(Gst.State.NULL)
  if not msg or msg.type==Gst.MessageType.ERROR:raise RuntimeError('视频文件收尾失败')

# Local FFmpeg fallback for formats without an installed GStreamer decoder.
GstVideoReader=VideoReader
class VideoReader(GstVideoReader):
 def __init__(self,path):
  self.ff=None
  if Path(path).suffix.lower() not in ['.mp4','.mov','.mkv','.webm'] or not (BASE/'tools/ffmpeg').is_file():super().__init__(path);return
  import subprocess
  data=json.loads(subprocess.check_output([str(BASE/'tools/ffprobe'),'-v','error','-select_streams','v:0','-show_entries','stream=width,height,avg_frame_rate','-of','json',str(path)],timeout=20))['streams'][0]
  self.width,self.height=data['width'],data['height'];num,den=map(int,data['avg_frame_rate'].split('/'));self.fps=num/den if num and den else 25;self.pipe=None
  self.log=open(BASE/'decode.log','ab');self.ff=subprocess.Popen([str(BASE/'tools/ffmpeg'),'-nostdin','-v','error','-threads','2','-i',str(path),'-an','-f','rawvideo','-pix_fmt','rgb24','pipe:1'],stdout=subprocess.PIPE,stderr=self.log)
 def frames(self,stop):
  if self.ff is None:yield from super().frames(stop);return
  count=0;size=self.width*self.height*3
  try:
   while not stop.is_set():
    data=bytearray()
    while len(data)<size:
     chunk=self.ff.stdout.read(size-len(data))
     if not chunk:break
     data.extend(chunk)
    if not data:break
    if len(data)!=size:raise RuntimeError('视频帧不完整')
    yield Image.frombytes('RGB',(self.width,self.height),bytes(data)),count/self.fps;count+=1
   if not stop.is_set() and self.ff.wait(timeout=10):raise RuntimeError('视频解码失败，见 decode.log')
  finally:
   if self.ff.poll() is None:self.ff.terminate()
   try:self.ff.wait(timeout=5)
   except Exception:self.ff.kill();self.ff.wait()
   self.ff.stdout.close();self.log.close()

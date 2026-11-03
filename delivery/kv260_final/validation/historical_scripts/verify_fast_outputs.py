from engine import *
import itertools
m=json.loads((BASE/'fast_ui_validation.json').read_text());folder=BASE/'results'/m['processing']['id'];readers=[VideoReader('/home/ubuntu/Videos/展示视频_雨夜交通_增强.avi'),VideoReader(folder/'annotated.avi')];count=0
for (a,ta),(b,tb) in itertools.zip_longest(*(r.frames(threading.Event()) for r in readers),fillvalue=(None,None)):
 assert a is not None and b is not None;assert a.tobytes()==b.tobytes(),count;count+=1
assert count==192;print('ALL_192_FRAMES_PIXEL_MATCH',flush=True)
e=Engine();im=Image.open(BASE/'smoke_result.png').convert('RGB');before=json.loads((BASE/'smoke_image.json').read_text())['detections'];start=time.perf_counter();rows,ms=e.detect(im,['pedestrian','vehicle'],.25);first=time.perf_counter()-start;assert len(rows)==len(before)
for a,b in zip(rows,before):assert a['class']==b['class'] and abs(a['score']-b['score'])<1e-5
warm=[]
for _ in range(3):
 start=time.perf_counter();e.detect(im,['pedestrian','vehicle'],.25);warm.append(time.perf_counter()-start)
(BASE/'fast_output_validation.json').write_text(json.dumps({'video_exact_frames':count,'detector_scores_match':True,'detector_first_seconds':first,'detector_warm_seconds':warm},indent=2));print('DETECTOR_PASS',first,warm,flush=True)

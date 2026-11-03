import fcntl,json,os,time,threading
from pathlib import Path

def run_session(fd,package,root,Status,record,save):
    sensor=Path('/sys/class/hwmon/hwmon2/power1_input')
    power=[];stop=threading.Event()
    def sample_power():
        while not stop.is_set():
            power.append({'t_ns':time.perf_counter_ns(),'power_uW':int(sensor.read_text())})
            stop.wait(.05)
    worker=threading.Thread(target=sample_power,daemon=True);worker.start()
    idle_begin=time.perf_counter_ns();time.sleep(5);idle_end=time.perf_counter_ns()
    record['power_sensor']={'name':'ina260_u14','path':str(sensor),'unit':'uW','idle_begin_ns':idle_begin,'idle_end_ns':idle_end}
    names=('golden/original.i16','golden/d_input.i16','golden/cnn_input.i16','model/weights_int8.bin','model/bias_int32.bin','model/weight_frac.bin','model/tanh_lut_q15.bin','golden/fused.i16','golden/rgb.u8')
    for n in names:
        view=memoryview((package/n).read_bytes())
        while view:
            count=os.write(fd,view)
            if count<=0:raise RuntimeError('Short upload')
            view=view[count:]
    params=Path('/sys/module/kv260_joint_once/parameters')
    cases=[('core_audit',0,1,30),('ps_rgb_audit',1,1,30),('hw_prepare_audit',2,1,30)]
    cases += [('core_perf_'+str(i+1),0,0,120) for i in range(3)]
    cases += [('ps_rgb_perf_'+str(i+1),1,0,120) for i in range(3)]
    cases += [('hw_prepare_perf_'+str(i+1),2,0,120) for i in range(3)]
    cases += [('hw_prepare_long',2,0,600)]
    cases += [('hw_prepare_latency_'+str(i+1),2,0,1) for i in range(30)]
    results=[]
    record['phase']='RUNNING_FPS_SUITE';save()
    for index,(name,mode,all_check,frames) in enumerate(cases):
        if index:fcntl.ioctl(fd,0x47e3)
        for key,value in (('bench_frames',frames),('ps_mode',mode),('verify_all',all_check),('cache_poison',all_check)):(params/key).write_text(str(value))
        print('FPS_CASE_BEGIN '+name,flush=True)
        begin=time.perf_counter_ns();error=None
        try:fcntl.ioctl(fd,0x47e1)
        except OSError as e:error=repr(e)
        wall=time.perf_counter_ns()-begin
        raw=bytearray(736);fcntl.ioctl(fd,0x82e047e0,raw,True);s=Status.from_buffer_copy(raw)
        row=dict(name=name,frames=frames,ps_preprocess=mode==1,prepare_mode=mode,rgb_output_consumed=bool(mode),slots=6,cache_poison=bool(all_check),golden_check='all frames' if all_check else 'first and last frame',batch_ns=s.elapsed_ns,ioctl_wall_ns=wall,batch_fps=frames*1e9/s.elapsed_ns if s.elapsed_ns else None,call_fps=frames*1e9/wall,status={n:list(getattr(s,n)) if n=='dma' else getattr(s,n) for n,_ in Status._fields_})
        if error:row['error']=error
        results.append(row);record['cases']=results;save()
        row.update(begin_ns=begin,end_ns=begin+wall)
        (root/'power_samples.json').write_text(json.dumps(power))
        if error or s.pending or s.error or not s.completed or s.reserved!=frames or not s.guards_ok:raise RuntimeError('FPS case failed; no retry: '+name)
        print('FPS_CASE_PASS '+name+' FPS='+str(round(row['batch_fps'],3)),flush=True)
    record.update(phase='PASS',frames=sum(x[3] for x in cases),ip_starts=sum(x[3]*(6 if x[1]==2 else 5) for x in cases),models_uploaded_once=True,dma_reused=all(row['status']['dma']==results[0]['status']['dma'] for row in results),hardware_build='c6496c6dc89aa54c4500',scope='same decoded RGB frame replay; PS cases include per-frame integer prepare, DMA input copy, five-core cross-frame scheduling, full Q14 readback, RGB conversion and CRC consumption; excludes compressed decode, display, disk recording, bitstream loading and buffer allocation')
    stop.set();worker.join();power.append({'t_ns':time.perf_counter_ns(),'power_uW':int(sensor.read_text())});(root/'power_samples.json').write_text(json.dumps(power))
    save();print('FPS_SUITE_PASS',flush=True)

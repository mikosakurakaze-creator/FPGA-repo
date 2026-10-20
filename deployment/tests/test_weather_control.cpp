#include "weather_control.h"
#include "weather_frame.h"
#include "weather_kernel.h"
#include <algorithm>
#include <iostream>
#include <stdexcept>
#include <string>
#include <vector>
#include <string.h>

static void check(bool ok,const char* what) { if(!ok) throw std::runtime_error(what); }
struct Mock {
    uint32_t regs[32];
    weather_buffer b[3];
    std::vector<std::string> events;
    weather_abi abi;
    int task,starts,polls,done_after,fail_reg,fail_read,fail_sync;
    bool running,done,stall,execute,reset_fail,auto_restart,frozen_clock;
    unsigned owned;
    uint64_t time;
    Mock(weather_abi a,int t):abi(a),task(t),starts(0),polls(0),done_after(2),fail_reg(-1),fail_read(-1),fail_sync(-1),
        running(false),done(false),stall(false),execute(false),reset_fail(false),auto_restart(false),frozen_clock(false),owned(0),time(0) {
        memset(regs,0,sizeof(regs));memset(b,0,sizeof(b));
    }
    uint64_t ptr(int off) { return uint64_t(regs[off/4]) | (uint64_t(regs[off/4+1])<<32); }
    void calculate() {
        check(ptr(0x18)==b[0].device_address && ptr(0x24)==b[1].device_address,"64-bit pointer programming");
        int h=int(regs[(abi==WEATHER_TILE_V1?0x3c:0x30)/4]);
        int w=int(regs[(abi==WEATHER_TILE_V1?0x44:0x38)/4]);
        if(abi==WEATHER_TILE_V1) check(ptr(0x30)==b[2].device_address,"scratch pointer");
        if(!execute) return;
        int16_t* in=static_cast<int16_t*>(b[0].cpu),*out=static_cast<int16_t*>(b[1].cpu),*scratch=static_cast<int16_t*>(b[2].cpu);
        regs[0x10/4] = abi==WEATHER_FRAME_V2 ? weather_frame_top(in,out,h,w,int(regs[0x40/4])) :
            task==0 ? derain_top(in,out,scratch,h,w) : dehaze_top(in,out,scratch,h,w);
    }
    static int read(void* u,uint32_t off,uint32_t* v) {
        Mock& m=*static_cast<Mock*>(u);
        if(int(off)==m.fail_read) return 1;
        if(off==0) {
            if(m.running && !m.stall && ++m.polls>=m.done_after) { m.calculate();m.running=false;m.done=true; }
            *v=(m.running?0U:4U)|(m.done?2U:0U)|(m.auto_restart?128U:0U);m.done=false;
        } else *v=m.regs[off/4];
        return 0;
    }
    static int write(void* u,uint32_t off,uint32_t value) {
        Mock& m=*static_cast<Mock*>(u);
        m.events.push_back("write:"+std::to_string(off));
        if(off==0) {
            check(value==1,"auto-restart or control value");
            check(m.owned==(m.abi==WEATHER_TILE_V1?7U:3U),"start without DMA ownership");
            ++m.starts;m.running=true;m.done=false;m.polls=0;
        }
        if(int(off)==m.fail_reg) return 1;
        m.regs[off/4]=value;return 0;
    }
    static int sync(void* u,const weather_buffer* b,size_t bytes,weather_direction dir,weather_owner owner) {
        Mock& m=*static_cast<Mock*>(u); int i=0;
        while(i<3 && b->device_address!=m.b[i].device_address)++i;
        check(i<3 && bytes<=b->bytes,"sync buffer/capacity");
        check(dir==(i==0?WEATHER_DEVICE_READ:i==1 && m.abi==WEATHER_FRAME_V2?WEATHER_DEVICE_WRITE:WEATHER_DEVICE_RW),"DMA direction");
        m.events.push_back(std::string(owner==WEATHER_DEVICE?"device:":"cpu:")+std::to_string(i));
        if(int(i)+(owner==WEATHER_CPU?10:0)==m.fail_sync) return 1;
        if(owner==WEATHER_DEVICE) { check(!(m.owned&(1U<<i)),"duplicate device acquire");m.owned|=1U<<i; }
        else { check(!m.running,"release while hardware running");check(m.owned&(1U<<i),"release without ownership");m.owned&=~(1U<<i); }
        return 0;
    }
    static void barrier(void* u) { static_cast<Mock*>(u)->events.push_back("barrier"); }
    static uint64_t now(void* u) { Mock& m=*static_cast<Mock*>(u);if(!m.frozen_clock)m.time+=5;return m.time; }
    static void poll(void*) {}
    static int reset(void* u) {
        Mock& m=*static_cast<Mock*>(u);m.events.push_back("reset_and_drain");
        if(m.reset_fail)return 1;
        m.running=false;m.done=false;m.stall=false;m.auto_restart=false;return 0;
    }
    weather_platform platform() {
        weather_platform p={this,read,write,sync,barrier,now,poll,reset};return p;
    }
};
struct Fixture {
    Mock m;
    std::vector<int16_t> input,output,scratch;
    weather_device device;
    weather_job job;
    Fixture(weather_abi abi,int task):m(abi,task),input(3*140*140),output(3*140*140),scratch(24*140*140) {
        weather_buffer a={input.data(),UINT64_C(0x123400000000),input.size()*2};
        weather_buffer b={output.data(),UINT64_C(0x123410000000),output.size()*2};
        weather_buffer c={scratch.data(),UINT64_C(0x123420000000),scratch.size()*2};
        m.b[0]=a;m.b[1]=b;m.b[2]=c;
        weather_job j={a,b,abi==WEATHER_TILE_V1?c:weather_buffer{0,0,0},7,11,task};job=j;
        weather_platform p=m.platform();
        check(weather_device_init(&device,&p,abi,abi==WEATHER_TILE_V1?task:-1)==0,"init");
    }
};
static int run(Fixture& f) { return weather_run(&f.device,&f.job,1000,100,0); }
static void control_tests() {
    for(weather_abi abi : {WEATHER_TILE_V1,WEATHER_FRAME_V2}) {
        Fixture f(abi,0);f.m.done=true; // stale completion must not complete the new job
        check(run(f)==0 && f.m.starts==1 && f.m.polls==2 && !f.m.owned,"normal/stale done");
        check(f.m.events.front()=="device:0","cache acquire order");
        for(int i=0;i<3;++i) check(run(f)==0,"consecutive driver call");
        f.m.regs[0x10/4]=3;uint32_t status=0;
        check(weather_run(&f.device,&f.job,1000,100,&status)==WEATHER_ECORE && status==3 && !f.m.owned,"core failure/release");
    }
    {
        Fixture f(WEATHER_TILE_V1,0);f.job.task=1;check(run(f)==WEATHER_EINVAL && !f.m.starts,"fixed-task mismatch");
        f.job.task=0;f.job.height=141;check(run(f)==WEATHER_EINVAL,"oversized tile");
    }
    {
        Fixture f(WEATHER_FRAME_V2,0);f.job.scratch=f.m.b[2];check(run(f)==WEATHER_EINVAL,"v1 scratch passed to v2");
    }
    for(int bad=0;bad<5;++bad) {
        Fixture f(WEATHER_TILE_V1,0);
        if(bad==0)f.job.output.device_address=f.job.input.device_address;
        if(bad==1)f.job.output.cpu=f.job.input.cpu;
        if(bad==2)f.job.scratch.bytes=1;
        if(bad==3)f.job.input.device_address|=1;
        if(bad==4)f.job.input.device_address=UINT64_MAX-1;
        check(run(f)==WEATHER_EINVAL && f.m.events.empty(),"invalid memory must not reach hardware");
    }
    for(int kind=0;kind<2;++kind) {
        Fixture f(WEATHER_TILE_V1,0);f.m.running=kind==0;f.m.stall=true;f.m.auto_restart=kind==1;
        check(run(f)==WEATHER_EBUSY && f.m.events.empty(),"busy/auto-restart");
    }
    {
        Fixture f(WEATHER_TILE_V1,0);f.m.fail_sync=1;
        check(run(f)==WEATHER_EIO && !f.m.owned && !f.device.owned_mask && !f.m.starts,"failed acquire rollback");
    }
    {
        Fixture f(WEATHER_TILE_V1,0);f.m.fail_reg=0x24;
        check(run(f)==WEATHER_EIO && !f.m.owned && !f.m.starts,"MMIO programming rollback");
    }
    for(int frozen=0;frozen<2;++frozen) {
        Fixture f(WEATHER_TILE_V1,0);f.m.stall=true;f.m.frozen_clock=frozen;
        check(weather_run(&f.device,&f.job,12,5,0)==WEATHER_ETIMEOUT && f.m.owned==7 && f.device.quarantined,"timeout quarantine");
        check(run(f)==WEATHER_EQUARANTINED && f.m.starts==1,"timeout buffer reuse");
        f.m.reset_fail=true;check(weather_recover(&f.device)==WEATHER_EQUARANTINED && f.m.owned==7,"failed drain must retain buffers");
        f.m.reset_fail=false;check(weather_recover(&f.device)==0 && !f.m.owned,"reset/drain release");
        check(run(f)==0,"post-recovery call");
    }
    {
        Fixture f(WEATHER_TILE_V1,0);f.m.fail_reg=0;
        check(run(f)==WEATHER_EQUARANTINED && f.m.running && f.m.owned==7,"uncertain start quarantine");
        f.m.fail_reg=-1;check(weather_recover(&f.device)==0,"uncertain start recovery");
    }
    {
        Fixture f(WEATHER_TILE_V1,0);f.m.fail_sync=11;
        check(run(f)==WEATHER_EQUARANTINED && f.m.owned==2,"CPU sync failure retention");
        f.m.fail_sync=-1;check(weather_recover(&f.device)==0 && !f.m.owned,"CPU sync recovery");
    }
    std::cout << "CONTROL_STATE_MACHINE_PASS\n";
}
static void tiled_tests() {
    for(int task=0;task<2;++task) for(int core : {64,128}) {
        Fixture f(WEATHER_TILE_V1,task);f.m.execute=true;
        const int h=145,w=149;
        std::vector<int16_t> input(3*h*w),expected(input.size()),output(input.size()+16,-12345);
        for(size_t i=0;i<input.size();++i)input[i]=int16_t((i*157+task*3451)%16385);
        check(weather_frame_top(input.data(),expected.data(),h,w,task)==0,"frame reference");
        uint32_t completed=0;
        check(weather_run_tiled(&f.device,input.data(),input.size(),output.data()+8,input.size(),h,w,core,&f.job,1000,100,&completed)==0,"tile driver");
        check(completed==uint32_t(((h+core-1)/core)*((w+core-1)/core)),"tile completion count");
        check(std::equal(expected.begin(),expected.end(),output.begin()+8),"gather/IP/scatter mismatch");
        for(int i=0;i<8;++i)check(output[i]==-12345 && output[output.size()-1-i]==-12345,"scatter guard");
        check(weather_run_tiled(&f.device,input.data(),input.size(),input.data(),input.size(),h,w,core,&f.job,1000,100,&completed)==WEATHER_EINVAL,"overlapping frames");
        std::fill(f.input.begin(),f.input.end(),-4321);f.m.stall=true;f.m.running=true;
        check(weather_run_tiled(&f.device,input.data(),input.size(),output.data()+8,input.size(),h,w,core,&f.job,1000,100,&completed)==WEATHER_EBUSY && f.input[0]==-4321,"busy IP input clobber");
        f.m.running=false;
        check(weather_run_tiled(&f.device,input.data(),input.size(),output.data()+8,input.size(),h,w,core,&f.job,12,5,&completed)==WEATHER_ETIMEOUT && completed==0,"tile timeout propagation");
        check(weather_recover(&f.device)==0,"tile timeout recovery");
        std::cout << "TILED_DRIVER_EXACT task=" << task << " core=" << core << "\n";
    }
    {
        Fixture f(WEATHER_FRAME_V2,0);f.m.execute=true;
        for(int task : {0,1,0}) {
            f.job.task=task;
            for(size_t i=0;i<231;++i)f.input[i]=int16_t((i*13+task)%16385);
            check(run(f)==0,"v2 driver task switch");
            std::vector<int16_t> expected(231);
            check(weather_frame_top(f.input.data(),expected.data(),7,11,task)==0,"v2 reference");
            check(std::equal(expected.begin(),expected.end(),f.output.begin()),"v2 driver output");
        }
    }
    std::cout << "MOCK_INTEGRATION_PASS\n";
}
int main() {
    try { control_tests();tiled_tests();std::cout << "DRIVER_HOST_SUITE_PASS\n";return 0; }
    catch(const std::exception& e) { std::cerr << e.what() << "\n";return 1; }
}

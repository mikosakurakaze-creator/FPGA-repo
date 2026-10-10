/* Ordinary AArch64 Linux process. Only clock/sysfs/uname reads; no MMIO/DMA/go. */
#define _POSIX_C_SOURCE 200809L
#include <stdio.h>
#include <stdint.h>
#include <string.h>
#include <time.h>
#include <sys/utsname.h>

static int raw(uint64_t *v) {
    struct timespec ts;
    if (clock_gettime(CLOCK_MONOTONIC_RAW,&ts)) return -1;
    *v=(uint64_t)ts.tv_sec*1000000000ULL+(uint64_t)ts.tv_nsec;
    return 0;
}
int main(void) {
    struct utsname u;
    struct timespec resolution;
    char source[128]; uint64_t before,after,min=UINT64_MAX,max=0;
    if (uname(&u) || strcmp(u.machine,"aarch64")) return 2;
    FILE *f=fopen("/sys/devices/system/clocksource/clocksource0/current_clocksource","r");
    if (!f) return 3;
    int ok=fgets(source,sizeof(source),f)!=NULL;fclose(f);
    if (!ok) return 4;
    source[strcspn(source,"\r\n")]=0;
    if (strcmp(source,"arch_sys_counter")) return 5;
    if (clock_getres(CLOCK_MONOTONIC_RAW,&resolution) || resolution.tv_sec || resolution.tv_nsec>1000) return 6;
    for (unsigned i=0;i<1000;i++) {
        if (raw(&before) || raw(&after) || after<before) return 7;
        uint64_t d=after-before;
        if (d<min) min=d;
        if (d>max) max=d;
    }
    /* uname fields are printed as plain text: not an unescaped JSON document. */
    printf("HOST_BUILT_BOARD_CLOCK_PROBE\nKernel=%s\nMachine=%s\nClocksource=%s\n"
           "Clock=CLOCK_MONOTONIC_RAW\nResolution_ns=%ld\nRead_pair_min_ns=%llu\n"
           "Read_pair_max_ns=%llu\nBOARD_30FPS=NOT_TESTED\n"
           "Physical_counter_frequency=REQUIRES_MATCHED_KERNEL_DT_TIMER_EVIDENCE\n",
           u.release,u.machine,source,resolution.tv_nsec,
           (unsigned long long)min,(unsigned long long)max);
    return 0;
}

/* Explicitly launched DDR smoke test. Does not program PL, clocks, or PMU. */
#include "weather_xilinx_standalone.h"
#include "weather_smoke_vectors.h"
#include "xil_printf.h"
#include <string.h>

#define FRAME_ELEMENTS (3U * 720U * 1280U)
static int16_t frame_input[FRAME_ELEMENTS] __attribute__((aligned(64)));
static int16_t frame_output[FRAME_ELEMENTS] __attribute__((aligned(64)));
static struct weather_device device;
static struct weather_xilinx_context context = {0xA0030000ULL};

static void stop_forever(void) {
    for (;;) __asm__ volatile("wfe");
}
int main(void) {
    struct weather_platform platform;
    struct weather_job job;
    unsigned sequence, i;
    uint32_t core_status;
    if (weather_xilinx_platform(&platform, &context) ||
        weather_device_init(&device, &platform, WEATHER_FRAME_V2, -1)) return 1;
    xil_printf("WEATHER_SMOKE_BEGIN ABI=2 BASE=A0030000 CACHE=EXPLICIT_SYNC\r\n");
    memset(&job, 0, sizeof(job));
    job.input = (struct weather_buffer){frame_input, (uintptr_t)frame_input, sizeof(frame_input)};
    job.output = (struct weather_buffer){frame_output, (uintptr_t)frame_output, sizeof(frame_output)};
    job.height = 8; job.width = 8;
    /* Alternate both fixed models on one synthesized core without reset. */
    for (sequence = 0; sequence < 3; ++sequence) {
        const unsigned task = sequence & 1U;
        const int16_t* input = task ? dehaze_input : derain_input;
        const int16_t* expected = task ? dehaze_output : derain_output;
        uint64_t begin, elapsed;
        job.task = (int)task;
        memcpy(frame_input, input, 192U * sizeof(int16_t));
        for (i = 0; i < FRAME_ELEMENTS; ++i) frame_output[i] = 0x2468;
        /* Commit all guard lines to DDR before testing out-of-range PL writes. */
        if (platform.sync(platform.user, &job.output, sizeof(frame_output),
                          WEATHER_DEVICE_WRITE, WEATHER_DEVICE)) stop_forever();
        begin = platform.now_us(platform.user);
        int status = weather_run(&device, &job, 30000000ULL, 100000000U, &core_status);
        elapsed = platform.now_us(platform.user) - begin;
        if (status != WEATHER_OK) {
            xil_printf("WEATHER_SMOKE_FAIL sequence=%u status=%d quarantine=%d\r\n",
                       sequence, status, device.quarantined);
            stop_forever(); /* Never reuse any possibly device-owned buffer. */
        }
        for (i = 0; i < 192; ++i) {
            if (frame_output[i] != expected[i] || frame_input[i] != input[i]) {
                xil_printf("WEATHER_SMOKE_FAIL sequence=%u index=%u\r\n", sequence, i);
                stop_forever();
            }
        }
        /* Sync the guard separately: only the active output was invalidated. */
        if (platform.sync(platform.user, &job.output, sizeof(frame_output),
                          WEATHER_DEVICE_WRITE, WEATHER_CPU)) stop_forever();
        for (i = 192; i < FRAME_ELEMENTS; ++i)
            if (frame_output[i] != 0x2468) {
                xil_printf("WEATHER_GUARD_FAIL index=%u\r\n", i);
                stop_forever();
            }
        xil_printf("WEATHER_FRAME_PASS sequence=%u task=%u elapsed_us=%u\r\n",
                   sequence, task, (unsigned)elapsed);
    }
    xil_printf("WEATHER_SMOKE_PASS frames=3 tasks=0,1,0\r\n");
    stop_forever();
    return 0;
}

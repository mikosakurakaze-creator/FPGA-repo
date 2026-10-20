#ifndef WEATHER_B_CONTROL_H
#define WEATHER_B_CONTROL_H
#include <stddef.h>
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif

enum weather_abi { WEATHER_TILE_V1 = 1, WEATHER_FRAME_V2 = 2 };
enum weather_direction { WEATHER_DEVICE_READ = 1, WEATHER_DEVICE_WRITE = 2, WEATHER_DEVICE_RW = 3 };
enum weather_owner { WEATHER_CPU = 0, WEATHER_DEVICE = 1 };
enum weather_status {
    WEATHER_OK = 0, WEATHER_EINVAL = -1, WEATHER_EBUSY = -2,
    WEATHER_EIO = -3, WEATHER_ETIMEOUT = -4, WEATHER_ECORE = -5,
    WEATHER_EQUARANTINED = -6
};
struct weather_buffer { void* cpu; uint64_t device_address; size_t bytes; };
struct weather_job {
    struct weather_buffer input, output, scratch;
    int height, width, task; /* task 0 derain, 1 dehaze */
};
/* Platform owns MMIO/DMA implementation. Return 0 on success from int hooks.
 * sync must perform the platform DMA ownership/cache operation, including
 * release to CPU after device READ. It must not throw or partially fail.
 * Buffers must use independent cache-line-aligned DMA allocations; adjacent
 * 16-bit regions of one cache line are not valid independent DMA buffers.
 * read32/write32 take IP-relative offsets, not virtual/physical base addresses.
 * reset_and_quiesce must stop the master AND drain outstanding DDR transactions.
 */
struct weather_platform {
    void* user;
    int (*read32)(void*, uint32_t offset, uint32_t* value);
    int (*write32)(void*, uint32_t offset, uint32_t value);
    int (*sync)(void*, const struct weather_buffer*, size_t active_bytes,
                enum weather_direction, enum weather_owner);
    void (*barrier)(void*);
    uint64_t (*now_us)(void*);
    void (*poll)(void*); /* optional yield; now_us must be monotonic */
    int (*reset_and_quiesce)(void*); /* optional; required to recover quarantine */
};
struct weather_device {
    struct weather_platform platform;
    enum weather_abi abi;
    int fixed_task; /* v1 IP identity; v2 must use -1 */
    int quarantined;
    unsigned owned_mask;
    struct weather_buffer held[3];
    size_t active_bytes[3];
    enum weather_direction directions[3];
};
/* Exclusive caller: no concurrent MMIO, auto-restart, interrupt-driven driver,
 * or second thread on this device. This object is not a lock.
 */
int weather_device_init(struct weather_device*, const struct weather_platform*,
                        enum weather_abi, int fixed_task);
int weather_run(struct weather_device*, const struct weather_job*,
                uint64_t timeout_us, uint32_t max_polls, uint32_t* core_return);
/* Timeout/uncertain start keeps device ownership. Never free/reuse held buffers
 * until recovery succeeds, or until platform shutdown proves DMA is quiescent.
 */
int weather_recover(struct weather_device*);

/* CPU gather/scatter correctness path for an A-group v1 IP. Full-frame memory
 * is CPU-owned; workspace has three independent max-140x140 DMA allocations.
 * Only a successful return makes the entire output frame valid. On failure it
 * can be partially written. max_polls/timeout apply to each tile, not the frame.
 */
int weather_run_tiled(struct weather_device*, const int16_t* input, size_t input_elements,
                      int16_t* output, size_t output_elements, int height, int width,
                      int core, struct weather_job* workspace,
                      uint64_t timeout_us, uint32_t max_polls, uint32_t* completed_tiles);
#ifdef __cplusplus
}
#endif
#endif

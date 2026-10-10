#ifndef KV_NATIVE_HOTPATH_H
#define KV_NATIVE_HOTPATH_H
#include <stdint.h>

#if defined(_WIN32)
#define KV_HP_API __declspec(dllexport)
#else
#define KV_HP_API __attribute__((visibility("default")))
#endif

/* Ordinary process pointers, never physical/DMA/MMIO addresses. 64-bit ABI. */
typedef struct {
    void *base;
    uint64_t allocation_bytes, payload_offset, payload_bytes;
} kv_hp_span;

enum {
    KV_HP_OK = 0, KV_HP_ARG = 1, KV_HP_BOUNDS = 2, KV_HP_ALIGN = 3,
    KV_HP_ALIAS = 4, KV_HP_POISON_IN_GOLDEN = 5,
    KV_HP_MISMATCH = 6, KV_HP_GUARD = 7,
    KV_HP_IMMUTABLE_COUNT = 14, KV_HP_OUTPUT_COUNT = 3,
    KV_HP_INPUT_COUNT = 2, KV_HP_GUARD_BYTES = 64
};

/* Fixed immutable order: weights,bias,frac,LUT; A low/full; B low/full;
 * A low/full/enhanced Golden; B low/full/enhanced Golden. No SHA field.
 */
typedef struct {
    uint32_t abi_version, status;
    uint64_t full_output_poison_bytes, input_copy_bytes;
    uint64_t compared_scalars, mismatches, slot_guard_bytes, guard_errors;
    uint64_t poison_checked_scalars, poison_occurrences;
    uint32_t first_bad_span, first_guard_side; /* guard side: 0=front, 1=rear */
    uint64_t first_bad_scalar, first_bad_guard_byte;
    int32_t observed_int16, expected_int16;
} kv_hp_receipt;

/* Span/descriptor/receipt memory must really be accessible and remain pinned
 * by the caller. Integer bounds are checked; OS mapping/lifetime are not.
 * No output write occurs before all bounds/alias validation succeeds.
 * Argument/bounds/alias errors return WITHOUT writing the receipt. Receipts
 * are emitted only after all descriptors and metadata are proved disjoint.
 */
KV_HP_API int kv_hp_validate_poison(const kv_hp_span immutable[14],
                                  int16_t poison, kv_hp_receipt *receipt);
KV_HP_API int kv_hp_prepare(const kv_hp_span outputs[3],
                           const kv_hp_span active_inputs[2],
                           const kv_hp_span immutable[14], uint32_t kind,
                           uint32_t copy_input, int16_t poison,
                           kv_hp_receipt *receipt);
KV_HP_API int kv_hp_verify(const kv_hp_span outputs[3],
                          const kv_hp_span immutable[14], uint32_t kind,
                          uint8_t expected_guard_byte, kv_hp_receipt *receipt);
#endif

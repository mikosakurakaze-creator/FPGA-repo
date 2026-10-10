#include "hotpath.h"
#include <stddef.h>
#include <string.h>
#include <limits.h>

_Static_assert(sizeof(void *) == 8, "64-bit process ABI required");
_Static_assert(sizeof(kv_hp_span) == 32, "span ABI drift");
_Static_assert(sizeof(kv_hp_receipt) == 104, "receipt ABI drift");
_Static_assert(CHAR_BIT == 8, "byte ABI drift");
#if defined(__BYTE_ORDER__) && __BYTE_ORDER__ != __ORDER_LITTLE_ENDIAN__
#error "Frozen Q14 bytes require a little-endian process"
#endif

typedef struct { uintptr_t begin, end, payload; uint64_t bytes; } region;
static const uint64_t immutable_bytes[14] = {
    10075,1944,486,8194,38160,5495040,38160,5495040,
    38160,5495040,5495040,38160,5495040,5495040
};
static const uint64_t output_bytes[3] = {38160,5495040,5495040};
static const uint64_t input_bytes[2] = {38160,5495040};

static kv_hp_receipt empty_receipt(void) {
    kv_hp_receipt r;
    memset(&r,0,sizeof(r)); r.abi_version=1;
    r.first_bad_span=UINT32_MAX; r.first_guard_side=UINT32_MAX;
    r.first_bad_scalar=UINT64_MAX; r.first_bad_guard_byte=UINT64_MAX;
    return r;
}
static int memory_range(const void *p, uint64_t size, region *r) {
    uintptr_t a=(uintptr_t)p;
    if (!p || !size || size>UINTPTR_MAX-a) return KV_HP_BOUNDS;
    r->begin=a; r->end=a+(uintptr_t)size; r->payload=a; r->bytes=size;
    return KV_HP_OK;
}
static int overlap(region a, region b) {
    return a.begin<b.end && b.begin<a.end;
}
static int span_region(kv_hp_span s, uint64_t expected, int guards,
                       int int16_aligned, region *r) {
    region allocation; int rc;
    if (s.payload_bytes!=expected) return KV_HP_ARG;
    rc=memory_range(s.base,s.allocation_bytes,&allocation);
    if (rc) return rc;
    if (s.payload_offset>s.allocation_bytes ||
        s.payload_bytes>s.allocation_bytes-s.payload_offset) return KV_HP_BOUNDS;
    if (guards && (s.payload_offset<KV_HP_GUARD_BYTES ||
        s.allocation_bytes-s.payload_offset-s.payload_bytes<KV_HP_GUARD_BYTES))
        return KV_HP_BOUNDS;
    r->payload=allocation.begin+(uintptr_t)s.payload_offset;
    if (int16_aligned && (r->payload & 1u)) return KV_HP_ALIGN;
    r->begin=r->payload-(guards?KV_HP_GUARD_BYTES:0u);
    r->end=r->payload+(uintptr_t)s.payload_bytes+(guards?KV_HP_GUARD_BYTES:0u);
    r->bytes=s.payload_bytes;
    return KV_HP_OK;
}
static int separated(const region *a, size_t n) {
    for (size_t i=0;i<n;i++) for (size_t j=i+1;j<n;j++)
        if (overlap(a[i],a[j])) return KV_HP_ALIAS;
    return KV_HP_OK;
}
/* Metadata/report must not overlap payload/guards or immutable memory.
 * All descriptors are copied before mutations; callers keep them stable.
 */
static int metadata_safe(region metadata, const region *data, size_t count) {
    for (size_t i=0;i<count;i++) if (overlap(metadata,data[i])) return KV_HP_ALIAS;
    return KV_HP_OK;
}
static int finish(kv_hp_receipt *dst, kv_hp_receipt r, int rc) {
    r.status=(uint32_t)rc; memcpy(dst,&r,sizeof(r)); return rc;
}
static int immutable_regions(const kv_hp_span *p, region r[14]) {
    for (size_t i=0;i<14;i++) {
        int rc=span_region(p[i],immutable_bytes[i],0,i>=4,&r[i]);
        if (rc) return rc;
        /* Protect immutable allocation padding/guards as well as its payload. */
        r[i].begin=(uintptr_t)p[i].base;
        r[i].end=r[i].begin+(uintptr_t)p[i].allocation_bytes;
    }
    return separated(r,14);
}
static int descriptor_and_receipt_ranges(const void *descriptor, size_t bytes,
                                         kv_hp_receipt *receipt, region *d, region *rr) {
    int rc=memory_range(receipt,sizeof(*receipt),rr);
    if (rc) return rc;
    rc=memory_range(descriptor,bytes,d);
    if (rc) return rc;
    return overlap(*d,*rr)?KV_HP_ALIAS:KV_HP_OK;
}

int kv_hp_validate_poison(const kv_hp_span immutable[14], int16_t poison,
                          kv_hp_receipt *receipt) {
    region data[14],descriptor,rr; kv_hp_span local[14];
    kv_hp_receipt r=empty_receipt(); int rc;
    rc=descriptor_and_receipt_ranges(immutable,sizeof(local),receipt,&descriptor,&rr);
    if (rc) return rc;
    memcpy(local,immutable,sizeof(local));
    rc=immutable_regions(local,data);
    if (rc) return rc;
    if (metadata_safe(rr,data,14) || metadata_safe(descriptor,data,14)) return KV_HP_ALIAS;
    for (uint32_t i=8;i<14;i++) {
        const int16_t *p=(const int16_t *)data[i].payload;
        for (uint64_t k=0;k<data[i].bytes/2;k++) {
            r.poison_checked_scalars++;
            if (p[k]==poison) {
                r.poison_occurrences=1; r.first_bad_span=i; r.first_bad_scalar=k;
                r.observed_int16=p[k]; r.expected_int16=poison;
                return finish(receipt,r,KV_HP_POISON_IN_GOLDEN);
            }
        }
    }
    return finish(receipt,r,KV_HP_OK);
}

int kv_hp_prepare(const kv_hp_span outputs[3], const kv_hp_span active_inputs[2],
                   const kv_hp_span immutable[14], uint32_t kind,
                   uint32_t copy_input, int16_t poison, kv_hp_receipt *receipt) {
    region data[19],out_descriptor,in_descriptor,imm_descriptor,rr;
    kv_hp_span out[3],active[2],imm[14]; kv_hp_receipt r=empty_receipt();
    size_t n=17; int rc;
    rc=descriptor_and_receipt_ranges(immutable,sizeof(imm),receipt,&imm_descriptor,&rr);
    if (rc) return rc;
    if (!outputs || kind>1 || copy_input>1 || (copy_input && !active_inputs))
        return KV_HP_ARG;
    rc=memory_range(outputs,sizeof(out),&out_descriptor);
    if (rc) return rc;
    if (overlap(out_descriptor,rr)) return KV_HP_ALIAS;
    memcpy(out,outputs,sizeof(out)); memcpy(imm,immutable,sizeof(imm));
    rc=immutable_regions(imm,data); if (rc) return rc;
    for (size_t i=0;i<3;i++) {
        rc=span_region(out[i],output_bytes[i],1,1,&data[14+i]);
        if (rc) return rc;
    }
    if (copy_input) {
        rc=memory_range(active_inputs,sizeof(active),&in_descriptor);
        if (rc) return rc;
        if (overlap(in_descriptor,rr)) return KV_HP_ALIAS;
        memcpy(active,active_inputs,sizeof(active)); n=19;
        for (size_t i=0;i<2;i++) {
            rc=span_region(active[i],input_bytes[i],1,1,&data[17+i]);
            if (rc) return rc;
        }
    }
    rc=separated(data,n); if (rc) return rc;
    if (metadata_safe(rr,data,n) || metadata_safe(out_descriptor,data,n) ||
        metadata_safe(imm_descriptor,data,n) ||
        (copy_input && metadata_safe(in_descriptor,data,n))) return KV_HP_ALIAS;
    /* Every word is explicitly assigned; counters reflect completed loops. */
    for (size_t i=0;i<3;i++) {
        int16_t *p=(int16_t *)data[14+i].payload;
        for (uint64_t k=0;k<data[14+i].bytes/2;k++) p[k]=poison;
        r.full_output_poison_bytes+=data[14+i].bytes;
    }
    if (copy_input) for (size_t i=0;i<2;i++) {
        memcpy((void *)data[17+i].payload,(const void *)data[4+kind*2+i].payload,
               (size_t)data[17+i].bytes);
        r.input_copy_bytes+=data[17+i].bytes;
    }
    return finish(receipt,r,KV_HP_OK);
}

int kv_hp_verify(const kv_hp_span outputs[3], const kv_hp_span immutable[14],
                  uint32_t kind, uint8_t expected_guard_byte,
                  kv_hp_receipt *receipt) {
    region data[17],out_descriptor,imm_descriptor,rr;
    kv_hp_span out[3],imm[14]; kv_hp_receipt r=empty_receipt(); int rc;
    rc=descriptor_and_receipt_ranges(immutable,sizeof(imm),receipt,&imm_descriptor,&rr);
    if (rc) return rc;
    if (!outputs || kind>1) return KV_HP_ARG;
    rc=memory_range(outputs,sizeof(out),&out_descriptor);
    if (rc) return rc;
    if (overlap(out_descriptor,rr)) return KV_HP_ALIAS;
    memcpy(out,outputs,sizeof(out)); memcpy(imm,immutable,sizeof(imm));
    rc=immutable_regions(imm,data); if (rc) return rc;
    for (size_t i=0;i<3;i++) {
        rc=span_region(out[i],output_bytes[i],1,1,&data[14+i]);
        if (rc) return rc;
    }
    rc=separated(data,17); if (rc) return rc;
    if (metadata_safe(rr,data,17) || metadata_safe(out_descriptor,data,17) ||
        metadata_safe(imm_descriptor,data,17)) return KV_HP_ALIAS;
    /* Fail fast: a mismatch reports only actually visited bytes/scalars. */
    for (uint32_t i=0;i<3;i++) for (uint32_t side=0;side<2;side++) {
        const uint8_t *g=(const uint8_t *)(side?data[14+i].payload+data[14+i].bytes:
                                                     data[14+i].begin);
        for (uint64_t k=0;k<64;k++) {
            r.slot_guard_bytes++;
            if (g[k]!=expected_guard_byte) {
                r.guard_errors=1; r.first_bad_span=i; r.first_guard_side=side;
                r.first_bad_guard_byte=k; r.observed_int16=g[k];
                r.expected_int16=expected_guard_byte;
                return finish(receipt,r,KV_HP_GUARD);
            }
        }
    }
    for (uint32_t i=0;i<3;i++) {
        const int16_t *actual=(const int16_t *)data[14+i].payload;
        const int16_t *expected=(const int16_t *)data[8+kind*3+i].payload;
        for (uint64_t k=0;k<data[14+i].bytes/2;k++) {
            r.compared_scalars++;
            if (actual[k]!=expected[k]) {
                r.mismatches=1; r.first_bad_span=i; r.first_bad_scalar=k;
                r.observed_int16=actual[k]; r.expected_int16=expected[k];
                return finish(receipt,r,KV_HP_MISMATCH);
            }
        }
    }
    return finish(receipt,r,KV_HP_OK);
}

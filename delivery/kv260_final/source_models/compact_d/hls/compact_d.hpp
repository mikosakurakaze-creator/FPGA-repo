#ifndef COMPACT_D_TOP_HPP
#define COMPACT_D_TOP_HPP
#include <stdint.h>

extern "C" int compact_d_top(const int16_t* input, int16_t* output,
                            int height, int width, uint32_t abi_cookie,
                            uint64_t& work_cycles, uint64_t& input_cycles);

#ifndef __SYNTHESIS__
namespace compact_d {
typedef void (*Trace)(int node, int c, int y, int x, int16_t value, void* user);
void set_trace(Trace callback, void* user);
}
#endif
#endif

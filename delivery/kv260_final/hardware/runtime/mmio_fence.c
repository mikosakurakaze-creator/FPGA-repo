/* Build on the target: cc -O2 -shared -fPIC mmio_fence.c -o libjoint_fence.so */
#include <stdatomic.h>
void joint_mmio_fence(void) {
#if defined(__aarch64__) || defined(__arm__)
    __asm__ volatile("dsb sy" ::: "memory");
#else
    atomic_thread_fence(memory_order_seq_cst);
#endif
}

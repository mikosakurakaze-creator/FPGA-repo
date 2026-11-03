/* SPDX-License-Identifier: GPL-2.0 */
#ifndef KV260_SMMU_NS_POLICY_H
#define KV260_SMMU_NS_POLICY_H
/* Arm IHI0062D.c: IDR0.SES reads as zero to Non-secure software.
 * The banked Non-secure CR0 is at +0. CLIENTPD=1 bypasses translation.
 * USFCFG=0 is retained as a conservative additional admission condition.
 * This observes the Non-secure bank only; it does not attest Secure streams. */
static inline int kv260_smmu_ns_bypass_ok(unsigned int id0, unsigned int cr0)
{
    return id0 == 0x7c013e30U && (cr0 & 0x401U) == 1U;
}
#endif

/* SPDX-License-Identifier: MIT */

#ifndef S2R_H
#define S2R_H

#include "types.h"

/*
 * Warm resume mailbox for suspend-to-RAM.
 *
 * Waking from S2R resets the CPU to RVBAR, which is locked to m1n1. kboot
 * publishes this mailbox in /chosen/asahi,s2r-mailbox. The next stage writes
 * a per-CPU resume entry before it powers a CPU down without retention, and
 * the reset path jumps there (MMU off, EL2) instead of cold booting. Without
 * an entry the reset behaves as before. After the handoff every reset stays
 * off the console, because the next stage owns the UART and may have powered
 * it down.
 *
 * The layout is ABI shared with Linux (drivers/soc/apple/s2r.c).
 */

#define S2R_MAGIC    0x31584f424d523253ULL /* "S2RMBOX1" */
#define S2R_VERSION  1
#define S2R_MAX_CPUS 32

#define S2R_STAGE_RESET     1 /* entered the reset path while quiet */
#define S2R_STAGE_CPU_INIT  2 /* core state initialized */
#define S2R_STAGE_JUMP      3 /* jumping to the resume entry */
#define S2R_STAGE_SECONDARY 4 /* no entry, back to the spin table */

struct s2r_cpu {
    u64 mpidr;
    u64 impl_reg;   /* RVBAR (CPU implementation register) */
    u64 start_reg0; /* PMGR CPU start, system level */
    u64 start_reg1; /* PMGR CPU start, cluster */
    u32 start_val0;
    u32 start_val1;
    u64 entry;  /* next stage: one-shot resume entry for the next reset */
    u64 resets; /* m1n1: quiet resets of this CPU */
    u64 stage;  /* m1n1: last S2R_STAGE_* of the latest reset */
};

struct s2r_mailbox {
    u64 magic;
    u32 version;
    u32 ncpus;
    u64 rvbar;
    u64 quiet;
    u64 boot_mpidr;
    u64 resumes;
    u64 reserved[2];
    struct s2r_cpu cpu[S2R_MAX_CPUS];
};

extern struct s2r_mailbox s2r_mailbox;

bool s2r_console_muted(void);
void s2r_reset_enter(void);
void s2r_reset_resume(void);
void s2r_reset_secondary(void);
int s2r_publish(void *dt);
void s2r_handoff(void);

#endif

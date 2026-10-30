/* SPDX-License-Identifier: MIT */

#include "s2r.h"
#include "cpu_regs.h"
#include "memory.h"
#include "string.h"
#include "smp.h"
#include "soc.h"
#include "utils.h"

#include "libfdt/libfdt.h"

/* Shared with the secondaries and reserved for the next stage with the image */
struct s2r_mailbox s2r_mailbox __attribute__((section(".data.smp_shared"), aligned(64)));

extern char _vectors_start[0];
extern char _el1_vectors_start[0];

bool s2r_console_muted(void)
{
    return s2r_mailbox.magic == S2R_MAGIC && s2r_mailbox.quiet;
}

static struct s2r_cpu *s2r_this_cpu(void)
{
    if (s2r_mailbox.magic != S2R_MAGIC)
        return NULL;

    u64 mpidr = mrs(MPIDR_EL1) & 0xffffff;
    for (u32 i = 0; i < s2r_mailbox.ncpus && i < S2R_MAX_CPUS; i++)
        if (s2r_mailbox.cpu[i].mpidr == mpidr)
            return &s2r_mailbox.cpu[i];

    return NULL;
}

/*
 * SoC watchdog WD1 on t6000. The next stage's test dead-man arms it for
 * system sleep; restarting it here with its own timeout makes the reset time
 * show how far a wake got. Nothing happens unless it is armed.
 */
#define S2R_T6000_WD1_CUR  0x2922b0010UL
#define S2R_T6000_WD1_BITE 0x2922b0014UL
#define S2R_T6000_WD1_CTL  0x2922b001cUL

static void s2r_wdt_mark(u32 seconds)
{
    if (chip_id != T6000 || !is_boot_cpu())
        return;
    if (!(read32(S2R_T6000_WD1_CTL) & BIT(2)))
        return;

    write32(S2R_T6000_WD1_CUR, 0);
    write32(S2R_T6000_WD1_BITE, seconds * 24000000);
}

/* First thing on an RVBAR entry, before anything can print. */
void s2r_reset_enter(void)
{
    if (!s2r_console_muted())
        return;

    struct s2r_cpu *cpu = s2r_this_cpu();
    if (!cpu)
        return;

    cpu->resets++;
    cpu->stage = S2R_STAGE_RESET;
    sysop("dsb sy");
    s2r_wdt_mark(45);
}

/*
 * After init_cpu(). The interrupt masks are still at their reset values and
 * this skips exception_initialize(), which unmasks interrupts on the boot CPU
 * and clears a pending fast IPI the next stage still has to see.
 */
void s2r_reset_resume(void)
{
    if (!s2r_console_muted())
        return;

    struct s2r_cpu *cpu = s2r_this_cpu();
    if (!cpu)
        return;

    cpu->stage = S2R_STAGE_CPU_INIT;
    u64 entry = cpu->entry;
    if (!entry) {
        sysop("dsb sy");
        /* Secondaries go back to the spin table. A cold boot from here would
         * run over the next stage, so park the boot CPU instead. */
        if (is_boot_cpu()) {
            cpu->stage = S2R_STAGE_PARKED;
            sysop("dsb sy");
            while (1)
                sysop("wfe");
        }
        return;
    }

    cpu->entry = 0;
    cpu->stage = S2R_STAGE_JUMP;
    s2r_mailbox.resumes++;
    sysop("dsb sy");
    s2r_wdt_mark(75);

    msr(DAIF, 7 << 6);
    msr(VBAR_EL1, _vectors_start);
    if (in_el2()) {
        /* What exception_initialize() gives the secondaries the next stage boots */
        msr(HCR_EL2, (BIT(41) | BIT(40) | BIT(37) | BIT(34) | BIT(31) | BIT(27) | BIT(5) |
                      BIT(4) | BIT(3)));
        msr(VBAR_EL12, _el1_vectors_start);
    }
    sysop("isb");

    ((void (*)(u64, u64, u64, u64))entry)(0, 0, 0, 0);

    while (1)
        sysop("wfe");
}

void s2r_reset_secondary(void)
{
    struct s2r_cpu *cpu = s2r_console_muted() ? s2r_this_cpu() : NULL;

    if (cpu) {
        cpu->stage = S2R_STAGE_SECONDARY;
        sysop("dsb sy");
    }
}

int s2r_publish(void *dt)
{
    memset(&s2r_mailbox, 0, sizeof(s2r_mailbox));

    int ncpus = smp_s2r_describe(s2r_mailbox.cpu, S2R_MAX_CPUS);
    if (ncpus <= 0) {
        printf("S2R: no CPUs to describe, not publishing the mailbox\n");
        return 0;
    }

    s2r_mailbox.version = S2R_VERSION;
    s2r_mailbox.ncpus = ncpus;
    s2r_mailbox.rvbar = (u64)_vectors_start;
    s2r_mailbox.boot_mpidr = mrs(MPIDR_EL1) & 0xffffff;

    int node = fdt_path_offset(dt, "/chosen");
    if (node < 0)
        return 0;

    if (fdt_setprop_u64(dt, node, "asahi,s2r-mailbox", (u64)&s2r_mailbox)) {
        printf("S2R: couldn't publish the mailbox\n");
        return 0;
    }

    printf("S2R: mailbox at %p for %d CPUs\n", &s2r_mailbox, ncpus);
    return 0;
}

/* Last step before the next stage runs: from here on resets stay quiet. */
void s2r_handoff(void)
{
    if (!s2r_mailbox.ncpus)
        return;

    s2r_mailbox.quiet = 1;
    s2r_mailbox.magic = S2R_MAGIC;
    dc_civac_range(&s2r_mailbox, sizeof(s2r_mailbox));
}

"""Privacy and unchanged-control-flow contracts for optional external logging."""

from pathlib import Path
import re
import subprocess


BASE = "65e063ceee96492e5668fb1131c3d52343c10098"
REPO = Path(__file__).resolve().parents[2]


def logging_helper():
    source = (REPO / "src/kboot.c").read_text()
    start = source.index("static void dt_t8140_log_external_firmware(")
    end = source.index("static int dt_set_display_t8140(", start)
    return source[start:end]


def test_external_metadata_read_surface():
    helper = logging_helper()
    calls = set(re.findall(r"\b([A-Za-z_][A-Za-z0-9_]*)\s*\(", helper))
    assert calls <= {"dt_t8140_log_external_firmware", "fdt_path_offset", "fdt_getprop",
                     "ARRAY_SIZE", "sizeof", "printf", "if", "for", "fdt32_ld"}
    properties = re.findall(r'"(apple,[a-z,-]+)"', helper)
    assert properties == ["apple,firmware-version", "apple,firmware-compat"]
    assert "len > 0" in helper and "len <= 5 * (int)sizeof(*values)" in helper
    assert "len % (int)sizeof(*values) == 0" in helper
    assert "%p" not in helper and "%lx" not in helper and "%llx" not in helper
    assert not re.search(r"printf\([^;]*\bpath\b", helper)


def test_external_metadata_preserves_existing_operations():
    before = subprocess.check_output(["git", "show", BASE + ":src/kboot.c"],
                                     cwd=REPO, text=True)
    after = (REPO / "src/kboot.c").read_text()
    start = "    char ext_path[128];"
    end = "    free(ext_saved);"
    old = before[before.index(start):before.index(end, before.index(start))]
    new = after[after.index(start):after.index(end, after.index(start))]
    # Restore only the recorded one-for-one power-check factoring and remove
    # new observer statements. Every remaining original statement must match.
    new = new.replace("    bool ext_alias_present = !!ext;\n", "")
    prefix_start = new.index("    int ext_power = 0;")
    prefix_end = new.index("    if (ext && ext_power == 1) {", prefix_start)
    new = new[:prefix_start] + new[prefix_end:]
    new = new.replace("if (ext && ext_power == 1)",
                      'if (ext && pmgr_power_is_on(0, "DISPEXT0_CPU") == 1)')
    new = re.sub(r'        printf\("FDT: T8140 external preflight: validation_attempted=1[^;]+;\n', '', new)
    new = new.replace('        printf("FDT: T8140 external preflight: validation_attempted=0\\n");\n', '')
    tail = new.index("    /* Observe the retained DT after any external-only rollback")
    new = new[:tail]
    assert new == old
    assert new.count('pmgr_power_is_on(0, "DISPEXT0_CPU")') == 1
    # Existing validation, rollback, disabling and internal panel paths remain
    # exactly those at the public base, not a synthetic new readiness policy.


def test_external_firmware_metadata_negative_runtime(tmp_path):
    helper = logging_helper()
    harness = r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
typedef uint32_t fdt32_t;
#define ARRAY_SIZE(a) (sizeof(a) / sizeof((a)[0]))
static void *dt;
static int node_present, property_mode, decoded_cells;
static const unsigned char tuple[] = {0,0,0,1, 0,0,0,2, 0,0,0,3, 0,0,0,4, 0,0,0,5};
static int fdt_path_offset(void *tree, const char *path) {
    (void)tree; assert(path); return node_present ? 1 : -1;
}
static const void *fdt_getprop(void *tree, int node, const char *name, int *length) {
    (void)tree; assert(node == 1);
    assert(!strcmp(name, "apple,firmware-version") || !strcmp(name, "apple,firmware-compat"));
    if (property_mode == -1) { *length = -1; return NULL; }
    *length = property_mode;
    return tuple;
}
static uint32_t fdt32_ld(const fdt32_t *value) {
    const unsigned char *p = (const unsigned char *)value;
    assert(p >= tuple && p + 4 <= tuple + sizeof(tuple));
    decoded_cells++;
    return (uint32_t)p[0] << 24 | (uint32_t)p[1] << 16 | (uint32_t)p[2] << 8 | p[3];
}
''' + helper + r'''
static void run(const char *tag, int present, int length, int expected_reads) {
    node_present = present; property_mode = length; decoded_cells = 0;
    printf("CASE %s\n", tag);
    dt_t8140_log_external_firmware("DO_NOT_EXPORT_PRIVATE_PATH_OR_IDENTITY");
    assert(decoded_cells == expected_reads);
}
int main(void) {
    dt_t8140_log_external_firmware(NULL);
    run("missing-node", 0, 20, 0);
    run("missing-properties", 1, -1, 0);
    run("zero-length", 1, 0, 0);
    run("negative-length", 1, -4, 0);
    run("misaligned-length", 1, 3, 0);
    run("oversized-length", 1, 24, 0);
    run("single-cell", 1, 4, 2);
    run("five-cells", 1, 20, 10);
    return 0;
}
'''
    source = tmp_path / "metadata.c"
    binary = tmp_path / "metadata"
    source.write_text(harness)
    subprocess.check_call(["cc", "-std=c11", "-Wall", "-Wextra", "-Werror",
                           "-UNDEBUG", str(source), "-o", str(binary)])
    output = subprocess.check_output([str(binary)], text=True)
    assert "DO_NOT_EXPORT" not in output
    assert "version=1.2.3.4.5" in output
    cases = re.split(r"CASE ([a-z-]+)\n", output)
    for index in range(1, len(cases), 2):
        if cases[index] in {"single-cell", "five-cells"}:
            continue
        assert "version=" not in cases[index + 1]
        assert "tuple_valid=1" not in cases[index + 1]

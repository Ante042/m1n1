#!/bin/sh
# SPDX-License-Identifier: MIT
#
# Reproducible release build of the J613 stage 1.
#
#   tools/build_j613_stage1.sh OUTDIR [extra make arguments]
#
# Builds the committed tree with RELEASE=1 USE_CLANG=1 CHAINLOADING=1
# J613_STAGE1=1 and writes to OUTDIR:
#   m1n1-j613-stage1.bin   factory image (fill it with tools/j613_stage1_fill.py)
#   m1n1-j613-stage1.elf   the matching ELF
#   manifest.json          sizes, hashes, tag, source commit, toolchain
#   SHA256SUMS
#
# Build paths are remapped and SOURCE_DATE_EPOCH comes from the commit, so the
# same commit built with the same toolchain gives identical bytes in any
# directory. The version tag defaults to v1.6.1-m3next.stage1 (set
# M1N1_VERSION_TAG to change it); traceability goes in the manifest.

set -eu

if [ $# -lt 1 ]; then
    echo "usage: $0 OUTDIR [make arguments]" >&2
    exit 1
fi
out=$1
shift
case "$out" in
    /*) ;;
    *) out=$(pwd)/$out ;;
esac

cd "$(dirname "$0")/.."
src=$(pwd -P)

if [ -n "$(git status --porcelain --untracked-files=no)" ]; then
    echo "error: release builds come from a commit; commit or stash your edits first" >&2
    exit 1
fi

commit=$(git rev-parse HEAD)
describe=$(git describe --tags --always --abbrev=12)
SOURCE_DATE_EPOCH=$(git log -1 --format=%ct)
M1N1_VERSION_TAG=${M1N1_VERSION_TAG:-v1.6.1-m3next.stage1}
export SOURCE_DATE_EPOCH M1N1_VERSION_TAG

cargo_home=$(cd "${CARGO_HOME:-$HOME/.cargo}" && pwd -P)
rustup_home=$(cd "${RUSTUP_HOME:-$HOME/.rustup}" 2>/dev/null && pwd -P || echo /nonexistent)
RUSTFLAGS="${RUSTFLAGS:-} --remap-path-prefix=$src=/m1n1 --remap-path-prefix=$cargo_home=/cargo"
RUSTFLAGS="$RUSTFLAGS --remap-path-prefix=$rustup_home=/rustup"
CARGO_INCREMENTAL=0
export RUSTFLAGS CARGO_INCREMENTAL

# USE_CLANG=1 passes ARCH to clang as --target
arch=aarch64-linux-gnu

make clean >/dev/null
make -j"${JOBS:-4}" ARCH="$arch" RELEASE=1 USE_CLANG=1 CHAINLOADING=1 J613_STAGE1=1 \
    EXTRA_CFLAGS="-ffile-prefix-map=$src=." "$@"

mkdir -p "$out"
cp build/m1n1.bin "$out/m1n1-j613-stage1.bin"
cp build/m1n1-raw.elf "$out/m1n1-j613-stage1.elf"

clang_version=$(${TOOLCHAIN:-}clang --version 2>/dev/null | head -n1 || echo unknown)
lld_version=$(${LLDDIR:-${TOOLCHAIN:-}}ld.lld --version 2>/dev/null | head -n1 || echo unknown)
rustc_version=$(rustc -V 2>/dev/null || echo unknown)
cargo_version=$(cargo -V 2>/dev/null || echo unknown)

python3 -I - "$out" "$commit" "$describe" "$M1N1_VERSION_TAG" "$SOURCE_DATE_EPOCH" \
    "$clang_version" "$lld_version" "$rustc_version" "$cargo_version" <<'EOF'
import hashlib, json, os, sys

out, commit, describe, tag, epoch, clang, lld, rustc, cargo = sys.argv[1:]
files = ["m1n1-j613-stage1.bin", "m1n1-j613-stage1.elf"]

def info(name):
    with open(os.path.join(out, name), "rb") as f:
        data = f.read()
    return {
        "bytes": len(data),
        "bytes_hex": hex(len(data)),
        "sha256": hashlib.sha256(data).hexdigest(),
        "md5": hashlib.md5(data).hexdigest(),
    }

manifest = {
    "name": f"m1n1-j613-stage1-{commit[:12]}",
    "tag": tag,
    "source_commit": commit,
    "git_describe": describe,
    "source_date_epoch": int(epoch),
    "build": "RELEASE=1 USE_CLANG=1 CHAINLOADING=1 J613_STAGE1=1",
    "size_bounds": ["0x114000", "0x381000"],
    "toolchain": {"clang": clang, "ld.lld": lld, "rustc": rustc, "cargo": cargo},
    "image": dict(file=files[0], **info(files[0])),
    "elf": dict(file=files[1], **info(files[1])),
}
with open(os.path.join(out, "manifest.json"), "w") as f:
    json.dump(manifest, f, indent=2)
    f.write("\n")

with open(os.path.join(out, "SHA256SUMS"), "w") as f:
    for name in files + ["manifest.json"]:
        with open(os.path.join(out, name), "rb") as g:
            f.write(f"{hashlib.sha256(g.read()).hexdigest()}  {name}\n")
EOF

echo "Wrote $out:"
cat "$out/SHA256SUMS"

#!/usr/bin/env bash
# Rebuild the patched Wine that Camfrog launches with.
#
# The changes live in wine-patches/ as one file per fix, applied in order on top
# of the Wine release commit recorded in wine-patches/base:
#
#   0001  devenum scans /dev/video0..63 instead of 0..9, so capture devices that
#         v4l2loopback pins higher up (the OBS Virtual Camera on /dev/video10) are
#         listed at all.
#   0002  qcap waits for a frame with poll() instead of spinning on the
#         non-blocking read, and reports V4L_E_FRAME_TIMEOUT when none arrives so
#         the capture thread can notice a stop. Without it, switching source
#         while the device delivers nothing spins at full CPU and the thread
#         that stops the graph waits forever.
#   0003  qcap flips the captured image a row at a time with memcpy() instead of
#         copying it byte by byte; at 1920x1080 that is 6 MB of copying per frame.
#   0004  qcap keeps the capture thread alive when GetBuffer(), the device read
#         or the downstream Receive() fails: warn once, back off and retry
#         instead of ending the stream for good with a frozen picture left
#         behind.
#   0005  qcap backs off 5 ms when the loopback reports a readable frame but
#         read() has none, which v4l2loopback does for a frame it already handed
#         out, so a stalled producer such as OBS costs no CPU.
#
# wine-patches/base holds the commit the series starts from (the Wine release the
# patches were written against). The script replays the whole series onto that
# commit and compares the result with the tree. Testing each patch on its own
# does not work here: later patches touch lines earlier ones added, so a single
# patch is neither cleanly appliable nor cleanly reversible once its neighbour is
# in place.
#
# Usage:  ./build-patched-wine.sh            apply/restore the series and build
#         ./build-patched-wine.sh --check    report state only, change nothing
#
# If wine-patches/base is missing, the script warns, prints the command that
# recreates it, and falls back to checking each patch on its own against the
# tree. That fallback cannot distinguish overlapping patches, so it may report a
# patch as neither applied nor appliable; the replay is the reliable answer.
#
# The build is 64-bit only (--enable-win64), which is all the Camfrog client
# needs. Do not reuse this tree for 32-bit programs.
#
# A first-time configure that silently builds a 32-bit tree is the trap here
# (host_cpu=i386, PE_ARCHS = i386). If that happens, run `make distclean` and
# this script again.

set -euo pipefail

here=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
src=${WINE_SRC:-$HOME/wine-src-11.22}
patchdir=$here/wine-patches
jobs=${JOBS:-$(nproc 2>/dev/null || echo 4)}
mode=${1:-build}

[ -d "$src" ] || { echo "error: no Wine source tree at $src (set WINE_SRC=...)" >&2; exit 1; }
[ -d "$patchdir" ] || { echo "error: missing patch directory: $patchdir" >&2; exit 1; }

patches=("$patchdir"/*.patch)
[ -e "${patches[0]}" ] || { echo "error: no patches in $patchdir" >&2; exit 1; }

cd "$src"

files=()
replayed=""

if [ -s "$patchdir/base" ]; then
    base=$(tr -d '[:space:]' < "$patchdir/base")

    replayed=$(mktemp -d)
    trap 'rm -rf "$replayed"' EXIT

    if ! git archive "$base" 2>/dev/null | tar -x -C "$replayed"; then
        echo "error: wine-patches/base names commit $base, which $src does not have." >&2
        echo "       fix it with: git -C $src rev-parse <commit-the-series-starts-from> > $patchdir/base" >&2
        exit 1
    fi

    for p in "${patches[@]}"; do
        if ! ( cd "$replayed" && git apply "$p" ); then
            echo "error: $(basename "$p") does not apply to the base commit $base" >&2
            exit 1
        fi
        while read -r f; do files+=("$f"); done < <(sed -n 's|^+++ b/||p' "$p")
    done

    applied=()
    missing=()
    for p in "${patches[@]}"; do
        changed=no
        for f in $(sed -n 's|^+++ b/||p' "$p"); do
            cmp -s "$replayed/$f" "$src/$f" || { changed=yes; break; }
        done
        if [ "$changed" = no ]; then applied+=("$p"); else missing+=("$p"); fi
    done
else
    echo "warning: $patchdir/base is missing; falling back to a per-patch check," >&2
    echo "         which cannot tell overlapping patches apart." >&2
    echo "         recreate it with: git -C $src rev-parse <commit-the-series-starts-from> > $patchdir/base" >&2

    # GNU patch with fuzz tolerates the overlaps that make `git apply` report a
    # false failure here (a later patch adding lines inside an earlier one).
    applied=()
    missing=()
    for p in "${patches[@]}"; do
        while read -r f; do files+=("$f"); done < <(sed -n 's|^+++ b/||p' "$p")
        if patch -R -p1 --dry-run -F3 --force --silent < "$p" >/dev/null 2>&1; then
            applied+=("$p")
        elif patch -p1 --dry-run -F3 --force --silent < "$p" >/dev/null 2>&1; then
            missing+=("$p")
        else
            echo "error: cannot tell whether $(basename "$p") is applied; without" >&2
            echo "       wine-patches/base the series cannot be replayed to find out." >&2
            exit 1
        fi
    done
fi

built=no
[ -f dlls/devenum/x86_64-windows/devenum.dll ] && [ -f dlls/qcap/x86_64-windows/qcap.dll ] && built=yes

arch=unknown
if [ -f config.status ]; then
    arch=$(sed -n 's/^host_cpu *= *//p' config.status | head -1)
    [ -n "$arch" ] || arch=unknown
fi

echo "tree:    $src ($(git describe --tags 2>/dev/null || echo unknown))"
echo "patches: ${#applied[@]} applied, ${#missing[@]} missing (of ${#patches[@]})"
for p in "${missing[@]}"; do echo "         missing: $(basename "$p")"; done
echo "built:   devenum+qcap=$built    configure arch: $arch"

if [ "$mode" = --check ]; then
    [ "${#missing[@]}" -eq 0 ] && [ "$built" = yes ] && [ "$arch" = x86_64 ] && exit 0
    exit 1
fi

if [ "${#missing[@]}" -gt 0 ]; then
    if [ -n "$replayed" ]; then
        echo "restoring patched files from the series"
        printf '%s\n' "${files[@]}" | sort -u | while read -r f; do
            mkdir -p "$(dirname "$f")"
            cp "$replayed/$f" "$f"
        done
    else
        for p in "${missing[@]}"; do
            echo "applying $(basename "$p")"
            patch -p1 -F3 --force < "$p"
        done
    fi
fi

if [ ! -f config.status ]; then
    echo "configuring (64-bit, no tests)"
    ./configure --enable-win64 --disable-tests
fi

arch=$(sed -n 's/^host_cpu *= *//p' config.status | head -1)
if [ "$arch" != x86_64 ]; then
    echo "error: this tree is configured for $arch, not x86_64." >&2
    echo "       run 'make distclean' in $src and rerun this script." >&2
    exit 1
fi

echo "building with -j$jobs"
make -j"$jobs"

[ -f dlls/devenum/x86_64-windows/devenum.dll ] || { echo "error: devenum.dll not produced" >&2; exit 1; }
[ -f dlls/qcap/x86_64-windows/qcap.dll ] || { echo "error: qcap.dll not produced" >&2; exit 1; }
echo "done: $("$src/wine" --version 2>/dev/null || echo 'wine --version failed') ($src/wine)"

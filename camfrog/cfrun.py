#!/usr/bin/env python3
"""Launch Camfrog under Wine and, if the UI thread dies with a stack overflow,
dump that thread's stack as a histogram of return addresses.

Usage: cfrun.py <logfile> [WINEDEBUG-string]

The dump needs /proc/<pid>/mem, which (ptrace_scope=1) only an ancestor of the
Wine process may read - hence this wrapper instead of a bare `wine ...`.
Writes <logfile>.stack.txt (histogram) and <logfile>.stack.bin (raw stack).
"""
import bisect
import collections
import os
import struct
import subprocess
import sys
import time

PREFIX = os.path.expanduser("~/.local/share/wineprefixes/camfrog8")
EXE = os.path.join(PREFIX, "drive_c/users/douggle/AppData/Local/Programs/"
                   "Camfrog Video Chat/Camfrog Video Chat.exe")
STACK_LO, STACK_HI = 0x21000, 0x220000      # main thread stack (see err:virtual line)


def read_maps(base):
    maps = []
    for line in open(base + "/maps"):
        p = line.split(None, 5)
        a, b = (int(x, 16) for x in p[0].split("-"))
        maps.append((a, b, p[1], p[5].strip() if len(p) > 5 else ""))
    return maps


def dump_stack(pid, out):
    tids = [t for t in os.listdir(f"/proc/{pid}/task") if t != str(pid)]
    if not tids:
        return "no live threads left"
    base = f"/proc/{pid}/task/{tids[0]}"
    maps = read_maps(base)
    with open(base + "/mem", "rb") as f:
        f.seek(STACK_LO)
        data = f.read(STACK_HI - STACK_LO)
    open(out + ".stack.bin", "wb").write(data)

    starts = [m[0] for m in maps]
    bases = {}
    for a, b, perm, name in maps:
        if name:
            bases[name] = min(bases.get(name, a), a)

    def find(v):
        i = bisect.bisect_right(starts, v) - 1
        if i >= 0 and maps[i][0] <= v < maps[i][1]:
            return maps[i]
        return None

    cnt = collections.Counter()
    order = []
    for off in range(0, len(data) - 7, 8):
        v = struct.unpack_from("<Q", data, off)[0]
        if v < 0x10000:
            continue
        m = find(v)
        if m and "x" in m[2]:
            cnt[v] += 1
            order.append((off, v))

    def label(v):
        m = find(v)
        name = m[3].split("/")[-1] if m[3] else "[anon]"
        return f"{name}+{v - bases.get(m[3], m[0]):#x}"

    lines = [f"stack {STACK_LO:#x}-{STACK_HI:#x}, {len(cnt)} distinct code pointers", "",
             "== most frequent code pointers =="]
    for v, c in cnt.most_common(40):
        lines.append(f"{c:7d}  {v:#x}  {label(v)}")
    lines += ["", "== deepest 60 code pointers (top of stack first) =="]
    for off, v in order[:60]:
        lines.append(f"  sp+{off:#08x}  {v:#x}  {label(v)}")
    open(out + ".stack.txt", "w").write("\n".join(lines) + "\n")
    return "ok"


def main():
    log = sys.argv[1]
    env = dict(os.environ, WINEPREFIX=PREFIX, DISPLAY=os.environ.get("DISPLAY", ":0"))
    if len(sys.argv) > 2 and sys.argv[2]:
        env["WINEDEBUG"] = sys.argv[2]
    else:
        env.pop("WINEDEBUG", None)

    with open(log, "wb") as lf:
        proc = subprocess.Popen(["wine", EXE], stdout=lf, stderr=subprocess.STDOUT, env=env)
    print(f"camfrog pid {proc.pid}", flush=True)

    pos = 0
    dumped = False
    def nthreads():
        try:
            return len(os.listdir(f"/proc/{proc.pid}/task"))
        except OSError:
            return 0

    while nthreads() > 0:
        time.sleep(0.5)
        try:
            with open(log, "rb") as f:
                f.seek(pos)
                chunk = f.read()
                pos = f.tell()
        except OSError:
            continue
        if not dumped and b"stack overflow" in chunk:
            time.sleep(0.3)
            try:
                res = dump_stack(proc.pid, log)
            except Exception as e:      # noqa: BLE001 - report whatever went wrong
                res = f"failed: {e!r}"
            print(f"stack overflow detected, dump: {res}", flush=True)
            dumped = True
        if proc.poll() is not None and nthreads() <= 1:
            break
    print("camfrog exited", flush=True)


if __name__ == "__main__":
    main()

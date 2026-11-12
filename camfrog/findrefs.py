#!/usr/bin/env python3
"""Find rip-relative references to strings in a PE, fast (numpy, chunked)."""
import struct, sys, os
import numpy as np

EXE = os.path.expanduser("~/.local/share/wineprefixes/camfrog8/drive_c/users/douggle/"
                         "AppData/Local/Programs/Camfrog Video Chat/Camfrog Video Chat.exe")


def load():
    data = open(EXE, 'rb').read()
    hdr = data[:0x1000]
    pe = struct.unpack_from('<I', hdr, 0x3c)[0]
    imgbase = struct.unpack_from('<I', hdr, pe + 0x34)[0]
    nsec = struct.unpack_from('<H', hdr, pe + 6)[0]
    optsz = struct.unpack_from('<H', hdr, pe + 20)[0]
    secs = []
    base = pe + 24 + optsz
    for i in range(nsec):
        o = base + i * 40
        name = data[o:o + 8].rstrip(b'\0').decode()
        vsz, va, rsz, ro = struct.unpack_from('<IIII', data, o + 8)
        secs.append((name, va, ro, rsz))
    return data, imgbase, secs


def main():
    data, imgbase, secs = load()

    def f2v(off):
        for n, va, ro, rsz in secs:
            if ro <= off < ro + rsz:
                return imgbase + va + (off - ro)
        return None

    text = [s for s in secs if s[0] == '.text'][0]
    _, tva, tro, trsz = text
    tbase = imgbase + tva           # VA of .text start
    chunk = data[tro:tro + trsz]

    pats = [
        ("CliMotd", b"cf_room.CliMotd\0"),
        ("CliMotdAgree", b"cf_room.CliMotdAgree\0"),
        ("CliMotdLocalized", b"cf_room.CliMotdLocalized\0"),
        ("log_motd", "log_motd".encode('utf-16-le') + b"\0\0"),
        ("rules_open", "camfrog:room:dialog:rules:open".encode('utf-16-le') + b"\0\0"),
        ("chat_room_motd_state", "chat_room_motd_state".encode('utf-16-le') + b"\0\0"),
        ("motd_agree", "motd_agree\0".encode('ascii')),
    ]

    for name, pat in pats:
        off = data.find(pat)
        if off < 0:
            print(f"{name}: string NOT FOUND")
            continue
        va = f2v(off)
        print(f"{name}: file {hex(off)} va {hex(va)}")

    print("\nScanning .text for refs...")
    n = len(chunk)
    refs = {}
    for name, pat in pats:
        off = data.find(pat)
        if off < 0:
            continue
        target = f2v(off)
        hits = []
        for k in range(4):
            usable = ((n - k) // 4) * 4
            if usable <= 0:
                continue
            arr = np.frombuffer(chunk[k:k + usable], dtype='<i4')
            idx = np.arange(len(arr), dtype=np.int64)
            want = target - (tbase + k) - 4 - 4 * idx
            ok = np.nonzero(arr.astype(np.int64) == want)[0]
            for i in ok:
                hits.append(tbase + k + 4 * int(i))
        refs[name] = sorted(hits)
        print(f"{name}: {len(hits)} refs -> {[hex(h) for h in sorted(hits)[:12]]}")

if __name__ == '__main__':
    main()

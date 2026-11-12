#!/usr/bin/env python3
"""Dependency-free pcap/pcapng reader that reassembles TCP payloads and reports
interesting ASCII/protobuf content. Usage: pcap_streams.py <file> [--all]
"""
import struct
import sys
import re
from collections import defaultdict


def read_pcap(data):
    """Yield (linktype, packet_bytes)."""
    if len(data) < 24:
        return
    magic = data[:4]
    if magic in (b"\xd4\xc3\xb2\xa1", b"\x4d\x3c\xb2\xa1"):
        endian = "<"
    elif magic in (b"\xa1\xb2\xc3\xd4", b"\xa1\xb2\x3c\x4d"):
        endian = ">"
    else:
        return read_pcapng(data)
    linktype = struct.unpack_from(endian + "I", data, 20)[0]
    off = 24
    n = len(data)
    while off + 16 <= n:
        _, _, incl, _ = struct.unpack_from(endian + "IIII", data, off)
        off += 16
        if off + incl > n:
            break
        yield linktype, data[off:off + incl]
        off += incl


def read_pcapng(data):
    off = 0
    n = len(data)
    linktypes = []
    while off + 12 <= n:
        btype, blen = struct.unpack_from("<II", data, off)
        if blen < 12 or off + blen > n:
            break
        if btype == 1:  # IDB
            linktypes.append(struct.unpack_from("<H", data, off + 8)[0])
        elif btype == 6:  # EPB
            iface, _, _, caplen, _ = struct.unpack_from("<IIIII", data, off + 8)
            pkt_off = off + 28
            lt = linktypes[iface] if iface < len(linktypes) else 1
            yield lt, data[pkt_off:pkt_off + caplen]
        off += blen


def ip_tcp(pkt, linktype):
    """Return (srcip, dstip, sport, dport, seq, payload) or None."""
    if linktype == 1:  # ethernet
        if len(pkt) < 14:
            return None
        etype = struct.unpack_from(">H", pkt, 12)[0]
        off = 14
        while etype in (0x8100, 0x88A8):
            etype = struct.unpack_from(">H", pkt, off + 2)[0]
            off += 4
        if etype == 0x0800:
            return ipv4_tcp(pkt[off:])
        return None
    if linktype in (101, 228, 12, 14):  # raw ip
        return ipv4_tcp(pkt)
    if linktype == 113:  # linux sll
        return ipv4_tcp(pkt[16:])
    return None


def ipv4_tcp(ip):
    if len(ip) < 20 or (ip[0] >> 4) != 4:
        return None
    ihl = (ip[0] & 0x0F) * 4
    proto = ip[9]
    if proto != 6:
        return None
    src = ".".join(str(b) for b in ip[12:16])
    dst = ".".join(str(b) for b in ip[16:20])
    tcp = ip[ihl:]
    if len(tcp) < 20:
        return None
    sport, dport, seq = struct.unpack_from(">HHI", tcp, 0)
    doff = (tcp[12] >> 4) * 4
    payload = tcp[doff:]
    return src, dst, sport, dport, seq, payload


def main():
    path = sys.argv[1]
    show_all = "--all" in sys.argv
    data = open(path, "rb").read()
    streams = defaultdict(list)  # (src,sport,dst,dport) -> [(seq, data)]
    pkts = 0
    for linktype, pkt in read_pcap(data):
        r = ip_tcp(pkt, linktype)
        pkts += 1
        if not r:
            continue
        src, dst, sport, dport, seq, payload = r
        if payload:
            streams[(src, sport, dst, dport)].append((seq, payload))

    print(f"packets={pkts} streams_with_data={len(streams)}")
    needles = (b"cf_room", b"motd", b"RULES", b"Welcome to", b"NO WANKING",
               b"Acoustic", b"agree")
    for key, segs in streams.items():
        segs.sort(key=lambda s: s[0])
        blob = b"".join(s[1] for s in segs)
        printable = sum(32 <= b < 127 for b in blob) / max(1, len(blob))
        hits = [n.decode() for n in needles if n in blob]
        if not (hits or (show_all and printable > 0.6)):
            continue
        src, sport, dst, dport = key
        print(f"\n=== {src}:{sport} -> {dst}:{dport}  {len(blob)} bytes  "
              f"printable={printable:.2f} hits={hits}")
        for m in re.finditer(rb"[\x20-\x7e]{8,}", blob):
            print("   ", m.group().decode()[:160])


if __name__ == "__main__":
    main()

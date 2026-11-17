# Camfrog Video Chat on Wine

Notes, patches and helper scripts for running the Camfrog Video Chat Windows client
under Wine on Linux. Out of the box the client starts but room text chat, the room
agreement page and outgoing audio do not work. Each of those turned out to be a
function Camfrog calls that Wine leaves unimplemented.

Nothing here contains Camfrog binaries.

There are two patch sets against two Wine versions, because they are installed in
different places:

| Patch set | Wine version | Where it ends up |
| --- | --- | --- |
| `camfrog/mf-audio-capture.patch`, `camfrog/wine-mshtml-ieframe.patch` | 11.21 | built from that source and installed as native overrides (`mf`, `mshtml`, `ieframe`) in the `camfrog8` prefix |
| `wine-patches/*.patch` (capture path) | 11.22, pinned by `wine-patches/base` | applied to `~/wine-src-11.22`, the Wine binary `camfrog-wine.sh` launches |

The 11.22 source does not contain the 11.21 patches: those DLLs exist only in the
prefix, loaded through `HKCU\Software\Wine\DllOverrides`. The capture series is the
only set that belongs in a Wine source tree, and it does not need the 11.21 patches to
build.

## What works with these patches

| Feature | State | Root cause in Wine |
| --- | --- | --- |
| Outgoing audio (Talk / hands-free) | works | `MFCreateDeviceSource` was a stub, so the app never got a microphone source |
| Live room chat log | works | `IMarkupPointer::Left`, `IHTMLElement2::doScroll` and `get_canHandleChildren` were stubs |
| Room agreement (MOTD) page | works | same three stubs; the pane is the same kind of page as the chat log |
| Enter sends a chat line | works | `IHTMLEditServices::AddDesigner` was a stub, so the app never saw typed text |
| Chat box keeps its height while typing | works | `body.scrollHeight` never went below the box height, unlike IE, so the app grew the box on every key |
| Room text rendering at all | works | earlier fixes: markup pointers, `styleSheet.ownerNode`, one patched page script |
| Incoming audio and video | worked already | |

## What is still open

- **Intermittent hang at startup.** The UI thread dies with a stack overflow roughly
  15 to 20 seconds after launch, about one launch in five. The cause is not known.
  `camfrog/cfrun.py` launches the client and dumps that thread's stack when it happens.
- Camfrog's record-volume slider is not applied by the new capture source. Adjust the
  microphone level on the host instead.
- The `ieframe` part of the patch still carries debug code and an unverified experiment
  (see the end of `crash-patch.txt`).

## Persistent setup for the OBS virtual camera

The Camfrog client only lists capture devices that Wine's `devenum` reports, and
`devenum` asked `avicap32` for drivers 0..9 only, so a camera on `/dev/video10` was
never offered. Two things now make that hold across reboots and ordinary launches:

- `wine-patches/0001-devenum-enumerate-video10-and-up.patch` widens the scan to
  `/dev/video0..63`. It is committed on branch `camfrog-patched-wine` in
  `~/wine-src-11.22` (Wine 11.22, 64-bit build), and `build-patched-wine.sh` reapplies
  it and rebuilds if that tree is ever cleaned or recreated.
- Four more patches fix the capture path itself. All five apply in order on top of
  the Wine release commit named in `wine-patches/base`:

  | Patch | What it fixes |
  | --- | --- |
  | `0001-devenum-enumerate-video10-and-up.patch` | `devenum` only scanned `/dev/video0..9`, so the OBS Virtual Camera on `/dev/video10` was never listed |
  | `0002-qcap-wait-for-frames-instead-of-spinning.patch` | `qcap` busy-spun on the non-blocking read and never noticed a stop request, which hung the UI on a source switch; it now polls and reports a frame timeout |
  | `0003-qcap-copy-rows-with-memcpy.patch` | the captured image was flipped byte by byte instead of a row at a time (6 MB of copying per 1080p frame) |
  | `0004-qcap-keep-the-stream-alive-on-errors.patch` | one failed `GetBuffer`, device read or `Receive` ended the capture thread for good, leaving a frozen picture; those now warn once and retry |
  | `0005-qcap-do-not-spin-when-the-loopback-is-idle.patch` | when the producer stalls, `v4l2loopback` still reports a readable frame, so the retry loop spun at full speed; it now backs off 5 ms |

  The capture loop deliberately never gives up, so a camera stream survives a stalled
  producer (OBS pausing its virtual camera, for instance) and resumes by itself when
  frames arrive again. It cannot make frames appear: if OBS stops writing to
  `/dev/video10`, the preview keeps the last frame until OBS recovers.
- `v4l2loopback/99-v4l2loopback-obs.conf` is installed as
  `/etc/modprobe.d/99-v4l2loopback-obs.conf` (`video_nr=10 exclusive_caps=0`) and
  `v4l2loopback/v4l2loopback.conf` as `/etc/modules-load.d/v4l2loopback.conf`, so the
  loopback node is loaded at boot and always advertises capture capability. Without
  `exclusive_caps=0` the node is video-output only until OBS starts streaming, and
  Wine's capture-capability probe skips it.
- `camfrog-wine.sh` is what the desktop and menu entries now call: it launches with the
  patched Wine and no tracing. `launch-camfrog-trace.sh` remains the tracing variant.

The system Wine (`/usr/bin/wine`) is untouched; `teknoparrot`, Battle.net and the
Camfrog 6.0 shortcuts still use it.

## Rebuilding the patched Wine

`wine-patches/` is a self-contained series against a known commit, so a fresh clone
can reproduce the tree those patches were developed in:

1. Get the Wine source at the version in `wine-patches/base`
   (`git rev-parse HEAD` there should match the file) into `~/wine-src-11.22`, or
   point `WINE_SRC` at it.
2. `./build-patched-wine.sh --check` reports whether the series is applied and whether
   the tree is a 64-bit build; it changes nothing.
3. `./build-patched-wine.sh` restores any patched file from the series, configures
   64-bit if needed, and builds.

`wine-patches/base` is tracked in this repo on purpose. The script replays the whole
series onto that commit and compares the result with the working tree, because the
patches overlap and checking them one at a time against the tree reports false
failures. If `base` is missing, the script warns, prints the command that recreates it
(`git -C ~/wine-src-11.22 rev-parse <commit> > wine-patches/base`) and falls back to a
per-patch check that cannot resolve overlaps.

## Files

| Path | What it is |
| --- | --- |
| `crash-patch.txt` | Running notes: every root cause, how it was found, rebuild and install steps |
| `camfrog/mf-audio-capture.patch` | Wine 11.21 `dlls/mf`: audio capture media source behind `MFCreateDeviceSource` |
| `camfrog/wine-mshtml-ieframe.patch` | Wine 11.21 `dlls/mshtml` and `dlls/ieframe` changes |
| `camfrog/cfrun.py` | Launcher that catches the startup hang and dumps the dead thread's stack |
| `camfrog/findrefs.py` | Finds RIP-relative references to strings in the client exe |
| `camfrog/pcap_streams.py` | Dependency-free pcap reader that reassembles TCP streams |
| `camfrog/shot.sh` | Screenshot helper for the Wine window |
| `camfrog/upload_receiver.py` | One-shot HTTP upload receiver |
| `wine-patches/*.patch` | The capture-path series, applied in order (see above) |
| `wine-patches/base` | Commit the series starts from; needed to verify or rebuild it |
| `build-patched-wine.sh` | Applies the series and builds the patched Wine |
| `camfrog-wine.sh` | Launches Camfrog with the patched Wine (`WINEPREFIX=camfrog8`) |

## Building the 11.21 app-level DLLs and installing them

This is the older patch set (audio capture, chat log, agreement page). The capture
series in `wine-patches/` is separate and is covered under "Rebuilding the patched
Wine" below.

1. Unpack Wine 11.21, configure it, and apply both `camfrog/*.patch` files with
   `patch -p1`.
2. Build only what changed:

   ```bash
   make -j16 dlls/mf/all dlls/mshtml/all dlls/ieframe/all
   ```

3. For each built DLL in `dlls/<name>/x86_64-windows/`, overwrite the 16 bytes at file
   offset `0x40` (the `Wine builtin DLL` marker) with any other text, then copy the file
   into the prefix's `drive_c/windows/system32/`. Without that step Wine refuses to load
   the file as a native DLL.
4. Set `HKCU\Software\Wine\DllOverrides` to `native` for `mf`, `mshtml` and `ieframe`.

## How the problems were found

The short version, in the order they were solved. `crash-patch.txt` has the detail.

- **Audio.** PipeWire showed no recording stream from Wine while Talk was held, in either
  talk mode. A WASAPI trace showed the app enumerating the microphone but never opening
  it, and one line gave it away: `fixme:mfplat:MFCreateDeviceSource ... stub!`. The client
  reads the microphone through Media Foundation's source reader.
- **Chat log.** A full MSHTML trace of one sent message showed the app asking a markup
  pointer for the last log entry, then scrolling, then asking whether the body can hold
  children, and giving up at whichever of those was unimplemented.
- **Enter.** Adding key codes to the trace showed the Enter key-down never reaches the
  browser. The client intercepts it and sends only if it thinks the box has text, which
  it learns through an edit designer callback.

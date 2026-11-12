# Camfrog Video Chat on Wine

Notes, patches and helper scripts for running the Camfrog Video Chat Windows client
under Wine 11.21 on Linux. Out of the box the client starts but room text chat, the
room agreement page and outgoing audio do not work. Each of those turned out to be a
function Camfrog calls that Wine leaves unimplemented.

Nothing here contains Camfrog binaries. The patches are against the Wine 11.21 source.

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

## Files

| Path | What it is |
| --- | --- |
| `crash-patch.txt` | Running notes: every root cause, how it was found, rebuild and install steps |
| `camfrog/mf-audio-capture.patch` | Wine `dlls/mf`: audio capture media source behind `MFCreateDeviceSource` |
| `camfrog/wine-mshtml-ieframe.patch` | Wine `dlls/mshtml` and `dlls/ieframe` changes |
| `camfrog/cfrun.py` | Launcher that catches the startup hang and dumps the dead thread's stack |
| `camfrog/findrefs.py` | Finds RIP-relative references to strings in the client exe |
| `camfrog/pcap_streams.py` | Dependency-free pcap reader that reassembles TCP streams |
| `camfrog/shot.sh` | Screenshot helper for the Wine window |
| `camfrog/upload_receiver.py` | One-shot HTTP upload receiver |

## Building and installing

1. Unpack Wine 11.21, configure it, and apply both patches with `patch -p1`.
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

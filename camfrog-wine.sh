#!/usr/bin/env bash
# Start the Camfrog 8.5 client with the patched Wine, no tracing.
#
# This is what the desktop and menu entries call. Use launch-camfrog-trace.sh
# instead when a log is wanted (it also refuses to start a second instance).
#
# Why a specific Wine binary: only the patched build in $WINE_SRC scans
# /dev/video0..63 for capture devices, and the system Wine stops at /dev/video9,
# which hides OBS's virtual camera on /dev/video10. Rebuild it with
# ./build-patched-wine.sh. Override with WINEBIN=/usr/bin/wine if you want the
# unpatched behaviour.

set -euo pipefail

here=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
export WINEPREFIX=${WINEPREFIX:-$HOME/.local/share/wineprefixes/camfrog8}

WINEBIN=${WINEBIN:-$HOME/wine-src-11.22/wine}
if [ ! -x "$WINEBIN" ]; then
    echo "warning: patched Wine not found at $WINEBIN." >&2
    echo "         OBS Virtual Camera will be missing; run $here/build-patched-wine.sh" >&2
    WINEBIN=wine
fi

appdir="$WINEPREFIX/drive_c/users/douggle/AppData/Local/Programs/Camfrog Video Chat"
exe="$appdir/Camfrog Video Chat.exe"
[ -f "$exe" ] || { echo "error: not found: $exe" >&2; exit 1; }

cd "$appdir"
exec "$WINEBIN" "Camfrog Video Chat.exe" "$@"

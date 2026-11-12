#!/bin/bash
# shot.sh <out.png> [window-name-or-id] [scale]
# Captures the Wine desktop (a single X window) and crops to the requested app window.
set -e
export DISPLAY=:0
OUT=${1:-/tmp/shot.png}
PAT=${2:-Video Chat Room}
SCALE=${3:-900}
if [[ "$PAT" =~ ^[0-9]+$ ]]; then W=$PAT; else W=$(xdotool search --name "$PAT" 2>/dev/null | head -1); fi
[ -z "$W" ] && { echo "no window for '$PAT'"; exit 1; }
D=$(xdotool search --name "Wine Desktop" 2>/dev/null | head -1)
DX=$(xwininfo -id "$D" | awk '/Absolute upper-left X/{print $4}')
DY=$(xwininfo -id "$D" | awk '/Absolute upper-left Y/{print $4}')
X=$(xwininfo -id "$W" | awk '/Absolute upper-left X/{print $4}')
Y=$(xwininfo -id "$W" | awk '/Absolute upper-left Y/{print $4}')
WD=$(xwininfo -id "$W" | awk '/Width:/{print $2}')
HT=$(xwininfo -id "$W" | awk '/Height:/{print $2}')
timeout 25 magick import -window "$D" /tmp/.shot_full.png 2>/dev/null || true
magick /tmp/.shot_full.png -crop "${WD}x${HT}+$((X-DX))+$((Y-DY))" +repage "$OUT" 2>/dev/null || true
if [ "$SCALE" != "0" ]; then magick "$OUT" -resize "${SCALE}x" "$OUT" 2>/dev/null || true; fi
echo "win=$W title=$(xdotool getwindowname "$W") pos=$X,$Y size=${WD}x${HT} -> $OUT"
identify "$OUT" | cut -d' ' -f3

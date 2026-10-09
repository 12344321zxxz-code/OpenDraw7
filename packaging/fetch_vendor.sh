#!/bin/bash
# Downloads the small X11 helper libraries that Qt's X11 plugin needs but that many
# desktops do not install by default (libxcb-cursor0 above all). They are taken from
# Ubuntu 22.04 so that they also load on older systems. All are MIT/X11 licensed.
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
out="$here/vendor"
tmp="$(mktemp -d)"
base="http://archive.ubuntu.com/ubuntu"
debs=(
  pool/universe/x/xcb-util-cursor/libxcb-cursor0_0.1.1-4ubuntu1_amd64.deb
  pool/main/x/xcb-util-wm/libxcb-icccm4_0.4.1-1.1build2_amd64.deb
  pool/main/x/xcb-util-image/libxcb-image0_0.4.0-2_amd64.deb
  pool/main/x/xcb-util-keysyms/libxcb-keysyms1_0.4.0-1build3_amd64.deb
  pool/main/x/xcb-util-renderutil/libxcb-render-util0_0.3.9-1build3_amd64.deb
  pool/main/x/xcb-util/libxcb-util1_0.4.0-1build2_amd64.deb
  pool/main/libx/libxkbcommon/libxkbcommon-x11-0_1.4.0-1_amd64.deb
  pool/main/libx/libxcb/libxcb-xinerama0_1.14-3ubuntu3_amd64.deb
  pool/main/libx/libxcb/libxcb-xinput0_1.14-3ubuntu3_amd64.deb
  pool/main/libx/libxcb/libxcb-shape0_1.14-3ubuntu3_amd64.deb
  pool/main/libx/libxcb/libxcb-xkb1_1.14-3ubuntu3_amd64.deb
)
mkdir -p "$out/lib" "$out/licenses" "$tmp/root"
for d in "${debs[@]}"; do
  f="$tmp/$(basename "$d")"
  curl -fsS -m 120 -o "$f" "$base/$d"
  dpkg-deb -x "$f" "$tmp/root"
done
cp -L "$tmp"/root/usr/lib/x86_64-linux-gnu/*.so.[0-9] "$out/lib/"
for p in "$tmp"/root/usr/share/doc/*; do
  [ -f "$p/copyright" ] && cp "$p/copyright" "$out/licenses/$(basename "$p").txt"
done
rm -rf "$tmp"
ls -1 "$out/lib"

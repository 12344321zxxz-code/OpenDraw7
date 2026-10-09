#!/bin/sh
# Installs OpenDraw7 for the current user (no root needed) and adds it to the app menu.
set -e
here="$(cd "$(dirname "$0")" && pwd)"
dest="${XDG_DATA_HOME:-$HOME/.local/share}/opendraw7"
apps="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
icons="${XDG_DATA_HOME:-$HOME/.local/share}/icons/hicolor/256x256/apps"
bin="$HOME/.local/bin"

if [ ! -x "$here/opendraw7" ]; then
  echo "Run this script from inside the unpacked OpenDraw7 folder." >&2
  exit 1
fi
rm -rf "$dest"
mkdir -p "$dest" "$apps" "$icons" "$bin"
cp -R "$here/opendraw7" "$here/_internal" "$dest/"
cp "$here/opendraw7.png" "$icons/opendraw7.png"
sed "s|@EXEC@|\"$dest/opendraw7\"|" "$here/opendraw7.desktop" > "$apps/opendraw7.desktop"
ln -sf "$dest/opendraw7" "$bin/opendraw7"
command -v update-desktop-database >/dev/null 2>&1 && update-desktop-database "$apps" >/dev/null 2>&1 || true
command -v gtk-update-icon-cache >/dev/null 2>&1 && gtk-update-icon-cache -q "${XDG_DATA_HOME:-$HOME/.local/share}/icons/hicolor" >/dev/null 2>&1 || true
echo "OpenDraw7 is installed. Find it in your applications menu, or run: $bin/opendraw7"

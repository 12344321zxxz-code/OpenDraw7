#!/bin/sh
# Removes what install.sh put in place. Your pictures and settings are not touched.
data="${XDG_DATA_HOME:-$HOME/.local/share}"
rm -rf "$data/opendraw7"
rm -f "$data/applications/opendraw7.desktop" "$data/icons/hicolor/256x256/apps/opendraw7.png" "$HOME/.local/bin/opendraw7"
echo "OpenDraw7 has been removed."

#!/bin/bash

# Vitis_HLS/xxx.x/common/scripts/autopilot_init.tcl is a Tcl script obfuscated
# with a ROT13-like cipher. This script replaces the value of the use_start_gui
# variable from 0 to 1 to fix the startup errors in vitis_hls.
# Credits to @edmeme from https://aur.archlinux.org/packages/vivado

MATCH="%r&\-'%rl%&n\$&lt'v\-"
AUTOPILOT_INIT_TCL_PATH="$(dirname "$(which vitis_hls)")"/../common/scripts/autopilot_init.tcl

if [ ! -f "$AUTOPILOT_INIT_TCL_PATH.bak" ]; then
    echo "Patching $AUTOPILOT_INIT_TCL_PATH (backup in $AUTOPILOT_INIT_TCL_PATH.bak)"
    cp "$AUTOPILOT_INIT_TCL_PATH" "$AUTOPILOT_INIT_TCL_PATH.bak"
    sed -i "s/\($MATCH\)=$/\1>/" "$AUTOPILOT_INIT_TCL_PATH"
fi

#!/bin/bash

# In Vitis/<version>/eclipse/lnx64.o/plugins/com.xilinx.sdk.utils_*.jar, an
# incorrect file filter is specified for the file chooser, which is not accepted
# by xdg-desktop-portal, causing the lack of the XSA selection window.
# Patch it by simply replacing "*dsa;" to "**.dsa" in HwSpecFile.class.

set -euo pipefail

if [ "$#" -ne 1 ]; then
	echo "Usage: $0 path/to/Vitis/installation/folder" >&2
	exit 1
fi

jar_files=( "$1/eclipse/lnx64.o/plugins/com.xilinx.sdk.utils_"*.jar )
jar_file="${jar_files[0]}"

tempdir=$(mktemp -d)
cd "$tempdir"

# Extract the JAR and replace the incorrect filter
unzip -q "$jar_file"
sed 's/*.dsa;/**.dsa/' "com/xilinx/sdk/utils/HwSpecFile.class" > "com/xilinx/sdk/utils/HwSpecFile.class.patched"

if diff -q "com/xilinx/sdk/utils/HwSpecFile.class" "com/xilinx/sdk/utils/HwSpecFile.class.patched" > /dev/null; then
	# Nothing to do
	echo "HwSpecFile.class in $jar_file does not need to be patched"
else
	# Rebuild the jar
	mv "com/xilinx/sdk/utils/HwSpecFile.class.patched" "com/xilinx/sdk/utils/HwSpecFile.class"
	mv "$jar_file" "$jar_file.bak"
	zip -qr "$jar_file" .
	echo "HwSpecFile.class in $jar_file patched, saved a backup in $jar_file.bak"
fi

rm -rf "$tempdir"

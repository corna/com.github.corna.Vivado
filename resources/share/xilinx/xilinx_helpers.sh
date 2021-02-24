#/bin/bash

if [ -z "$XILINX_INSTALL_PATH" ]; then
	XILINX_INSTALL_PATH="$XDG_DATA_HOME/xilinx"
fi

function xilinx_install() {
	if [ -f "$XILINX_INSTALL_PATH/.xinstall/xic/xsetup" ]; then
		installer_path="$XILINX_INSTALL_PATH/.xinstall/xic/xsetup"
	else
		zenity --width=600 --info --title "Missing xsetup" --text "xsetup is not installed. Please download the Xilinx Unified installer and select it in the next window."

		# Launch the browser
		xdg-open 'https://www.xilinx.com/support/download.html'

		# Get the installer path
		installer_path=$(zenity --file-selection --title "Select the Xilinx installer (Xilinx_Unified_*_Lin64.bin)")

		zenity --width=600 --warning --text "The Xilinx installer will now start. Make sure to select $XILINX_INSTALL_PATH as installation path."
		mkdir -p "$XILINX_INSTALL_PATH"
	fi

	# Run the installer
	sh "$installer_path"

	zenity --width=600 --info --text "Installation is complete.\nTo allow access to the hardware devices (necessary to program them within Vivado and Vitis), run <b>sudo $XILINX_INSTALL_PATH/Vivado/2020.2/data/xicom/cable_drivers/lin64/install_script/install_drivers/install_drivers &amp;&amp; sudo udevadm control --reload</b>, then reconnect all the devices (if any)"
}

function xilinx_install_if_needed() {
	if [ ! -f "$XILINX_INSTALL_PATH/$1" ]; then
		zenity --width=400 --question --title "Missing software" --text "$(basename $1) is not installed. Do you want to install it now?" && xilinx_install
	fi
}

function xilinx_install_if_needed_then_run() {
	command="$1"
	shift

	xilinx_install_if_needed "$command"

	SETTINGS64_DIR=$(mktemp -d)

	# Fix the paths in .settings64*.sh (so that the installation can be freely moved)
	find "$XILINX_INSTALL_PATH" -maxdepth 3 -name ".settings64*.sh" -exec cp {} "$SETTINGS64_DIR" \;
	find "$SETTINGS64_DIR" -type f -exec sed -i -E "s@=.*/(Vivado|Vitis|DocNav)@=$XILINX_INSTALL_PATH/\1@g" {} \;

	# Replace the absolute paths in Vivado/*/settings64.sh with relative ones
	sed "s|source .*/.settings64|source $SETTINGS64_DIR/.settings64|g" "$XILINX_INSTALL_PATH/Vivado/2020.2/settings64.sh" > "$SETTINGS64_DIR/settings64.sh"

	. "$SETTINGS64_DIR/settings64.sh"
	rm -rf "$SETTINGS64_DIR"

	"$XILINX_INSTALL_PATH/$command" "$@"
}
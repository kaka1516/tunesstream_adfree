#!/data/data/com.termux/files/usr/bin/sh
# Termux:Boot template (ms-v75): copy to ~/.termux/boot/ (install.sh --autostart does it). Needs the Termux:Boot app.
termux-wake-lock
cd "@DIR@" && ./start.sh

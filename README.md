# ADB Control Center

Linux desktop GUI for Android Debug Bridge.

## License

MIT. See [LICENSE](./LICENSE).

## Run

```bash
cd ~/adb-gui
./run.sh
```

ADB must be installed and in the path. 

## Features

- Device discovery with `adb devices -l`
- Start and kill ADB server
- Select a connected USB or wireless device
- Wireless ADB connect, pair, disconnect, and `adb tcpip`
- Reboot, reboot recovery, reboot bootloader, and reboot sideload
- Install one APK or multiple APK splits
- List packages, uninstall packages, clear app data, and force-stop apps
- Push files/folders and pull files/folders
- Run shell commands and common quick shell checks
- Dump or follow logcat, with optional logcat arguments
- Save logcat dumps and Android bugreports
- Save the full output pane or selected output lines
- Take screenshots
- Record screen clips
- Trigger Android input keys
- Create an ADB backup file
- Run raw ADB commands for anything not exposed as a button

Generated logs, bugreports, screenshots, screen recordings, and backups are saved to:

```text
~/adb-gui-output
```

## Notes

Some commands require a device to be authorized for USB debugging. Android may show a confirmation prompt on the device the first time it connects.

#!/usr/bin/env python3
import os
import queue
import shlex
import subprocess
import threading
import time
from pathlib import Path
from tkinter import (
    BOTH,
    END,
    LEFT,
    RIGHT,
    VERTICAL,
    X,
    Y,
    BooleanVar,
    Button,
    Entry,
    Frame,
    Label,
    LabelFrame,
    Listbox,
    Menu,
    PanedWindow,
    StringVar,
    Toplevel,
    Tk,
    filedialog,
    messagebox,
)
from tkinter import ttk


APP_TITLE = "ADB Control Center"
OUTPUT_DIR = Path.home() / "adb-gui-output"


class AdbGui:
    def __init__(self, root):
        self.root = root
        self.root.title(APP_TITLE)
        self.root.geometry("1180x760")
        self.root.minsize(980, 640)

        self.adb_path = StringVar(value=self.find_adb())
        self.selected_device = StringVar(value="")
        self.status = StringVar(value="Ready")
        self.tcpip_port = StringVar(value="5555")
        self.connect_target = StringVar(value="")
        self.package_name = StringVar(value="")
        self.shell_command = StringVar(value="getprop ro.build.version.release")
        self.raw_command = StringVar(value="devices -l")
        self.logcat_filter = StringVar(value="")
        self.follow_logcat = BooleanVar(value=False)
        self.command_queue = queue.Queue()
        self.logcat_process = None
        self.logcat_thread = None

        OUTPUT_DIR.mkdir(exist_ok=True)
        self.build_ui()
        self.refresh_devices()
        self.root.after(100, self.drain_queue)

    def find_adb(self):
        for candidate in ("/usr/bin/adb", "/bin/adb"):
            if Path(candidate).exists():
                return candidate
        return "adb"

    def build_ui(self):
        self.root.option_add("*Font", "TkDefaultFont 10")

        toolbar = Frame(self.root, padx=8, pady=6)
        toolbar.pack(fill=X)

        Label(toolbar, text="ADB").pack(side=LEFT)
        Entry(toolbar, textvariable=self.adb_path, width=34).pack(side=LEFT, padx=(6, 8))
        Button(toolbar, text="Refresh", command=self.refresh_devices).pack(side=LEFT)
        Button(toolbar, text="Start Server", command=lambda: self.run_adb(["start-server"])).pack(side=LEFT, padx=(8, 0))
        Button(toolbar, text="Kill Server", command=lambda: self.run_adb(["kill-server"])).pack(side=LEFT, padx=(6, 0))
        Label(toolbar, textvariable=self.status, anchor="e").pack(side=RIGHT)

        main = PanedWindow(self.root, orient="horizontal", sashrelief="raised")
        main.pack(fill=BOTH, expand=True)

        left = Frame(main, padx=8, pady=8)
        main.add(left, minsize=280)

        right = Frame(main, padx=8, pady=8)
        main.add(right, minsize=650)

        self.build_device_panel(left)
        self.build_tabs(right)
        self.build_output(right)

    def build_device_panel(self, parent):
        box = LabelFrame(parent, text="Devices", padx=8, pady=8)
        box.pack(fill=BOTH, expand=True)

        self.device_list = Listbox(box, height=12, exportselection=False)
        self.device_list.pack(fill=BOTH, expand=True)
        self.device_list.bind("<<ListboxSelect>>", self.on_device_select)

        buttons = Frame(box, pady=8)
        buttons.pack(fill=X)
        Button(buttons, text="Refresh", command=self.refresh_devices).pack(side=LEFT)
        Button(buttons, text="Info", command=self.device_info).pack(side=LEFT, padx=6)

        net = LabelFrame(parent, text="Wireless ADB", padx=8, pady=8)
        net.pack(fill=X, pady=(8, 0))
        Label(net, text="host:port or pair host:port").pack(anchor="w")
        Entry(net, textvariable=self.connect_target).pack(fill=X, pady=(2, 6))
        row = Frame(net)
        row.pack(fill=X)
        Button(row, text="Connect", command=self.connect_device).pack(side=LEFT)
        Button(row, text="Pair", command=self.pair_device).pack(side=LEFT, padx=6)
        Button(row, text="Disconnect", command=self.disconnect_device).pack(side=LEFT)
        port_row = Frame(net, pady=6)
        port_row.pack(fill=X)
        Label(port_row, text="TCP/IP port").pack(side=LEFT)
        Entry(port_row, textvariable=self.tcpip_port, width=8).pack(side=LEFT, padx=6)
        Button(port_row, text="Enable", command=self.enable_tcpip).pack(side=LEFT)

        power = LabelFrame(parent, text="Power / Boot", padx=8, pady=8)
        power.pack(fill=X, pady=(8, 0))
        for label, mode in (
            ("Reboot", None),
            ("Recovery", "recovery"),
            ("Bootloader", "bootloader"),
            ("Sideload", "sideload"),
        ):
            Button(power, text=label, command=lambda m=mode: self.reboot(m)).pack(fill=X, pady=2)

    def build_tabs(self, parent):
        self.tabs = ttk.Notebook(parent)
        self.tabs.pack(fill=BOTH, expand=True)

        self.tab_apps = Frame(self.tabs, padx=8, pady=8)
        self.tab_files = Frame(self.tabs, padx=8, pady=8)
        self.tab_shell = Frame(self.tabs, padx=8, pady=8)
        self.tab_media = Frame(self.tabs, padx=8, pady=8)
        self.tab_logs = Frame(self.tabs, padx=8, pady=8)
        self.tab_raw = Frame(self.tabs, padx=8, pady=8)

        self.tabs.add(self.tab_apps, text="Apps")
        self.tabs.add(self.tab_files, text="Files")
        self.tabs.add(self.tab_shell, text="Shell")
        self.tabs.add(self.tab_media, text="Screen")
        self.tabs.add(self.tab_logs, text="Logcat")
        self.tabs.add(self.tab_raw, text="Raw ADB")

        self.build_apps_tab()
        self.build_files_tab()
        self.build_shell_tab()
        self.build_screen_tab()
        self.build_logs_tab()
        self.build_raw_tab()

    def build_apps_tab(self):
        apk = LabelFrame(self.tab_apps, text="APK", padx=8, pady=8)
        apk.pack(fill=X)
        Button(apk, text="Install APK", command=self.install_apk).pack(side=LEFT)
        Button(apk, text="Install Multiple APKs", command=self.install_multiple_apks).pack(side=LEFT, padx=6)

        pkg = LabelFrame(self.tab_apps, text="Packages", padx=8, pady=8)
        pkg.pack(fill=X, pady=(8, 0))
        Entry(pkg, textvariable=self.package_name).pack(side=LEFT, fill=X, expand=True)
        Button(pkg, text="List Packages", command=self.list_packages).pack(side=LEFT, padx=6)
        Button(pkg, text="Uninstall", command=self.uninstall_package).pack(side=LEFT)
        Button(pkg, text="Clear Data", command=self.clear_package).pack(side=LEFT, padx=6)
        Button(pkg, text="Force Stop", command=self.force_stop_package).pack(side=LEFT)

    def build_files_tab(self):
        actions = LabelFrame(self.tab_files, text="File Transfer", padx=8, pady=8)
        actions.pack(fill=X)
        Button(actions, text="Push File/Folder", command=self.push_path).pack(side=LEFT)
        Button(actions, text="Pull From Device", command=self.pull_path).pack(side=LEFT, padx=6)
        Button(actions, text="List /sdcard", command=lambda: self.shell("ls -la /sdcard")).pack(side=LEFT)

        backup = LabelFrame(self.tab_files, text="Backup", padx=8, pady=8)
        backup.pack(fill=X, pady=(8, 0))
        Button(backup, text="ADB Backup APK + Shared", command=self.backup_device).pack(side=LEFT)
        Label(backup, text=f"Saved in {OUTPUT_DIR}").pack(side=LEFT, padx=10)

    def build_shell_tab(self):
        command = LabelFrame(self.tab_shell, text="Shell Command", padx=8, pady=8)
        command.pack(fill=X)
        Entry(command, textvariable=self.shell_command).pack(side=LEFT, fill=X, expand=True)
        Button(command, text="Run", command=lambda: self.shell(self.shell_command.get())).pack(side=LEFT, padx=6)

        quick = LabelFrame(self.tab_shell, text="Quick Commands", padx=8, pady=8)
        quick.pack(fill=X, pady=(8, 0))
        commands = [
            ("Build Props", "getprop"),
            ("Battery", "dumpsys battery"),
            ("Storage", "df -h"),
            ("IP Addr", "ip addr"),
            ("Settings", "settings list global"),
            ("Processes", "ps -A"),
        ]
        for label, command_text in commands:
            Button(quick, text=label, command=lambda c=command_text: self.shell(c)).pack(side=LEFT, padx=(0, 6), pady=2)

    def build_screen_tab(self):
        screen = LabelFrame(self.tab_media, text="Capture", padx=8, pady=8)
        screen.pack(fill=X)
        Button(screen, text="Screenshot", command=self.screenshot).pack(side=LEFT)
        Button(screen, text="Screen Record 10s", command=lambda: self.screenrecord(10)).pack(side=LEFT, padx=6)
        Button(screen, text="Screen Record 30s", command=lambda: self.screenrecord(30)).pack(side=LEFT)

        input_box = LabelFrame(self.tab_media, text="Input", padx=8, pady=8)
        input_box.pack(fill=X, pady=(8, 0))
        Button(input_box, text="Home", command=lambda: self.shell("input keyevent HOME")).pack(side=LEFT)
        Button(input_box, text="Back", command=lambda: self.shell("input keyevent BACK")).pack(side=LEFT, padx=6)
        Button(input_box, text="Recent Apps", command=lambda: self.shell("input keyevent APP_SWITCH")).pack(side=LEFT)
        Button(input_box, text="Power", command=lambda: self.shell("input keyevent POWER")).pack(side=LEFT, padx=6)
        Button(input_box, text="Wake", command=lambda: self.shell("input keyevent WAKEUP")).pack(side=LEFT)

    def build_logs_tab(self):
        controls = LabelFrame(self.tab_logs, text="Logcat", padx=8, pady=8)
        controls.pack(fill=X)
        Entry(controls, textvariable=self.logcat_filter).pack(side=LEFT, fill=X, expand=True)
        Button(controls, text="Dump", command=self.logcat_dump).pack(side=LEFT, padx=6)
        Button(controls, text="Save Dump", command=self.save_logcat_dump).pack(side=LEFT)
        Button(controls, text="Follow", command=self.start_logcat).pack(side=LEFT)
        Button(controls, text="Stop", command=self.stop_logcat).pack(side=LEFT, padx=6)
        Button(controls, text="Clear", command=lambda: self.run_device_adb(["logcat", "-c"])).pack(side=LEFT)
        Button(controls, text="Bugreport", command=self.bugreport).pack(side=LEFT, padx=6)

    def build_raw_tab(self):
        raw = LabelFrame(self.tab_raw, text="Run Any ADB Arguments", padx=8, pady=8)
        raw.pack(fill=X)
        Entry(raw, textvariable=self.raw_command).pack(side=LEFT, fill=X, expand=True)
        Button(raw, text="Run", command=self.run_raw).pack(side=LEFT, padx=6)
        Label(self.tab_raw, text="Examples: devices -l | shell id | shell pm list packages | pull /sdcard/file.txt").pack(anchor="w", pady=8)

    def build_output(self, parent):
        out = LabelFrame(parent, text="Output", padx=8, pady=8)
        out.pack(fill=BOTH, expand=True, pady=(8, 0))
        wrap = Frame(out)
        wrap.pack(fill=BOTH, expand=True)
        self.output = Listbox(wrap, font=("TkFixedFont", 10), selectmode="extended")
        scrollbar = ttk.Scrollbar(wrap, orient=VERTICAL, command=self.output.yview)
        self.output.configure(yscrollcommand=scrollbar.set)
        self.output.pack(side=LEFT, fill=BOTH, expand=True)
        scrollbar.pack(side=RIGHT, fill=Y)
        bottom = Frame(out, pady=6)
        bottom.pack(fill=X)
        Button(bottom, text="Clear Output", command=lambda: self.output.delete(0, END)).pack(side=LEFT)
        Button(bottom, text="Save Output", command=self.save_output).pack(side=LEFT, padx=6)
        Button(bottom, text="Save Selection", command=lambda: self.save_output(selection_only=True)).pack(side=LEFT)
        Button(bottom, text="Open Output Folder", command=self.open_output_folder).pack(side=LEFT, padx=6)

    def adb_base(self):
        return [self.adb_path.get().strip() or "adb"]

    def device_args(self):
        device = self.selected_device.get().strip()
        return ["-s", device] if device else []

    def run_async(self, args, label=None, cwd=None, device=False):
        command = self.adb_base()
        if device:
            command += self.device_args()
        command += args
        title = label or " ".join(shlex.quote(part) for part in command)
        self.append(f"$ {title}")
        self.status.set("Running")

        def worker():
            try:
                proc = subprocess.run(
                    command,
                    cwd=cwd,
                    text=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    check=False,
                )
                if proc.stdout:
                    for line in proc.stdout.splitlines():
                        self.command_queue.put(("line", line))
                self.command_queue.put(("line", f"[exit {proc.returncode}]"))
            except FileNotFoundError:
                self.command_queue.put(("line", "adb was not found. Update the ADB path at the top."))
            except Exception as exc:
                self.command_queue.put(("line", f"Error: {exc}"))
            finally:
                self.command_queue.put(("status", "Ready"))

        threading.Thread(target=worker, daemon=True).start()

    def run_adb(self, args):
        self.run_async(args)

    def run_device_adb(self, args):
        self.run_async(args, device=True)

    def run_device_sequence(self, command_list, label):
        device = self.device_args()
        commands = [self.adb_base() + device + args for args in command_list]
        self.append(f"$ {label}")
        self.status.set("Running")

        def worker():
            try:
                for command in commands:
                    self.command_queue.put(("line", "$ " + " ".join(shlex.quote(part) for part in command)))
                    proc = subprocess.run(
                        command,
                        text=True,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.STDOUT,
                        check=False,
                    )
                    if proc.stdout:
                        for line in proc.stdout.splitlines():
                            self.command_queue.put(("line", line))
                    self.command_queue.put(("line", f"[exit {proc.returncode}]"))
                    if proc.returncode != 0:
                        break
            except FileNotFoundError:
                self.command_queue.put(("line", "adb was not found. Update the ADB path at the top."))
            except Exception as exc:
                self.command_queue.put(("line", f"Error: {exc}"))
            finally:
                self.command_queue.put(("status", "Ready"))

        threading.Thread(target=worker, daemon=True).start()

    def run_to_file(self, args, path, label=None, device=False):
        command = self.adb_base()
        if device:
            command += self.device_args()
        command += args
        title = label or " ".join(shlex.quote(part) for part in command)
        self.append(f"$ {title}")
        self.append(f"[saving to {path}]")
        self.status.set("Saving")

        def worker():
            try:
                with open(path, "w", encoding="utf-8", errors="replace") as handle:
                    proc = subprocess.run(
                        command,
                        text=True,
                        stdout=handle,
                        stderr=subprocess.STDOUT,
                        check=False,
                    )
                self.command_queue.put(("line", f"[saved {path}]"))
                self.command_queue.put(("line", f"[exit {proc.returncode}]"))
            except FileNotFoundError:
                self.command_queue.put(("line", "adb was not found. Update the ADB path at the top."))
            except Exception as exc:
                self.command_queue.put(("line", f"Error: {exc}"))
            finally:
                self.command_queue.put(("status", "Ready"))

        threading.Thread(target=worker, daemon=True).start()

    def run_raw(self):
        try:
            args = shlex.split(self.raw_command.get())
        except ValueError as exc:
            messagebox.showerror(APP_TITLE, str(exc))
            return
        self.run_adb(args)

    def shell(self, command):
        if not command.strip():
            return
        self.run_device_adb(["shell", command])

    def refresh_devices(self):
        self.run_async(["devices", "-l"], label="adb devices -l")
        threading.Thread(target=self.load_devices, daemon=True).start()

    def load_devices(self):
        try:
            proc = subprocess.run(
                self.adb_base() + ["devices", "-l"],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                check=False,
            )
            devices = []
            for line in proc.stdout.splitlines()[1:]:
                if not line.strip():
                    continue
                parts = line.split()
                if len(parts) >= 2:
                    devices.append((parts[0], line))
            self.command_queue.put(("devices", devices))
        except Exception as exc:
            self.command_queue.put(("line", f"Could not load devices: {exc}"))

    def on_device_select(self, _event=None):
        selection = self.device_list.curselection()
        if not selection:
            return
        line = self.device_list.get(selection[0])
        self.selected_device.set(line.split()[0])
        self.status.set(f"Selected {self.selected_device.get()}")

    def set_devices(self, devices):
        current = self.selected_device.get()
        self.device_list.delete(0, END)
        selected_index = None
        for index, (_serial, line) in enumerate(devices):
            self.device_list.insert(END, line)
            if line.startswith(current):
                selected_index = index
        if selected_index is not None:
            self.device_list.selection_set(selected_index)
        elif devices:
            self.device_list.selection_set(0)
            self.selected_device.set(devices[0][0])

    def connect_device(self):
        target = self.connect_target.get().strip()
        if target:
            self.run_adb(["connect", target])

    def pair_device(self):
        target = self.connect_target.get().strip()
        if not target:
            return
        code = self.prompt("Pairing Code", "Enter pairing code")
        if code:
            self.run_adb(["pair", target, code])

    def disconnect_device(self):
        target = self.connect_target.get().strip()
        self.run_adb(["disconnect", target] if target else ["disconnect"])

    def enable_tcpip(self):
        port = self.tcpip_port.get().strip() or "5555"
        self.run_device_adb(["tcpip", port])

    def reboot(self, mode):
        args = ["reboot"]
        if mode:
            args.append(mode)
        self.run_device_adb(args)

    def device_info(self):
        self.shell("getprop ro.product.manufacturer; getprop ro.product.model; getprop ro.build.version.release; getprop ro.build.fingerprint")

    def install_apk(self):
        path = filedialog.askopenfilename(title="Select APK", filetypes=[("Android packages", "*.apk"), ("All files", "*")])
        if path:
            self.run_device_adb(["install", "-r", path])

    def install_multiple_apks(self):
        paths = filedialog.askopenfilenames(title="Select APKs", filetypes=[("Android packages", "*.apk"), ("All files", "*")])
        if paths:
            self.run_device_adb(["install-multiple", *paths])

    def list_packages(self):
        self.run_device_adb(["shell", "pm list packages -f"])

    def uninstall_package(self):
        package = self.package_name.get().strip()
        if package and messagebox.askyesno(APP_TITLE, f"Uninstall {package}?"):
            self.run_device_adb(["uninstall", package])

    def clear_package(self):
        package = self.package_name.get().strip()
        if package and messagebox.askyesno(APP_TITLE, f"Clear all data for {package}?"):
            self.run_device_adb(["shell", f"pm clear {shlex.quote(package)}"])

    def force_stop_package(self):
        package = self.package_name.get().strip()
        if package:
            self.run_device_adb(["shell", f"am force-stop {shlex.quote(package)}"])

    def push_path(self):
        path = filedialog.askopenfilename(title="Select file to push")
        if not path:
            directory = filedialog.askdirectory(title="Or select folder to push")
            path = directory
        if path:
            dest = self.prompt("Push Destination", "Device path", "/sdcard/Download/")
            if dest:
                self.run_device_adb(["push", path, dest])

    def pull_path(self):
        source = self.prompt("Pull From Device", "Device path", "/sdcard/Download/")
        if not source:
            return
        dest = filedialog.askdirectory(title="Choose local destination", initialdir=str(OUTPUT_DIR))
        if dest:
            self.run_device_adb(["pull", source, dest])

    def backup_device(self):
        path = OUTPUT_DIR / f"backup-{time.strftime('%Y%m%d-%H%M%S')}.ab"
        self.run_device_adb(["backup", "-apk", "-shared", "-all", "-f", str(path)])

    def screenshot(self):
        remote = "/sdcard/adb-gui-screenshot.png"
        local = OUTPUT_DIR / f"screenshot-{time.strftime('%Y%m%d-%H%M%S')}.png"
        self.run_device_sequence(
            [
                ["shell", "screencap", "-p", remote],
                ["pull", remote, str(local)],
                ["shell", "rm", remote],
            ],
            f"save screenshot to {local}",
        )

    def screenrecord(self, seconds):
        remote = "/sdcard/adb-gui-screenrecord.mp4"
        local = OUTPUT_DIR / f"screenrecord-{time.strftime('%Y%m%d-%H%M%S')}.mp4"
        self.run_device_sequence(
            [
                ["shell", f"screenrecord --time-limit {int(seconds)} {remote}"],
                ["pull", remote, str(local)],
                ["shell", "rm", remote],
            ],
            f"save screen recording to {local}",
        )

    def logcat_dump(self):
        filt = self.logcat_filter.get().strip()
        args = ["logcat", "-d"]
        if filt:
            try:
                args += shlex.split(filt)
            except ValueError as exc:
                messagebox.showerror(APP_TITLE, str(exc))
                return
        self.run_device_adb(args)

    def save_logcat_dump(self):
        filt = self.logcat_filter.get().strip()
        args = ["logcat", "-d"]
        if filt:
            try:
                args += shlex.split(filt)
            except ValueError as exc:
                messagebox.showerror(APP_TITLE, str(exc))
                return
        path = OUTPUT_DIR / f"logcat-{time.strftime('%Y%m%d-%H%M%S')}.txt"
        self.run_to_file(args, path, label=f"save logcat dump to {path}", device=True)

    def bugreport(self):
        path = OUTPUT_DIR / f"bugreport-{time.strftime('%Y%m%d-%H%M%S')}.zip"
        self.run_device_adb(["bugreport", str(path)])

    def start_logcat(self):
        if self.logcat_process and self.logcat_process.poll() is None:
            return
        args = self.adb_base() + self.device_args() + ["logcat"]
        filt = self.logcat_filter.get().strip()
        if filt:
            try:
                args += shlex.split(filt)
            except ValueError as exc:
                messagebox.showerror(APP_TITLE, str(exc))
                return
        self.append("$ " + " ".join(shlex.quote(part) for part in args))
        self.status.set("Following logcat")

        def reader():
            try:
                self.logcat_process = subprocess.Popen(
                    args,
                    text=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    bufsize=1,
                )
                for line in self.logcat_process.stdout:
                    self.command_queue.put(("line", line.rstrip()))
            except Exception as exc:
                self.command_queue.put(("line", f"Logcat error: {exc}"))
            finally:
                self.command_queue.put(("status", "Ready"))

        self.logcat_thread = threading.Thread(target=reader, daemon=True)
        self.logcat_thread.start()

    def stop_logcat(self):
        if self.logcat_process and self.logcat_process.poll() is None:
            self.logcat_process.terminate()
            self.append("[logcat stopped]")
        self.status.set("Ready")

    def open_output_folder(self):
        subprocess.Popen(["xdg-open", str(OUTPUT_DIR)])

    def save_output(self, selection_only=False):
        if selection_only:
            indexes = self.output.curselection()
            if not indexes:
                messagebox.showinfo(APP_TITLE, "Select output lines to save first.")
                return
            lines = [self.output.get(index) for index in indexes]
            default_name = f"adb-output-selection-{time.strftime('%Y%m%d-%H%M%S')}.txt"
        else:
            lines = list(self.output.get(0, END))
            default_name = f"adb-output-{time.strftime('%Y%m%d-%H%M%S')}.txt"

        if not lines:
            messagebox.showinfo(APP_TITLE, "There is no output to save yet.")
            return

        path = filedialog.asksaveasfilename(
            title="Save Output",
            initialdir=str(OUTPUT_DIR),
            initialfile=default_name,
            defaultextension=".txt",
            filetypes=[("Text files", "*.txt"), ("Log files", "*.log"), ("All files", "*")],
        )
        if not path:
            return

        try:
            with open(path, "w", encoding="utf-8") as handle:
                handle.write("\n".join(lines))
                handle.write("\n")
            self.append(f"[saved output to {path}]")
        except Exception as exc:
            messagebox.showerror(APP_TITLE, f"Could not save output: {exc}")

    def prompt(self, title, label, default=""):
        dialog = TkPrompt(self.root, title, label, default)
        self.root.wait_window(dialog.top)
        return dialog.value

    def append(self, line):
        self.output.insert(END, line)
        self.output.yview_moveto(1)

    def drain_queue(self):
        while True:
            try:
                kind, payload = self.command_queue.get_nowait()
            except queue.Empty:
                break
            if kind == "line":
                self.append(payload)
            elif kind == "status":
                self.status.set(payload)
            elif kind == "devices":
                self.set_devices(payload)
        self.root.after(100, self.drain_queue)


class TkPrompt:
    def __init__(self, parent, title, label, default=""):
        self.value = None
        self.top = Toplevel(parent)
        self.top.title(title)
        self.top.transient(parent)
        self.top.grab_set()
        self.top.resizable(False, False)

        frame = Frame(self.top, padx=12, pady=12)
        frame.pack(fill=BOTH, expand=True)
        Label(frame, text=label).pack(anchor="w")
        self.entry = Entry(frame, width=52)
        self.entry.insert(0, default)
        self.entry.pack(fill=X, pady=(4, 10))

        buttons = Frame(frame)
        buttons.pack(fill=X)
        Button(buttons, text="Cancel", command=self.cancel).pack(side=RIGHT)
        Button(buttons, text="OK", command=self.ok).pack(side=RIGHT, padx=(0, 6))
        self.entry.bind("<Return>", lambda _event: self.ok())
        self.entry.focus_set()

    def ok(self):
        self.value = self.entry.get()
        self.top.destroy()

    def cancel(self):
        self.value = None
        self.top.destroy()


def main():
    root = Tk()
    app = AdbGui(root)
    root.protocol("WM_DELETE_WINDOW", lambda: (app.stop_logcat(), root.destroy()))
    root.mainloop()


if __name__ == "__main__":
    main()

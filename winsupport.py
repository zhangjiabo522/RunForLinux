"""Windows Run compatibility helpers for Linux."""

import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import urllib.parse
from pathlib import Path
from typing import NamedTuple, Optional, Tuple


class LaunchPlan(NamedTuple):
    kind: str
    argv: Tuple[str, ...] = ()
    target: str = ""
    title: str = ""
    message: str = ""
    cwd: Optional[str] = None


def process_plan(argv, cwd=None):
    if isinstance(argv, str):
        argv = (argv,)
    return LaunchPlan("process", tuple(argv), cwd=cwd)


def open_plan(target):
    return LaunchPlan("open", target=target)


def info_plan(title, message):
    return LaunchPlan("info", title=title, message=message)


def error_plan(message):
    return LaunchPlan("error", message=message)


class RunResolver:
    """Translate common Windows Run commands into Linux launch actions."""

    GUI_ALIASES = {
        "calc": ("gnome-calculator", "kcalc", "xcalc"),
        "calc.exe": ("gnome-calculator", "kcalc", "xcalc"),
        "calculator": ("gnome-calculator", "kcalc", "xcalc"),
        "charmap": ("gnome-characters", "gucharmap"),
        "charmap.exe": ("gnome-characters", "gucharmap"),
        "cleanmgr": ("baobab",),
        "cleanmgr.exe": ("baobab",),
        "compmgmt.msc": ("gnome-system-monitor",),
        "dfrgui": ("gnome-disks",),
        "dfrgui.exe": ("gnome-disks",),
        "diskmgmt.msc": ("gnome-disks",),
        "eventvwr": ("gnome-logs",),
        "eventvwr.exe": ("gnome-logs",),
        "eventvwr.msc": ("gnome-logs",),
        "explorer": (),
        "explorer.exe": (),
        "fsmgmt.msc": ("nautilus", "nemo", "dolphin"),
        "logoff": ("gnome-session-quit", "--logout", "--no-prompt"),
        "magnify": ("gnome-control-center", "universal-access"),
        "msconfig": ("gnome-session-properties",),
        "msconfig.exe": ("gnome-session-properties",),
        "mspaint": (),
        "mspaint.exe": (),
        "notepad": ("gnome-text-editor", "gedit", "kate", "mousepad"),
        "notepad.exe": ("gnome-text-editor", "gedit", "kate", "mousepad"),
        "osk": ("gnome-control-center", "universal-access"),
        "perfmon": ("gnome-system-monitor",),
        "perfmon.exe": ("gnome-system-monitor",),
        "perfmon.msc": ("gnome-system-monitor",),
        "taskmgr": ("gnome-system-monitor", "ksysguard"),
        "taskmgr.exe": ("gnome-system-monitor", "ksysguard"),
        "useraccountcontrolsettings": ("gnome-control-center", "system", "users"),
        "utilman": ("gnome-control-center", "universal-access"),
        "wmimgmt.msc": ("gnome-control-center", "system"),
        "wordpad": ("gnome-text-editor", "gedit", "kate", "mousepad"),
        "wordpad.exe": ("gnome-text-editor", "gedit", "kate", "mousepad"),
    }

    CONTROL_PANELS = {
        "accessibility": ("universal-access",),
        "administrative tools": ("system",),
        "background": ("background",),
        "bluetooth": ("bluetooth",),
        "color": ("color",),
        "colour": ("color",),
        "dateandtime": ("system", "datetime"),
        "date/time": ("system", "datetime"),
        "datetime": ("system", "datetime"),
        "default programs": ("applications",),
        "desktop": ("background",),
        "display": ("display",),
        "folders": ("applications",),
        "folderoptions": ("applications",),
        "fonts": ("applications",),
        "internet options": ("network",),
        "internetoptions": ("network",),
        "keyboard": ("keyboard",),
        "mouse": ("mouse",),
        "network": ("network",),
        "network connections": ("network",),
        "network and sharing center": ("network",),
        "networkandsharingcenter": ("network",),
        "pen and touch": ("wacom",),
        "personalization": ("background",),
        "power options": ("power",),
        "poweroptions": ("power",),
        "printers": ("printers",),
        "programs and features": ("applications",),
        "programsandfeatures": ("applications",),
        "region": ("system", "region"),
        "sound": ("sound",),
        "system": ("system", "about"),
        "easeofaccesscenter": ("universal-access",),
        "user accounts": ("system", "users"),
        "useraccounts": ("system", "users"),
        "windowsfirewall": ("privacy",),
        "windows update": ("ubuntu",),
        "windowsupdate": ("ubuntu",),
    }

    CPL_ALIASES = {
        "appwiz.cpl": ("applications",),
        "desk.cpl": ("background",),
        "firewall.cpl": (),
        "hdwwiz.cpl": (),
        "inetcpl.cpl": ("network",),
        "intl.cpl": ("system", "region"),
        "joy.cpl": ("wacom",),
        "main.cpl": ("mouse",),
        "mmsys.cpl": ("sound",),
        "ncpa.cpl": ("network",),
        "powercfg.cpl": ("power",),
        "sysdm.cpl": ("system", "about"),
        "tabletpc.cpl": ("wacom",),
        "timedate.cpl": ("system", "datetime"),
        "wscui.cpl": ("privacy",),
        "wuaucpl.cpl": ("ubuntu",),
    }

    MANAGEMENT_COMMANDS = {
        "certmgr.msc": (
            "certificates",
            "Linux 使用系统证书库，而不是 Windows 证书管理器。\n"
            "可使用系统设置中的隐私与安全页面查看相关配置。",
        ),
        "devmgmt.msc": (
            "terminal",
            "lshw -short; echo; lspci; echo; lsusb",
        ),
        "lusrmgr.msc": ("control", "system users"),
        "regedit": (
            "registry",
            "Linux 不使用 Windows 注册表。GNOME 配置可通过 dconf/gsettings 管理。",
        ),
        "regedit.exe": (
            "registry",
            "Linux 不使用 Windows 注册表。GNOME 配置可通过 dconf/gsettings 管理。",
        ),
        "regedt32": (
            "registry",
            "Linux 不使用 Windows 注册表。GNOME 配置可通过 dconf/gsettings 管理。",
        ),
        "secpol.msc": (
            "unsupported",
            "Windows 本地安全策略在 Linux 中没有直接对应项。",
        ),
        "services.msc": (
            "terminal",
            "systemctl --no-pager --type=service --state=running",
        ),
        "taskschd.msc": (
            "terminal",
            "systemctl list-timers --all --no-pager",
        ),
    }

    TERMINAL_COMMANDS = {
        "bash",
        "cmd",
        "cmd.exe",
        "fish",
        "htop",
        "journalctl",
        "pip",
        "pip3",
        "powershell",
        "powershell.exe",
        "pwsh",
        "pwsh.exe",
        "python",
        "python3",
        "sh",
        "systemctl",
        "top",
        "zsh",
    }

    DOS_TRANSLATIONS = {
        "cd": "cd",
        "chdir": "cd",
        "cls": "clear",
        "copy": "cp",
        "date": "date",
        "del": "rm",
        "dir": "ls -la",
        "echo": "echo",
        "erase": "rm",
        "exit": "exit",
        "ipconfig": "ip addr",
        "md": "mkdir",
        "mkdir": "mkdir",
        "more": "less",
        "move": "mv",
        "pause": "read -n 1 -s -r -p 'Press Enter to continue...'",
        "ping": "ping",
        "rd": "rmdir",
        "ren": "mv",
        "rename": "mv",
        "rmdir": "rmdir",
        "set": "env",
        "start": "xdg-open",
        "systeminfo": "uname -a && lscpu && free -h",
        "taskkill": "kill",
        "tasklist": "ps aux",
        "time": "date",
        "tracert": "traceroute",
        "type": "cat",
        "ver": "uname -a",
        "where": "command -v",
    }

    def __init__(self, home=None, env=None, which=None):
        self.home = str(Path(home or Path.home()).expanduser())
        self.env = dict(os.environ if env is None else env)
        self.which = which or shutil.which

    def resolve(self, raw):
        text = (raw or "").strip()
        if not text:
            return error_plan("请输入要运行的程序、文件夹、文档或 Internet 资源。")

        plan = self._resolve_url(text)
        if plan:
            return plan

        plan = self._resolve_shell_folder(text)
        if plan:
            return plan

        expanded = self._expand_environment(text)
        lowered = expanded.casefold()

        plan = self._resolve_command_alias(expanded, lowered)
        if plan:
            return plan

        plan = self._resolve_control_panel(expanded, lowered)
        if plan:
            return plan

        plan = self._resolve_management_tool(expanded, lowered)
        if plan:
            return plan

        plan = self._resolve_browser(expanded, lowered)
        if plan:
            return plan

        plan = self._resolve_path(expanded)
        if plan:
            return plan

        return self._resolve_program(expanded)

    def _resolve_command_alias(self, text, lowered):
        first, _, argline = text.partition(" ")
        first = first.casefold()

        if first in ("cmd", "cmd.exe"):
            return self._resolve_cmd(argline)

        if first in ("powershell", "powershell.exe", "pwsh", "pwsh.exe"):
            return self._resolve_powershell(argline)

        if first in ("wt", "terminal", "windows terminal"):
            return self._terminal_plan("exec bash -l")

        if first in ("explorer", "explorer.exe"):
            return self._resolve_explorer(argline)

        if lowered in ("winver", "winver.exe"):
            return info_plan(
                "关于 Run For Linux",
                "Run For Linux\n"
                "Windows Run compatibility layer\n\n"
                "系统：{}\n"
                "快捷方式：Super + R".format(self._pretty_os_name()),
            )

        if lowered in ("msinfo32", "msinfo32.exe", "dxdiag", "dxdiag.exe"):
            return info_plan("系统信息", self._system_information())

        if lowered in ("mspaint", "mspaint.exe"):
            return error_plan(
                "当前系统没有检测到画图程序。\n"
                "可以安装 GNOME Drawing 或 GIMP 后再从运行对话框启动。"
            )

        if lowered == "logoff":
            command = self.which("gnome-session-quit")
            if command:
                return process_plan(
                    (command, "--logout", "--no-prompt"),
                    cwd=self.home,
                )
            return error_plan("没有检测到可用于注销的桌面会话工具。")

        if lowered in ("magnify", "osk", "utilman"):
            return self._control_panel_plan(("universal-access",))

        if lowered == "useraccountcontrolsettings":
            return self._control_panel_plan(("system", "users"))

        if lowered == "wmimgmt.msc":
            return self._control_panel_plan(("system", "about"))

        if lowered == "firewall.cpl":
            gufw = self.which("gufw")
            if gufw:
                return process_plan((gufw,), cwd=self.home)
            return info_plan(
                "防火墙",
                "已使用 ufw 作为系统防火墙，但未安装图形管理工具 gufw。\n\n"
                "安装命令：sudo apt install gufw\n"
                "命令行查看：sudo ufw status",
            )

        if lowered in self.CPL_ALIASES:
            panel = self.CPL_ALIASES[lowered]
            if panel:
                return self._control_panel_plan(panel)

        aliases = self.GUI_ALIASES.get(lowered)
        if aliases is not None:
            if not aliases:
                if lowered.startswith("explorer"):
                    return self._resolve_explorer("")
                return error_plan("当前系统没有检测到可用于此命令的图形程序。")
            command = self._first_available(*aliases)
            if command:
                return process_plan(command, cwd=self.home)
            return error_plan(
                "没有检测到适合此 Windows 命令的 Linux 程序：\n"
                + ", ".join(aliases)
            )

        if lowered in ("shell", "shell:"):
            return open_plan(self.home)

        if first in self.DOS_TRANSLATIONS and first not in ("start",):
            command = self._translate_dos_command(text)
            return self._terminal_plan(self._keep_open_command(command))

        return None

    def _resolve_cmd(self, argline):
        if not argline:
            return self._terminal_plan("exec bash -l")

        parts = argline.split(None, 1)
        option = parts[0].casefold()
        command = parts[1] if len(parts) > 1 else ""

        if option not in ("/c", "/k"):
            command = argline
        elif not command:
            return self._terminal_plan("exec bash -l")

        command = self._translate_dos_command(command)
        if option == "/c":
            return self._terminal_plan(command)
        return self._terminal_plan(self._keep_open_command(command))

    def _resolve_powershell(self, argline):
        powershell = self._first_available("pwsh", "powershell")
        if not powershell:
            return error_plan(
                "系统未安装 PowerShell。\n\n"
                "安装后即可直接运行 powershell 或 pwsh 命令。\n"
                "Ubuntu 可参考 Microsoft 官方 PowerShell 安装说明。"
            )
        if not argline:
            return self._terminal_plan("exec " + shlex.quote(powershell) + " -NoLogo")
        command = "exec " + shlex.join([powershell, "-NoLogo"] + shlex.split(argline))
        return self._terminal_plan(command)

    def _resolve_explorer(self, argline):
        target = argline.strip().strip('"')
        if not target:
            return open_plan(self.home)
        if target.casefold() in (".", "..."):
            return open_plan(self.home)
        converted = self._windows_path_to_linux(target)
        if converted:
            return open_plan(converted)
        return open_plan(self._expand_environment(target))

    def _resolve_control_panel(self, text, lowered):
        first, _, argline = text.partition(" ")
        if first.casefold() != "control":
            return None

        if not argline:
            return self._control_panel_plan(())

        if argline.casefold().startswith("/name "):
            argline = argline[6:].strip()
        elif argline.casefold().startswith("/page "):
            argline = argline[6:].strip()

        key = " ".join(argline.casefold().split())
        for name, panel in self.CONTROL_PANELS.items():
            if name in key:
                return self._control_panel_plan(panel)
        return self._control_panel_plan(())

    def _resolve_management_tool(self, text, lowered):
        entry = self.MANAGEMENT_COMMANDS.get(lowered)
        if not entry:
            return None
        kind, value = entry
        if kind == "terminal":
            return self._terminal_plan(self._keep_open_command(value))
        if kind == "control":
            return self._resolve_control_panel("control " + value, "")
        if kind == "registry":
            dconf_editor = self._first_available("dconf-editor", "dconf")
            if dconf_editor:
                if dconf_editor.endswith("dconf-editor"):
                    return process_plan((dconf_editor,), cwd=self.home)
                return self._terminal_plan(
                    self._keep_open_command("dconf dump /")
                )
            return info_plan(
                "注册表",
                value + "\n\n安装图形编辑器：sudo apt install dconf-editor",
            )
        if kind == "certificates":
            return self._control_panel_plan(("privacy",))
        return info_plan("运行", value)

    def _resolve_browser(self, text, lowered):
        first, _, argline = text.partition(" ")
        browser_names = {
            "chrome": ("google-chrome", "chromium", "chromium-browser"),
            "chrome.exe": ("google-chrome", "chromium", "chromium-browser"),
            "edge": ("microsoft-edge", "microsoft-edge-stable"),
            "edge.exe": ("microsoft-edge", "microsoft-edge-stable"),
            "firefox": ("firefox",),
            "firefox.exe": ("firefox",),
            "iexplore": ("firefox", "microsoft-edge"),
            "iexplore.exe": ("firefox", "microsoft-edge"),
        }
        choices = browser_names.get(first.casefold())
        if not choices:
            return None

        browser = self._first_available(*choices)
        if not browser:
            return error_plan("没有检测到可用的浏览器。")
        if argline:
            try:
                arguments = shlex.split(argline)
            except ValueError:
                arguments = [argline]
            return process_plan((browser,) + tuple(arguments), cwd=self.home)
        return process_plan((browser,), cwd=self.home)

    def _resolve_url(self, text):
        parsed = urllib.parse.urlsplit(text)
        scheme = parsed.scheme.casefold()
        if scheme in ("http", "https", "ftp", "mailto", "file", "smb", "ssh"):
            return open_plan(text)
        if re.match(r"^(www\.|localhost(?::\d+)?(?:/|$))", text, re.I):
            return open_plan("https://" + text)
        return None

    def _resolve_shell_folder(self, text):
        if not text.casefold().startswith("shell:"):
            return None

        key = " ".join(text[6:].strip().casefold().split())
        if not key:
            return open_plan(self.home)

        if key == "controlpanel":
            return self._control_panel_plan(())
        if key in ("connectionsfolder", "networkplaces"):
            return self._control_panel_plan(("network",))
        if key == "printersfolder":
            return self._control_panel_plan(("printers",))

        directories = {
            "addnewprograms": self._software_center(),
            "administrative tools": self._first_existing(
                Path("/usr/share/applications"), Path("/etc")
            ),
            "appdata": self._config_home(),
            "appsfolder": self._applications_folder(),
            "cache": str(Path(self.home) / ".cache"),
            "common administrative tools": self._first_existing(
                Path("/usr/share/applications"), Path("/etc")
            ),
            "common programs": "/usr/share/applications",
            "common startup": "/etc/xdg/autostart",
            "common start menu": "/usr/share/applications",
            "common templates": "/usr/share/templates",
            "cookies": str(Path(self.home) / ".config"),
            "desktop": self._xdg_dir("DESKTOP", "Desktop"),
            "documents": self._xdg_dir("DOCUMENTS", "Documents"),
            "downloads": self._xdg_dir("DOWNLOAD", "Downloads"),
            "favorites": self.home,
            "fonts": str(Path(self.home) / ".local/share/fonts"),
            "history": str(Path(self.home) / ".local/share"),
            "localappdata": str(Path(self.home) / ".local/share"),
            "music": self._xdg_dir("MUSIC", "Music"),
            "mycomputer": "/",
            "mypictures": self._xdg_dir("PICTURES", "Pictures"),
            "myvideo": self._xdg_dir("VIDEOS", "Videos"),
            "personal": self.home,
            "pictures": self._xdg_dir("PICTURES", "Pictures"),
            "profile": self.home,
            "programs": str(Path(self.home) / ".local/share/applications"),
            "public": self._xdg_dir("PUBLICSHARE", "Public"),
            "recent": str(Path(self.home) / ".local/share"),
            "sendto": self._applications_folder(),
            "start menu": str(Path(self.home) / ".local/share/applications"),
            "startup": str(Path(self.home) / ".config/autostart"),
            "system": "/usr/bin",
            "system32": "/usr/bin",
            "temp": tempfile.gettempdir(),
            "templates": self._xdg_dir("TEMPLATES", "Templates"),
            "usersfilesfolder": self.home,
            "videos": self._xdg_dir("VIDEOS", "Videos"),
            "windows": "/etc",
        }
        if key in directories:
            target = directories[key]
            return open_plan(target)
        return error_plan("不支持的 Windows 特殊文件夹：shell:" + key)

    def _resolve_path(self, text):
        if text.casefold().endswith(".exe"):
            windows_path = os.path.expanduser(text)
            if os.path.isfile(windows_path):
                wine = self.which("wine")
                if wine:
                    return process_plan((wine, windows_path), cwd=self.home)
                return error_plan("检测到 Windows 程序，但系统未安装 Wine。")

        converted = self._windows_path_to_linux(text)
        candidate = converted or os.path.expanduser(text)
        if not os.path.isabs(candidate) and any(
            marker in text for marker in ("/", "\\", "~")
        ):
            candidate = str(Path(self.home) / candidate)

        if os.path.exists(candidate):
            return open_plan(os.path.abspath(candidate))

        if converted or text.startswith(("/", "./", "../", "~")):
            return error_plan(
                "Linux 找不到路径：\n"
                + text
                + "\n\n请检查名称并重试。"
            )
        return None

    def _resolve_program(self, text):
        try:
            parts = shlex.split(text)
        except ValueError as exc:
            return error_plan("命令格式错误：\n" + str(exc))

        if not parts:
            return error_plan("请输入要运行的命令。")

        command_name = parts[0]
        command = self.which(command_name)
        if command:
            if Path(command_name).name.casefold() in self.TERMINAL_COMMANDS:
                shell_command = self._keep_open_command(shlex.join(parts))
                return self._terminal_plan(shell_command)
            return process_plan((command,) + tuple(parts[1:]), cwd=self.home)

        if self._contains_shell_syntax(text):
            return self._terminal_plan(
                self._keep_open_command(self._translate_windows_paths(text))
            )

        return error_plan(
            "Linux 找不到“"
            + command_name
            + "”。请确定文件名是否正确后，再试一次。\n\n"
            "可以直接使用 Linux 命令，也可以输入 cmd 打开终端。"
        )

    def _control_panel_plan(self, panel):
        command = self.which("gnome-control-center")
        if not command:
            return error_plan("没有检测到 GNOME 系统设置。")
        return process_plan((command,) + tuple(panel), cwd=self.home)

    def _terminal_plan(self, shell_command):
        terminal = self.which("gnome-terminal")
        if terminal:
            argv = (terminal, "--", "bash", "-lc", shell_command)
        else:
            terminal = self.which("xterm")
            if not terminal:
                return error_plan("没有检测到可用的终端程序。")
            argv = (terminal, "-e", "bash", "-lc", shell_command)
        return process_plan(argv, cwd=self.home)

    def _translate_dos_command(self, command):
        command = self._translate_windows_paths(command.strip())
        if not command:
            return ""
        first, separator, rest = command.partition(" ")
        translated = self.DOS_TRANSLATIONS.get(first.casefold())
        if not translated:
            return command
        if separator:
            return translated + " " + rest
        return translated

    def _translate_windows_paths(self, text):
        def replace(match):
            converted = self._windows_path_to_linux(match.group(0))
            return shlex.quote(converted) if converted else match.group(0)

        pattern = r"(?<![A-Za-z0-9])(?:[A-Za-z]:\\[^ \t\"]*)"
        return re.sub(pattern, replace, text)

    def _expand_environment(self, text):
        aliases = {
            "%ALLUSERSPROFILE%": "/var/lib",
            "%APPDATA%": self._config_home(),
            "%HOMEDRIVE%%HOMEPATH%": self.home,
            "%HOMEPATH%": self.home,
            "%LOCALAPPDATA%": str(Path(self.home) / ".local/share"),
            "%PROGRAMDATA%": "/usr/share",
            "%PROGRAMFILES%": "/usr/share",
            "%PROGRAMFILES(X86)%": "/usr/share",
            "%PUBLIC%": self._xdg_dir("PUBLICSHARE", "Public"),
            "%SYSTEMDRIVE%": "/",
            "%SYSTEMROOT%": "/etc",
            "%TEMP%": tempfile.gettempdir(),
            "%TMP%": tempfile.gettempdir(),
            "%USERPROFILE%": self.home,
            "%WINDIR%": "/etc",
        }
        aliases.update({key.casefold(): value for key, value in aliases.items()})
        result = text
        for name in sorted(aliases, key=len, reverse=True):
            result = re.sub(
                re.escape(name),
                lambda _match, value=aliases[name]: value,
                result,
                flags=re.IGNORECASE,
            )
        return result

    def _windows_path_to_linux(self, value):
        value = self._expand_environment(value.strip().strip('"'))
        if re.match(r"^\\\\[^\\]+\\[^\\]+", value):
            return "smb:" + value.replace("\\", "/")

        match = re.match(r"^([A-Za-z]):(?:[\\/](.*))?$", value)
        if not match:
            if "\\" not in value:
                return None
            normalized = value.replace("\\", "/")
            home_prefix = self.home.rstrip("/") + "/"
            if normalized.casefold().startswith(home_prefix.casefold()):
                remainder = normalized[len(home_prefix):]
                parts = [part for part in remainder.split("/") if part]
                if parts:
                    xdg_name = {
                        "desktop": ("DESKTOP", "Desktop"),
                        "documents": ("DOCUMENTS", "Documents"),
                        "downloads": ("DOWNLOAD", "Downloads"),
                        "music": ("MUSIC", "Music"),
                        "pictures": ("PICTURES", "Pictures"),
                        "videos": ("VIDEOS", "Videos"),
                    }.get(parts[0].casefold())
                    if xdg_name:
                        return str(
                            Path(self._xdg_dir(*xdg_name)).joinpath(*parts[1:])
                        )
            return normalized

        drive = match.group(1).casefold()
        remainder = (match.group(2) or "").replace("\\", "/").strip("/")
        parts = [part for part in remainder.split("/") if part]

        if drive != "c":
            mount = Path("/mnt") / drive
            if not mount.exists():
                mount = Path("/media") / self._user_name() / drive.upper()
            return str(mount.joinpath(*parts))

        if not parts:
            return "/"
        if parts[0].casefold() == "windows":
            return str(Path("/etc").joinpath(*parts[1:]))
        if parts[0].casefold() == "users":
            if len(parts) == 1:
                return "/home"
            user_dir = Path("/home") / parts[1]
            if parts[1].casefold() == self._user_name().casefold():
                user_dir = Path(self.home)
            if len(parts) >= 3:
                xdg_name = {
                    "desktop": ("DESKTOP", "Desktop"),
                    "documents": ("DOCUMENTS", "Documents"),
                    "downloads": ("DOWNLOAD", "Downloads"),
                    "music": ("MUSIC", "Music"),
                    "pictures": ("PICTURES", "Pictures"),
                    "videos": ("VIDEOS", "Videos"),
                }.get(parts[2].casefold())
                if xdg_name:
                    user_dir = Path(self._xdg_dir(*xdg_name))
                    return str(user_dir.joinpath(*parts[3:]))
            return str(user_dir.joinpath(*parts[2:]))
        return str(Path("/").joinpath(*parts))

    def _xdg_dir(self, name, fallback):
        command = self.which("xdg-user-dir")
        if command:
            try:
                result = subprocess.run(
                    [command, name],
                    check=False,
                    capture_output=True,
                    text=True,
                    timeout=2,
                )
                path = result.stdout.strip()
                if result.returncode == 0 and path and os.path.isabs(path):
                    return path
            except (OSError, subprocess.SubprocessError):
                pass
        return str(Path(self.home) / fallback)

    def _config_home(self):
        return self.env.get("XDG_CONFIG_HOME", str(Path(self.home) / ".config"))

    def _applications_folder(self):
        return self._first_existing(
            Path(self.home) / ".local/share/applications",
            Path("/usr/share/applications"),
        )

    def _software_center(self):
        software = self._first_available(
            "software-properties-gtk", "update-manager", "snap-store"
        )
        return str(software) if software else self._applications_folder()

    def _first_available(self, *names):
        for name in names:
            found = self.which(name)
            if found:
                return found
        return None

    @staticmethod
    def _first_existing(*paths):
        for path in paths:
            if path.exists():
                return str(path)
        return str(paths[-1])

    def _user_name(self):
        return Path(self.home).name

    @staticmethod
    def _contains_shell_syntax(text):
        return bool(re.search(r"[|&;<>`$*?(){}]", text))

    @staticmethod
    def _keep_open_command(command):
        if not command:
            return "exec bash -l"
        return command + "\nstatus=$?\nprintf '\\n[退出状态: %s]\\n' \"$status\"\nexec bash -l"

    @staticmethod
    def _pretty_os_name():
        try:
            with open("/etc/os-release", "r", encoding="utf-8") as handle:
                for line in handle:
                    if line.startswith("PRETTY_NAME="):
                        return line.split("=", 1)[1].strip().strip('"')
        except OSError:
            pass
        return "{} {}".format(sys.platform, sys.version.split()[0])

    def _system_information(self):
        lines = [
            "Run For Linux 系统信息",
            "",
            "系统：" + sys.platform,
            "Python：" + sys.version.split()[0],
            "用户目录：" + self.home,
        ]
        uname = self.which("uname")
        if uname:
            try:
                result = subprocess.run(
                    [uname, "-a"],
                    check=False,
                    capture_output=True,
                    text=True,
                    timeout=2,
                )
                if result.stdout.strip():
                    lines.extend(("", "内核：" + result.stdout.strip()))
            except (OSError, subprocess.SubprocessError):
                pass
        try:
            usage = shutil.disk_usage(self.home)
            lines.extend(
                (
                    "",
                    "磁盘：已用 %.1f GB / 共 %.1f GB"
                    % (
                        (usage.total - usage.free) / (1024 ** 3),
                        usage.total / (1024 ** 3),
                    ),
                )
            )
        except OSError:
            pass
        return "\n".join(lines)

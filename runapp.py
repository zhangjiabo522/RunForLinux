import json
import os
import subprocess
import sys
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from PIL import Image, ImageTk

from winsupport import RunResolver


APP_DIR = Path(__file__).resolve().parent
CONFIG_DIR = Path(
    os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config"))
) / "run-for-linux"
HISTORY_FILE = CONFIG_DIR / "history.json"
WINDOW_WIDTH = 430
WINDOW_HEIGHT = 210


class RunDialogApp:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("运行")
        self.root.resizable(False, False)
        self.root.protocol("WM_DELETE_WINDOW", self.root.destroy)
        self._set_window_position()

        self.resolver = RunResolver()
        self.history = self._load_history()
        self._icon = None

        self._configure_style()
        self._build_interface()
        self._bind_keys()

    def _configure_style(self):
        style = ttk.Style(self.root)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure("Run.TCombobox", padding=2)
        style.configure("Run.TButton", padding=(4, 2))

    def _set_window_position(self):
        self.root.update_idletasks()
        screen_height = self.root.winfo_screenheight()
        x = 0
        y = max(0, screen_height - WINDOW_HEIGHT)
        self.root.geometry(
            "{}x{}+{}+{}".format(WINDOW_WIDTH, WINDOW_HEIGHT, x, y)
        )

    def _build_interface(self):
        self._load_icon()

        ttk.Label(
            self.root,
            text="Linux 将根据你所输入的名称，为你打开相应的程序、文",
        ).place(x=76, y=34)
        ttk.Label(
            self.root,
            text="件夹、文档或 Internet 资源。",
        ).place(x=76, y=53)

        ttk.Label(self.root, text="打开(O):").place(x=14, y=101)

        self.entry = ttk.Combobox(
            self.root,
            width=40,
            style="Run.TCombobox",
            values=self.history,
        )
        self.entry.place(x=83, y=97)
        self.entry.focus_set()

        ttk.Button(
            self.root,
            text="确定",
            width=10,
            style="Run.TButton",
            command=self.run_command,
        ).place(x=111, y=150)
        ttk.Button(
            self.root,
            text="取消",
            width=10,
            style="Run.TButton",
            command=self.root.destroy,
        ).place(x=221, y=150)
        ttk.Button(
            self.root,
            text="浏览(B)...",
            width=10,
            style="Run.TButton",
            command=self.browse_file,
        ).place(x=331, y=150)

        tk.Button(
            self.root,
            text="关于",
            bd=0,
            relief=tk.FLAT,
            fg="#777777",
            activeforeground="#444444",
            command=self.about,
        ).place(x=0, y=181)

    def _load_icon(self):
        icon_path = APP_DIR / "运行_00002.ico"
        if not icon_path.exists():
            return
        try:
            image = Image.open(str(icon_path)).convert("RGBA")
            image = image.resize((32, 32), Image.Resampling.LANCZOS)
            self._icon = ImageTk.PhotoImage(image)
            ttk.Label(self.root, image=self._icon).place(x=18, y=42)
            self.root.iconphoto(True, self._icon)
        except (OSError, tk.TclError):
            self._icon = None

    def _bind_keys(self):
        self.root.bind("<Escape>", lambda _event: self.root.destroy())
        self.root.bind("<Alt-o>", lambda _event: self._focus_entry())
        self.root.bind("<Alt-O>", lambda _event: self._focus_entry())
        self.root.bind("<Alt-b>", lambda _event: self.browse_file())
        self.root.bind("<Alt-B>", lambda _event: self.browse_file())
        self.entry.bind("<Return>", lambda _event: self.run_command())
        self.entry.bind("<KP_Enter>", lambda _event: self.run_command())

    def _focus_entry(self):
        self.entry.focus_set()
        self.entry.selection_range(0, tk.END)
        return "break"

    def browse_file(self):
        filepath = filedialog.askopenfilename(
            parent=self.root,
            title="选择要打开的文件",
        )
        if not filepath:
            return
        if sys.platform == "win32":
            filepath = filepath.replace("/", "\\")
        self.entry.delete(0, tk.END)
        self.entry.insert(0, filepath)
        self.entry.focus_set()

    def run_command(self):
        command = self.entry.get().strip()
        if not command:
            return

        plan = self.resolver.resolve(command)
        if plan.kind == "error":
            messagebox.showerror("运行", plan.message, parent=self.root)
            self.entry.focus_set()
            self.entry.selection_range(0, tk.END)
            return

        if plan.kind == "info":
            self.root.withdraw()
            messagebox.showinfo(plan.title or "运行", plan.message, parent=self.root)
            self._remember(command)
            self.root.destroy()
            return

        try:
            if plan.kind == "open":
                opener = self.resolver.which("xdg-open")
                if not opener:
                    raise RuntimeError("未安装 xdg-open。")
                subprocess.Popen(
                    [opener, plan.target],
                    cwd=self.resolver.home,
                    start_new_session=True,
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            elif plan.kind == "process":
                subprocess.Popen(
                    list(plan.argv),
                    cwd=plan.cwd or self.resolver.home,
                    start_new_session=True,
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            else:
                raise RuntimeError("未知的启动类型：{}".format(plan.kind))
        except (OSError, RuntimeError) as exc:
            self.root.deiconify()
            messagebox.showerror(
                "运行",
                "无法打开：{}\n{}".format(command, exc),
                parent=self.root,
            )
            return

        self._remember(command)
        self.root.destroy()

    def _load_history(self):
        try:
            with HISTORY_FILE.open("r", encoding="utf-8") as handle:
                data = json.load(handle)
            if isinstance(data, list):
                return [item for item in data if isinstance(item, str)][:20]
        except (OSError, ValueError, TypeError):
            pass
        return []

    def _remember(self, command):
        self.history = [command] + [
            item for item in self.history if item != command
        ]
        self.history = self.history[:20]
        try:
            CONFIG_DIR.mkdir(parents=True, exist_ok=True)
            with HISTORY_FILE.open("w", encoding="utf-8") as handle:
                json.dump(self.history, handle, ensure_ascii=False, indent=2)
        except OSError:
            pass

    def about(self):
        messagebox.showinfo(
            "关于",
            "Run For Linux\n\n"
            "项目：@Windows卸载程序\n"
            "Win+R 命令兼容层：Codex\n"
            "快捷键：Super + R",
            parent=self.root,
        )

    def run(self):
        self.root.mainloop()


def RunDialog():
    RunDialogApp().run()


if __name__ == "__main__":
    RunDialog()

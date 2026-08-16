from tkinter import *
from tkinter import ttk
from tkinter import filedialog
from PIL import Image, ImageTk
import sys
import subprocess
import os
if sys.platform == "win32":
    __import__("ctypes").windll.user32.SetProcessDPIAware() # Fuck the DPI
    print("Fuck the DPI!")

osdict = {
    "win32": "Windows",
    "linux": "Linux",
    "darwin": "MacOS",
    "freebsd": "Free BSD"
}

def set_size():
    "某些Linux桌面环境对resizable支持不全"
    geometry = "430x200"
    if geometry not in root.winfo_geometry():
        root.geometry(geometry + "+10-10")
    root.after(10, set_size)

# 浏览按钮回调函数
def browse_file():
    # 弹出文件选择框
    filepath = filedialog.askopenfilename(title="选择要打开的文件")
    if sys.platform == "win32":
        filepath = filepath.replace("/", "\\")
    if filepath:
        # 清空并写入路径
        entry.delete(0, END)
        entry.insert(0, filepath)
        entry.focus()

# 确定按钮回调函数
def run_command():
    cmd = entry.get().strip()
    if not cmd:
        return
    try:
        if sys.platform == "win32":
            # Windows 使用 start 打开
            root.withdraw()
            if not os.system("start "+cmd):
                root.destroy()
            else:
                root.deiconify()
        else:
            # Linux/macOS
            opener = "xterm" if sys.platform == "linux" else "open"
            subprocess.Popen([opener, cmd])
            root.destroy()
    except Exception as e:
        from tkinter import messagebox
        messagebox.showerror("错误", f"无法打开：{cmd}\n{e}")

def about():
    from tkinter import messagebox
    messagebox.showinfo("关于", "@Windows卸载程序\n同时感谢以♂下♂开♂发♂者：@豆包 @TraeCode CN")

def RunDialog():
    global root, entry
    root = Tk()
    root.title("运行")
    set_size()
    root.resizable(False, False)

    # 图片容错：找不到ico就不加载，避免崩溃
    try:
        img = ImageTk.PhotoImage(Image.open("运行_00001.ico"))
        ttk.Label(root, image=img).place(x=18, y=39)
    except Exception:
        pass

    ttk.Label(root, text="%s 将根据你所输入的名称，为你打开相应的程序、文" % osdict[sys.platform]).place(x=77, y=32)
    ttk.Label(root, text="件夹、文档或 Internet 资源。").place(x=77, y=50)
    ttk.Label(root, text="打开(O):").place(x=14, y=100)

    entry = ttk.Entry(root, width=41)
    entry.place(x=83, y=95)
    entry.focus()

    # 绑定回车等价点击确定
    entry.bind("<Return>", lambda e: run_command())

    ttk.Button(root, text="确定", width=10, command=run_command).place(x=111, y=149)
    ttk.Button(root, text="取消", width=10, command=root.destroy).place(x=221, y=149)
    # 浏览按钮绑定函数
    ttk.Button(root, text="浏览(B)...", width=10, command=browse_file).place(x=331, y=149)

    Button(root, text="关于", bd=0, fg="#808080", command=about).place(x=0, y=179)
    root.mainloop()

if __name__ == "__main__":
    RunDialog()
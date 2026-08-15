from keyboard import add_hotkey, wait
from runapp import RunDialog
import sys
if sys.platform == "win32":
    add_hotkey("left Windows+r", RunDialog)
else:
    add_hotkey("left Super+r", RunDialog)
wait()
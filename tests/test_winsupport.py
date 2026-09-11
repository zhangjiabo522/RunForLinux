import tempfile
import unittest
from pathlib import Path

from winsupport import RunResolver


class RunResolverTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.home = Path(self.temp_dir.name)
        (self.home / "Documents").mkdir()
        (self.home / "Downloads").mkdir()
        commands = {
            "cmd": "/usr/bin/cmd",
            "dconf": "/usr/bin/dconf",
            "firefox": "/usr/bin/firefox",
            "gnome-control-center": "/usr/bin/gnome-control-center",
            "gnome-session-properties": "/usr/bin/gnome-session-properties",
            "gnome-system-monitor": "/usr/bin/gnome-system-monitor",
            "gnome-terminal": "/usr/bin/gnome-terminal",
            "gnome-text-editor": "/usr/bin/gnome-text-editor",
            "nautilus": "/usr/bin/nautilus",
            "xdg-open": "/usr/bin/xdg-open",
        }
        self.resolver = RunResolver(
            home=str(self.home),
            env={"XDG_CONFIG_HOME": str(self.home / ".config")},
            which=commands.get,
        )

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_cmd_opens_linux_terminal(self):
        plan = self.resolver.resolve("cmd")
        self.assertEqual(plan.kind, "process")
        self.assertEqual(plan.argv[0], "/usr/bin/gnome-terminal")
        self.assertEqual(plan.argv[-1], "exec bash -l")

    def test_cmd_k_translates_dir_and_keeps_shell(self):
        plan = self.resolver.resolve(r"cmd /k dir C:\\")
        self.assertEqual(plan.kind, "process")
        self.assertIn("ls -la /", plan.argv[-1])
        self.assertIn("exec bash -l", plan.argv[-1])

    def test_control_panel_aliases(self):
        plan = self.resolver.resolve("control date/time")
        self.assertEqual(
            plan.argv,
            ("/usr/bin/gnome-control-center", "system", "datetime"),
        )

        plan = self.resolver.resolve("control /name Microsoft.UserAccounts")
        self.assertEqual(
            plan.argv,
            ("/usr/bin/gnome-control-center", "system", "users"),
        )

    def test_gui_command_alias_is_not_split_into_characters(self):
        plan = self.resolver.resolve("taskmgr")
        self.assertEqual(
            plan.argv,
            ("/usr/bin/gnome-system-monitor",),
        )

    def test_shell_folder_uses_xdg_directory(self):
        plan = self.resolver.resolve("shell:downloads")
        self.assertEqual(plan.kind, "open")
        self.assertEqual(plan.target, str(self.home / "Downloads"))

    def test_windows_user_folder_maps_to_linux_home(self):
        plan = self.resolver.resolve(
            r"C:\Users\{}".format(self.home.name) + r"\Documents"
        )
        self.assertEqual(plan.kind, "open")
        self.assertEqual(plan.target, str(self.home / "Documents"))

    def test_user_profile_environment_variable_with_backslashes(self):
        plan = self.resolver.resolve(r"%USERPROFILE%\Downloads")
        self.assertEqual(plan.kind, "open")
        self.assertEqual(plan.target, str(self.home / "Downloads"))

    def test_browser_arguments_are_preserved(self):
        plan = self.resolver.resolve("firefox --new-window https://example.com")
        self.assertEqual(
            plan.argv,
            (
                "/usr/bin/firefox",
                "--new-window",
                "https://example.com",
            ),
        )

    def test_information_and_error_commands(self):
        self.assertEqual(self.resolver.resolve("winver").kind, "info")
        self.assertEqual(
            self.resolver.resolve("definitely-not-a-command").kind,
            "error",
        )


if __name__ == "__main__":
    unittest.main()

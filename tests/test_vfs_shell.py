"""Проверки интеграции VFS с интерактивной оболочкой."""

import io
import unittest

from src.shell import Shell
from src.vfs import Vfs, load_vfs


class ShellVfsTests(unittest.TestCase):
    """Проверяет использование VFS внутри оболочки."""

    def test_prompt_contains_vfs_directory(self):
        """Приглашение отражает текущий каталог VFS."""
        shell = Shell(io.StringIO(), Vfs())
        self.assertIn(":/$ ", shell.prompt())

    def test_information_command(self):
        """Служебная команда отображает имя и состав загруженной VFS."""
        output = io.StringIO()
        shell = Shell(output, load_vfs("vfs/minimal.csv"))
        self.assertTrue(shell.execute("vfsinfo"))
        self.assertIn("minimal.csv", output.getvalue())
        self.assertIn("файлов:", output.getvalue())
        self.assertFalse(shell.execute("vfsinfo extra"))

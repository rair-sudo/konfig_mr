"""Тесты конфигурации и выполнения стартового скрипта."""

import io
import tempfile
import unittest
from pathlib import Path

from src.config import Config, describe, parse_args
from src.script import run_script
from src.shell import Shell


class ConfigTests(unittest.TestCase):
    """Проверки конфигурации командной строки."""

    def test_parameters(self):
        """Оба параметра читаются и показываются в отладочном выводе."""
        config = parse_args(["--vfs", "a.csv", "--script", "b.txt"])
        self.assertEqual(config, Config("a.csv", "b.txt"))
        self.assertIn("a.csv", describe(config))
        self.assertIn("b.txt", describe(config))
        self.assertIn("не задан", describe(Config()))

    def test_unknown_option(self):
        """Неизвестный параметр вызывает ошибку argparse."""
        with self.assertRaises(SystemExit):
            parse_args(["--unknown"])


class ScriptTests(unittest.TestCase):
    """Проверки имитации диалога и обработки ошибок."""

    def test_error_does_not_stop_script(self):
        """После неверной строки выполняется следующая команда."""
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "startup.txt"
            path.write_text("badcmd\nls 'a b'\nexit\n", encoding="utf-8")
            output = io.StringIO()
            shell = Shell(output)
            self.assertFalse(run_script(shell, str(path)))
            self.assertIn("badcmd", output.getvalue())
            self.assertIn(":1: ошибка", output.getvalue())
            self.assertIn("a b", output.getvalue())
            self.assertFalse(shell.running)

    def test_missing_file(self):
        """Ошибка чтения сообщается, а оболочка остаётся открытой."""
        output = io.StringIO()
        shell = Shell(output)
        self.assertFalse(run_script(shell, "/nonexistent/startup.txt"))
        self.assertIn("script:", output.getvalue())
        self.assertTrue(shell.running)

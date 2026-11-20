"""Интеграционные проверки консольного запуска эмулятора."""

import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


def run_cli(args: list[str], commands: str = "") -> subprocess.CompletedProcess:
    """Запускает отдельный процесс оболочки в корне проекта."""
    environment = os.environ.copy()
    environment["PYTHONIOENCODING"] = "utf-8"
    return subprocess.run(
        [sys.executable, "-m", "src.main", *args], cwd=ROOT,
        input=commands, text=True, capture_output=True,
        encoding="utf-8", env=environment, timeout=10,
    )


class CliTests(unittest.TestCase):
    """Проверяет полный путь от аргументов до выхода из процесса."""

    def test_interactive_commands_and_errors(self):
        """Ввод в REPL работает после загрузки VFS, ошибки не завершают его."""
        commands = 'cd "/path with spaces"\nhead "hello world.txt"\n'
        commands += 'cd /absent\nunknown\nls\nexit\n'
        result = run_cli(["--vfs", "vfs/deep.csv"], commands)
        self.assertEqual(result.returncode, 0)
        self.assertIn("Конфигурация:", result.stdout)
        self.assertIn(":/path with spaces$ ", result.stdout)
        self.assertIn("Hello, VFS!", result.stdout)
        self.assertIn("cd: ", result.stdout)
        self.assertIn("unknown: command not found", result.stdout)
        self.assertIn("hello world.txt", result.stdout)

    def test_script_mutations_are_not_persisted(self):
        """Изменения остаются в памяти и не влияют на следующий запуск."""
        image = "path,type,content\n/a,file,SGVsbG8K\n/empty,dir,\n"
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "vfs.csv"
            script = Path(directory) / "start.txt"
            path.write_text(image, encoding="utf-8")
            script.write_text(
                "mv /a /b\nrmdir /empty\nls /\nexit\n", encoding="utf-8"
            )
            result = run_cli(["--vfs", str(path), "--script", str(script)])
            self.assertEqual(result.returncode, 0)
            self.assertIn("mv /a /b", result.stdout)
            self.assertIn("ls /\nb\n", result.stdout)
            self.assertEqual(path.read_text(encoding="utf-8"), image)
            again = run_cli(["--vfs", str(path)], "ls /\nexit\n")
            self.assertIn("a\nempty\n", again.stdout)

    def test_invalid_image_and_script_are_reported(self):
        """Ошибки загрузки отображаются, после чего можно вводить команды."""
        with tempfile.TemporaryDirectory() as directory:
            image = Path(directory) / "broken.csv"
            data = "path,type,content\n/a,file,???\n"
            image.write_text(data, encoding="utf-8")
            args = ["--vfs", str(image), "--script", str(image) + ".txt"]
            result = run_cli(args, "vfsinfo\nexit\n")
            self.assertEqual(result.returncode, 0)
            self.assertIn("VFS:", result.stdout)
            self.assertIn("invalid base64", result.stdout)
            self.assertIn("script:", result.stdout)
            self.assertIn("файлов: 0", result.stdout)

    def test_unknown_cli_option_is_rejected(self):
        """Неподдерживаемый параметр запуска возвращает ненулевой код."""
        result = run_cli(["--not-an-option"])
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("unrecognized arguments", result.stderr)

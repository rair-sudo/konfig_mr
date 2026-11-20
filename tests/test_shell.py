"""Тесты диалога и разбора команд."""

import io
import unittest

from src.errors import ShellError
from src.parser import parse_line
from src.shell import Shell


class ParserTests(unittest.TestCase):
    """Проверки командного парсера."""

    def test_quotes_and_escapes(self):
        """Пробелы внутри кавычек и экранированные символы сохраняются."""
        result = parse_line("ls 'one two' \"three four\" five\\ six")
        self.assertEqual(result, ["ls", "one two", "three four", "five six"])

    def test_unclosed_quote(self):
        """Незакрытая кавычка превращается в понятную ошибку."""
        with self.assertRaises(ShellError):
            parse_line("ls 'unclosed")


class ShellTests(unittest.TestCase):
    """Проверки базового цикла."""

    def setUp(self):
        """Создаёт оболочку с перехватом вывода."""
        self.output = io.StringIO()
        self.shell = Shell(self.output)

    def test_prompt_uses_host_data(self):
        """Приглашение содержит пользователя и имя компьютера."""
        prompt = self.shell.prompt()
        self.assertIn(self.shell.user, prompt)
        self.assertIn(self.shell.host, prompt)
        self.assertTrue(prompt.endswith("$ "))

    def test_stub_quotes_and_errors(self):
        """Заглушки печатают аргументы, а ошибки не закрывают оболочку."""
        self.assertTrue(self.shell.execute('ls "two words"'))
        self.assertIn("two words", self.output.getvalue())
        self.assertFalse(self.shell.execute("unknown"))
        self.assertFalse(self.shell.execute("cd '"))
        self.assertFalse(self.shell.execute("exit extra"))
        self.assertTrue(self.shell.running)

    def test_repl_and_exit(self):
        """Интерактивный цикл завершается по exit."""
        self.shell.run(io.StringIO("cd path\nexit\nls\n"))
        self.assertFalse(self.shell.running)
        self.assertIn("cd:", self.output.getvalue())
        self.assertNotIn("ls:", self.output.getvalue())

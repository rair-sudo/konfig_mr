"""Модульные проверки команд чтения и навигации по виртуальному дереву."""

import calendar
from datetime import date
import unittest
from unittest.mock import patch

from src.commands import cal, cd, head, ls
from src.errors import ShellError
from src.vfs import Node, Vfs


class CommandTests(unittest.TestCase):
    """Проверки команд на дереве, построенном без файловых образцов."""

    def setUp(self):
        """Создаёт дерево с файлами, скрытыми именами и подкаталогами."""
        self.vfs = Vfs()
        self.vfs.root.children = {
            "alpha": Node("alpha", False, b"a\nb\nc\n"),
            ".secret": Node(".secret", False, b"secret"),
            "dir": Node("dir", True, children={
                "child": Node("child", False, b"child"),
                ".hidden": Node(".hidden", False, b"hidden"),
                "sub": Node("sub", True),
            }),
            "-dash": Node("-dash", False, b"dash"),
        }

    def test_ls_default_hidden_and_options(self):
        """Без -a скрытые имена исчезают, а с -a показаны также . и ..."""
        self.assertEqual(ls(self.vfs, []), "-dash\nalpha\ndir\n")
        self.assertEqual(
            ls(self.vfs, ["-a", "/dir"]),
            ".\n..\n.hidden\nchild\nsub\n",
        )
        long_output = ls(self.vfs, ["-la", "/dir"])
        self.assertIn("-      6 .hidden\n", long_output)
        self.assertIn("d      0 sub\n", long_output)

    def test_ls_paths_multiple_and_separator(self):
        """Файлы, несколько каталогов, относительные пути и -- работают."""
        cd(self.vfs, ["dir"])
        self.assertEqual(ls(self.vfs, ["child"]), "child\n")
        self.assertEqual(ls(self.vfs, ["--", "/-dash"]), "/-dash\n")
        output = ls(self.vfs, ["/alpha", ".", "sub"])
        self.assertTrue(output.startswith("/alpha\n\n.:\n"))
        self.assertIn("\n\nsub:\n", output)

    def test_ls_errors_and_empty_directory(self):
        """Пустой каталог не выдаёт текста, неправильные пути дают ошибки."""
        self.assertEqual(ls(self.vfs, ["/dir/sub"]), "")
        for args in (["-q"], ["/missing"], ["/alpha/"]):
            with self.subTest(args=args), self.assertRaises(ShellError):
                ls(self.vfs, args)

    def test_cd_relative_absolute_and_home(self):
        """cd нормализует . и .. и без аргумента возвращается в корень."""
        self.assertEqual(cd(self.vfs, ["/dir/sub"]), "")
        self.assertEqual(self.vfs.cwd_path(), "/dir/sub")
        cd(self.vfs, [".././sub/.."])
        self.assertEqual(self.vfs.cwd_path(), "/dir")
        cd(self.vfs, [])
        self.assertEqual(self.vfs.cwd_path(), "/")
        cd(self.vfs, ["../../"])
        self.assertEqual(self.vfs.cwd_path(), "/")
        self.vfs.root.children["-d"] = Node("-d", True)
        cd(self.vfs, ["--", "-d"])
        self.assertEqual(self.vfs.cwd_path(), "/-d")
        cd(self.vfs, ["--"])
        self.assertEqual(self.vfs.cwd_path(), "/")

    def test_cd_errors_preserve_cwd(self):
        """Файл, отсутствующий путь и лишние аргументы не меняют cwd."""
        for args in (["alpha"], ["missing"], ["dir", "sub"]):
            with self.subTest(args=args), self.assertRaises(ShellError):
                cd(self.vfs, args)
            self.assertEqual(self.vfs.cwd, [])

    def test_head_defaults_and_line_counts(self):
        """По умолчанию выдаются 10 LF-строк, включая завершающий LF."""
        data = b"".join(f"{i}\n".encode() for i in range(12))
        self.vfs.root.children["lines"] = Node("lines", False, data)
        self.assertEqual(head(self.vfs, ["lines"]), data[:20].decode())
        self.assertEqual(head(self.vfs, ["-n", "0", "lines"]), "")
        self.assertEqual(head(self.vfs, ["-n2", "lines"]), "0\n1\n")
        self.assertEqual(head(self.vfs, ["-n", "+2", "lines"]), "0\n1\n")
        self.assertEqual(head(self.vfs, ["-n", "-1", "alpha"]), "a\nb\n")
        self.assertEqual(head(self.vfs, ["-n-0", "alpha"]), "a\nb\nc\n")

    def test_head_binary_and_unterminated_line(self):
        """Некорректный UTF-8 заменяется, NUL и CR не теряются."""
        self.vfs.root.children["bin"] = Node(
            "bin", False, b"a\r\nb\x00\xff\rc\nlast")
        self.assertEqual(head(self.vfs, ["-n", "2", "bin"]),
                         "a\r\nb\x00\ufffd\rc\n")
        self.assertEqual(head(self.vfs, ["bin"]),
                         "a\r\nb\x00\ufffd\rc\nlast")

    def test_head_multiple_files_and_separator(self):
        """Для нескольких файлов выдаются заголовки с правильными именами."""
        output = head(self.vfs, ["-n", "1", "alpha", "/dir/child"])
        self.assertEqual(output, "==> alpha <==\na\n\n"
                         "==> /dir/child <==\nchild")
        self.assertEqual(head(self.vfs, ["--", "-dash"]), "dash")

    def test_head_errors(self):
        """Отсутствие stdin, опции, плохое число и каталог дают ShellError."""
        cases = ([], ["-n"], ["-n", "abc", "alpha"], ["-z", "alpha"],
                 ["missing"], ["dir"], ["alpha/"], ["-n", "9" * 5000])
        for args in cases:
            with self.subTest(args=args[:2]), self.assertRaises(ShellError):
                head(self.vfs, args)

    def test_cal_current_month_and_month_year(self):
        """Календарь месяца и сегодняшнее значение начинаются с воскресенья."""
        formatter = calendar.TextCalendar(calendar.SUNDAY)
        with patch("src.commands.date") as fake_date:
            fake_date.today.return_value = date(2024, 2, 29)
            expected = formatter.formatmonth(2024, 2)
            self.assertEqual(cal(self.vfs, []), expected)
        self.assertEqual(cal(self.vfs, ["2", "2024"]),
                         formatter.formatmonth(2024, 2))
        self.assertIn("29", cal(self.vfs, ["2", "2024"]))

    def test_cal_full_year_and_limits(self):
        """Один аргумент задаёт год; границы годов включительные."""
        formatter = calendar.TextCalendar(calendar.SUNDAY)
        self.assertEqual(cal(self.vfs, ["2024"]), formatter.formatyear(2024))
        self.assertIn("January", cal(self.vfs, ["1"]))
        self.assertIn("December", cal(self.vfs, ["12", "9999"]))

    def test_cal_invalid_arguments(self):
        """Неверное количество или диапазон аргументов вызывают ошибку."""
        cases = (["0"], ["10000"], ["0", "2024"], ["13", "2024"],
                 ["x"], ["1", "2024", "3"], ["1.0", "2024"])
        for args in cases:
            with self.subTest(args=args), self.assertRaises(ShellError):
                cal(self.vfs, args)


if __name__ == "__main__":
    unittest.main()

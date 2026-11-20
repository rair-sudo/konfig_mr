"""Модульные проверки операций изменения виртуальной файловой системы."""

import base64
from pathlib import Path
import tempfile
import unittest

from src.commands import cd
from src.errors import ShellError
from src.mutations import mv, rmdir
from src.vfs import Node, Vfs, load_vfs


class MutationTests(unittest.TestCase):
    """Проверки удаления и перемещения файлов и каталогов."""

    def setUp(self):
        """Создаёт независимое дерево в памяти."""
        self.vfs = Vfs()
        self.vfs.root.children = {
            "a": Node("a", False, b"alpha"),
            "b": Node("b", False, b"bravo"),
            "empty": Node("empty", True),
            "other": Node("other", True),
            "dir": Node("dir", True, children={
                "child": Node("child", False, b"inside"),
                "nested": Node("nested", True, children={
                    "leaf": Node("leaf", True),
                }),
            }),
        }

    def test_rmdir_empty_relative_and_multiple(self):
        """Удаление нескольких пустых каталогов допускает относительные пути."""
        self.assertEqual(rmdir(self.vfs, ["empty", "/other"]), "")
        self.assertNotIn("empty", self.vfs.root.children)
        self.assertNotIn("other", self.vfs.root.children)
        cd(self.vfs, ["dir"])
        rmdir(self.vfs, ["nested/leaf"])
        self.assertEqual(self.vfs.find("nested").children, {})

    def test_rmdir_root_cwd_and_ancestors_are_protected(self):
        """Корень, рабочий каталог и его предки запрещено удалять."""
        cd(self.vfs, ["/dir/nested/leaf"])
        for path in ("/", ".", "..", "/dir", "/dir/nested/leaf"):
            with self.subTest(path=path), self.assertRaises(ShellError):
                rmdir(self.vfs, [path])
        self.assertEqual(self.vfs.cwd_path(), "/dir/nested/leaf")

    def test_rmdir_errors_and_partial_changes(self):
        """На ошибке нескольких путей ранние изменения остаются в памяти."""
        for args in ([], ["missing"], ["a"], ["dir"], ["-p", "empty"]):
            with self.subTest(args=args), self.assertRaises(ShellError):
                rmdir(self.vfs, args)
        with self.assertRaises(ShellError):
            rmdir(self.vfs, ["empty", "missing", "other"])
        self.assertNotIn("empty", self.vfs.root.children)
        self.assertIn("other", self.vfs.root.children)

    def test_rmdir_separator(self):
        """Файловые имена с дефисом доступны после --."""
        self.vfs.root.children["-d"] = Node("-d", True)
        rmdir(self.vfs, ["--", "-d"])
        self.assertNotIn("-d", self.vfs.root.children)

    def test_mv_rename_and_replace_file(self):
        """Переименование и перезапись файла сохраняют исходные байты."""
        self.assertEqual(mv(self.vfs, ["a", "renamed"]), "")
        self.assertEqual(self.vfs.find("/renamed").name, "renamed")
        self.assertNotIn("a", self.vfs.root.children)
        mv(self.vfs, ["renamed", "b"])
        self.assertEqual(self.vfs.find("/b").content, b"alpha")
        self.assertNotIn("renamed", self.vfs.root.children)

    def test_mv_files_into_directory(self):
        """Несколько файлов перемещаются в существующий каталог."""
        mv(self.vfs, ["a", "b", "empty"])
        self.assertEqual(self.vfs.find("/empty/a").content, b"alpha")
        self.assertEqual(self.vfs.find("/empty/b").content, b"bravo")
        self.assertNotIn("a", self.vfs.root.children)
        self.assertNotIn("b", self.vfs.root.children)

    def test_mv_directory_and_nested_cwd(self):
        """Перемещение предка переносит вложенную рабочую директорию."""
        cd(self.vfs, ["/dir/nested/leaf"])
        mv(self.vfs, ["/dir", "/other"])
        self.assertEqual(self.vfs.cwd, ["other", "dir", "nested", "leaf"])
        self.assertEqual(self.vfs.cwd_path(), "/other/dir/nested/leaf")
        self.assertEqual(self.vfs.find("../../child").content, b"inside")
        mv(self.vfs, ["/other/dir", "/renamed"])
        self.assertEqual(self.vfs.cwd_path(), "/renamed/nested/leaf")

    def test_mv_replace_empty_directory(self):
        """Каталог может заменить только пустой каталог одинакового типа."""
        self.vfs.find("/other").children["dir"] = Node("dir", True)
        mv(self.vfs, ["dir", "other"])
        self.assertEqual(self.vfs.find("/other/dir/child").content, b"inside")
        self.assertNotIn("dir", self.vfs.root.children)

    def test_mv_multiple_with_relative_destination_and_moved_cwd(self):
        """Относительное назначение сохраняется после переноса предка cwd."""
        cd(self.vfs, ["/dir/nested/leaf"])
        mv(self.vfs, ["/dir", "/b", "../../../other"])
        self.assertEqual(self.vfs.cwd_path(), "/other/dir/nested/leaf")
        self.assertEqual(self.vfs.find("/other/b").content, b"bravo")

    def test_mv_reject_nonempty_directory(self):
        """Несовместимая перезапись не меняет ни один из узлов."""
        other = self.vfs.find("/other")
        other.children["dir"] = Node("dir", True, children={
            "file": Node("file", False, b"old")})
        with self.assertRaises(ShellError):
            mv(self.vfs, ["dir", "other"])
        self.assertEqual(self.vfs.find("/dir/child").content, b"inside")
        self.assertEqual(self.vfs.find("/other/dir/file").content, b"old")

    def test_mv_reject_cross_type_overwrites(self):
        """Файл и каталог нельзя заменить объектом другого типа."""
        self.vfs.find("/other").children["a"] = Node("a", True)
        self.vfs.find("/other").children["dir"] = Node("dir", False, b"x")
        for args in (["a", "other"], ["dir", "other"], ["dir", "a"]):
            with self.subTest(args=args), self.assertRaises(ShellError):
                mv(self.vfs, args)
        self.assertEqual(self.vfs.find("a").content, b"alpha")
        self.assertTrue(self.vfs.find("dir").is_dir)

    def test_mv_reject_self_root_and_descendant(self):
        """Нельзя переместить корень, файл в себя или каталог внутрь себя."""
        cases = (["/", "/new"], ["a", "a"], ["dir", "dir"],
                 ["dir", "dir/nested"], ["dir", "dir/new"])
        for args in cases:
            with self.subTest(args=args), self.assertRaises(ShellError):
                mv(self.vfs, args)
        self.assertTrue(self.vfs.find("/dir/nested").is_dir)

    def test_mv_does_not_replace_directory_in_use(self):
        """Пустой каталог назначения, совпадающий с cwd, нельзя заменить."""
        self.vfs.find("/other").children["dir"] = Node("dir", True)
        cd(self.vfs, ["/other/dir"])
        with self.assertRaises(ShellError):
            mv(self.vfs, ["/dir", "/other"])
        self.assertEqual(self.vfs.cwd_path(), "/other/dir")
        self.assertTrue(self.vfs.find("/dir/nested").is_dir)

    def test_mv_errors_options_and_missing_targets(self):
        """Неверные аргументы и недоступные пути вызывают ShellError."""
        cases = ([], ["a"], ["-q", "a", "b"], ["missing", "new"],
                 ["a", "missing/child"], ["a/", "new"], ["a", "new/"],
                 ["a", "b", "missing"], ["a", "b", "dir/child"])
        for args in cases:
            with self.subTest(args=args), self.assertRaises(ShellError):
                mv(self.vfs, args)
        self.assertEqual(self.vfs.find("a").content, b"alpha")

    def test_mv_separator_and_partial_changes(self):
        """После -- имя с дефисом допустимо; выполненные переносы остаются."""
        self.vfs.root.children["-f"] = Node("-f", False, b"f")
        mv(self.vfs, ["--", "-f", "new"])
        self.assertEqual(self.vfs.find("new").content, b"f")
        with self.assertRaises(ShellError):
            mv(self.vfs, ["a", "missing", "other"])
        self.assertEqual(self.vfs.find("/other/a").content, b"alpha")

    def test_dotdot_must_not_hide_invalid_components(self):
        """Нельзя обойти отсутствующий путь или файл с помощью '..'."""
        cases = [
            ["/a/../b", "/new"],
            ["/missing/../b", "/new"],
            ["/b", "/a/../new"],
            ["/b", "/missing/../new"],
        ]
        for args in cases:
            with self.subTest(args=args), self.assertRaises(ShellError):
                mv(self.vfs, args)
        with self.assertRaises(ShellError):
            rmdir(self.vfs, ["/a/../empty"])
        self.assertTrue(self.vfs.find("/empty").is_dir)
        self.assertEqual(self.vfs.find("/b").content, b"bravo")

    def test_mutations_do_not_write_csv(self):
        """Мутации дерева не модифицируют исходный временный CSV-образ."""
        content = base64.b64encode(b"test").decode("ascii")
        image = f"path,type,content\n/a,file,{content}\n/empty,dir,\n"
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "image.csv"
            path.write_text(image, encoding="utf-8")
            vfs = load_vfs(path)
            mv(vfs, ["/a", "/b"])
            rmdir(vfs, ["/empty"])
            self.assertEqual(path.read_text(encoding="utf-8"), image)
            self.assertEqual(vfs.find("/b").content, b"test")


if __name__ == "__main__":
    unittest.main()

"""Tests for the in-memory filesystem and its strict CSV image loader."""

import base64
import csv
import io
import tempfile
import unittest
from pathlib import Path

from src.errors import ShellError
from src.vfs import Node, Vfs, load_vfs


PROJECT_ROOT = Path(__file__).resolve().parent.parent


class PathTests(unittest.TestCase):
    """Verify path normalization, lookup and mutable tree behavior."""

    def setUp(self):
        """Build a small tree without touching disk."""
        self.vfs = Vfs()
        self.vfs.root.children["a"] = Node("a", True)
        self.vfs.root.children["a"].children["space dir"] = Node(
            "space dir", True
        )
        self.vfs.root.children["a"].children["file"] = Node(
            "file", False, b"abc\x00\xff"
        )

    def test_empty_vfs_and_independent_children(self):
        """Root is empty and nodes do not share children dictionaries."""
        empty = Vfs()
        self.assertEqual(empty.cwd, [])
        self.assertEqual(empty.cwd_path(), "/")
        self.assertEqual(empty.name, "")
        self.assertTrue(empty.root.is_dir)
        self.assertEqual(empty.root.name, "/")
        self.assertEqual(empty.root.content, b"")
        self.assertEqual(empty.root.children, {})
        other = Node("other", True)
        other.children["child"] = Node("child", False)
        self.assertEqual(empty.root.children, {})

    def test_absolute_and_relative_normalization(self):
        """Paths normalize dots, slashes and attempts to go above root."""
        self.vfs.cwd = ["a", "space dir"]
        self.assertEqual(self.vfs.cwd_path(), "/a/space dir")
        self.assertEqual(self.vfs.split_path("."), ["a", "space dir"])
        self.assertEqual(self.vfs.split_path("../file"), ["a", "file"])
        self.assertEqual(self.vfs.split_path("/a//./file/"), ["a", "file"])
        self.assertEqual(self.vfs.split_path("../../../x"), ["x"])
        self.assertEqual(self.vfs.split_path("/../../"), [])
        self.assertEqual(self.vfs.find("../file").content, b"abc\x00\xff")
        self.assertIs(self.vfs.find("/a/space dir"), self.vfs.find("."))

    def test_empty_and_nul_paths_are_invalid(self):
        """Reject empty and NUL-containing paths with useful context."""
        for path in ("", "/a/\0bad"):
            with self.subTest(path=path), self.assertRaises(ShellError) as exc:
                self.vfs.find(path)
            self.assertIn("Invalid path", str(exc.exception))
            self.assertIn(repr(path), str(exc.exception))

    def test_lookup_root_existing_and_missing(self):
        """Root is special; only a missing final entry returns None."""
        parent, name, node = self.vfs.lookup("/")
        self.assertIsNone(parent)
        self.assertEqual(name, "/")
        self.assertIs(node, self.vfs.root)
        parent, name, node = self.vfs.lookup("/a/file")
        self.assertIs(parent, self.vfs.find("/a"))
        self.assertEqual(name, "file")
        self.assertIs(node, self.vfs.find("/a/file"))
        parent, name, node = self.vfs.lookup("/a/missing name")
        self.assertIs(parent, self.vfs.find("/a"))
        self.assertEqual(name, "missing name")
        self.assertIsNone(node)

    def test_find_reports_missing_component_and_original_path(self):
        """Both the requested path and the failing component are reported."""
        with self.assertRaises(ShellError) as exc:
            self.vfs.find("/a/missing/deeper")
        self.assertIn("No such file or directory", str(exc.exception))
        self.assertIn("/a/missing/deeper", str(exc.exception))
        self.assertIn("'/a/missing'", str(exc.exception))

    def test_find_reports_intermediate_file(self):
        """A file cannot be traversed as an intermediate directory."""
        with self.assertRaises(ShellError) as exc:
            self.vfs.find("/a/file/child")
        self.assertIn("Not a directory", str(exc.exception))
        self.assertIn("'/a/file'", str(exc.exception))
        self.assertIn("/a/file/child", str(exc.exception))

    def test_dot_components_do_not_hide_invalid_traversal(self):
        """Neither dot nor dot-dot skips a missing or non-directory prefix."""
        cases = (
            ("/a/file/..", "Not a directory"),
            ("/a/file/.", "Not a directory"),
            ("/a/file/", "Not a directory"),
            ("/a/missing/../file", "No such file or directory"),
        )
        for path, message in cases:
            for operation in (self.vfs.find, self.vfs.lookup):
                with self.subTest(path=path, operation=operation):
                    with self.assertRaises(ShellError) as exc:
                        operation(path)
                    self.assertIn(message, str(exc.exception))

    def test_lookup_requires_a_directory_parent(self):
        """Missing parents and parents that are files both raise ShellError."""
        cases = (
            ("/a/missing/child", "No such file or directory"),
            ("/a/file/child", "Not a directory"),
        )
        for path, message in cases:
            with self.subTest(path=path), self.assertRaises(ShellError) as exc:
                self.vfs.lookup(path)
            self.assertIn(message, str(exc.exception))
            self.assertIn(path, str(exc.exception))

    def test_mutation_supports_move_and_remove_in_memory(self):
        """Parents' dictionaries support moving files and removing dirs."""
        old_parent, old_name, node = self.vfs.lookup("/a/file")
        new_parent, new_name, _ = self.vfs.lookup("/a/space dir/new name")
        old_parent.children.pop(old_name)
        node.name = new_name
        new_parent.children[new_name] = node
        self.assertEqual(self.vfs.find("/a/space dir/new name").content,
                         b"abc\x00\xff")
        new_parent.children.pop(new_name)
        self.vfs.find("/a").children.pop("space dir")
        self.assertIsNone(self.vfs.lookup("/a/space dir")[2])


class CsvTests(unittest.TestCase):
    """Exercise valid and invalid images while checking source immutability."""

    def setUp(self):
        """Allocate one temporary CSV path per test."""
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "input.csv"

    def save(self, payload):
        """Write exact test bytes without newline conversion."""
        self.path.write_bytes(payload)
        return self.path

    def check_invalid(self, payload, *details):
        """An invalid image raises with context and leaves bytes intact."""
        self.save(payload)
        with self.assertRaises(ShellError) as exc:
            load_vfs(self.path)
        message = str(exc.exception)
        self.assertIn(str(self.path), message)
        for detail in details:
            self.assertIn(detail, message)
        self.assertEqual(self.path.read_bytes(), payload)

    def test_bundled_examples(self):
        """The three sample images cover root, multiple files and depth."""
        folder = PROJECT_ROOT / "vfs"
        minimal = load_vfs(folder / "minimal.csv")
        self.assertEqual(minimal.name, "minimal.csv")
        self.assertEqual(minimal.root.children, {})
        files = load_vfs(folder / "several.csv")
        self.assertEqual(files.find("/binary.dat").content, b"\x00\xff\x80\xff")
        self.assertEqual(files.find("/empty.txt").content, b"")
        self.assertEqual(files.find("/empty-dir").children, {})
        deep = load_vfs(folder / "deep.csv")
        self.assertEqual(deep.find("/a/b/c/hello world.txt").content,
                         b"Space in the name\n")
        self.assertEqual(deep.find("/a/b/c/empty").children, {})
        self.assertEqual(deep.find("/other/nested/empty").children, {})

    def test_header_only_is_an_empty_filesystem(self):
        """An image need not explicitly declare the root."""
        payload = b"path,type,content\n"
        image = load_vfs(self.save(payload))
        self.assertEqual(image.root.children, {})
        self.assertEqual(image.cwd_path(), "/")
        self.assertEqual(self.path.read_bytes(), payload)

    def test_any_order_and_implicit_parents(self):
        """Children may precede declared parents and create other parents."""
        payload = (
            b"path,type,content\n"
            b"/outer/inner/file,file,AAEC/w==\n"
            b"/outer/inner/empty,dir,\n"
            b"/outer,dir,\n"
            b"/outer/inner,dir,\n"
        )
        image = load_vfs(self.save(payload))
        self.assertEqual(image.find("/outer/inner/file").content,
                         b"\x00\x01\x02\xff")
        self.assertEqual(image.find("/outer/inner/empty").children, {})
        self.assertEqual(self.path.read_bytes(), payload)

    def test_deep_images_are_not_limited_by_python_recursion(self):
        """Build and resolve more levels than the typical recursion limit."""
        levels = [f"part{index}" for index in range(1200)]
        path = "/" + "/".join(levels)
        payload = f"path,type,content\n{path},file,WA==\n".encode("utf-8")
        image = load_vfs(self.save(payload))
        self.assertEqual(image.find(path).content, b"X")
        self.assertEqual(image.split_path(path), levels)

    def test_quoted_unicode_comma_quote_and_newline(self):
        """CSV quoting preserves Unicode and unusual but valid path names."""
        stream = io.StringIO(newline="")
        writer = csv.writer(stream, lineterminator="\r\n")
        writer.writerow(["path", "type", "content"])
        path = '/каталог/a,"b\nnext line'
        writer.writerow([path, "file", "ZGF0YQ=="])
        payload = stream.getvalue().encode("utf-8")
        image = load_vfs(self.save(payload))
        self.assertEqual(image.find(path).content, b"data")
        self.assertEqual(self.path.read_bytes(), payload)

    def test_normalized_image_paths(self):
        """CSV absolute paths use the same lexical normalization as lookups."""
        payload = b"path,type,content\n/a//b/../c/,file,WA==\n"
        image = load_vfs(self.save(payload))
        self.assertEqual(image.find("/a/c").content, b"X")
        self.assertEqual(image.find("/a").children.keys(), {"c"})

    def test_large_base64_field_and_restored_csv_limit(self):
        """Files may exceed the stdlib CSV field-size default."""
        old_limit = csv.field_size_limit()
        size = max(old_limit + 1, 200_000)
        content = b"\x00\xff" * size
        payload = b"path,type,content\n/big,file," + base64.b64encode(content)
        self.save(payload)
        self.assertEqual(load_vfs(self.path).find("/big").content, content)
        self.assertEqual(csv.field_size_limit(), old_limit)
        self.assertEqual(self.path.read_bytes(), payload)

    def test_bad_headers_and_empty_input(self):
        """Only the exact three-column header is accepted."""
        cases = (
            b"", b"path,type\n", b"type,path,content\n",
            b"path,type,content,extra\n", b"\xef\xbb\xbfpath,type,content\n",
        )
        for payload in cases:
            with self.subTest(payload=payload):
                self.check_invalid(payload, "line 1", "expected header")

    def test_bad_column_counts_and_blank_record(self):
        """Missing, extra and blank records identify their source line."""
        rows = (b"/x,file\n", b"/x,file,,extra\n", b"\n")
        for row in rows:
            with self.subTest(row=row):
                self.check_invalid(b"path,type,content\n" + row,
                                   "line 2", "expected 3 fields")

    def test_bad_paths_and_types(self):
        """Reject relative paths, NULs, unknown types and a file root."""
        cases = (
            (b"x,file,\n", "expected absolute path"),
            (b",dir,\n", "expected absolute path"),
            (b"/x\x00y,file,\n", "NUL in path"),
            (b"/x,symlink,\n", "invalid type"),
            (b"/x,FILE,\n", "invalid type"),
            (b"/,file,\n", "root must be a directory"),
            (b"/x,dir,AA==\n", "directory content is not empty"),
        )
        for row, detail in cases:
            with self.subTest(row=row):
                self.check_invalid(b"path,type,content\n" + row,
                                   "line 2", detail)

    def test_bad_base64(self):
        """Reject invalid alphabet, bad padding and non-canonical pad bits."""
        cases = (b"a?==", b"A", b"AAA", b"YQ===", b"YR==", b"\xc3\xa9")
        for value in cases:
            with self.subTest(value=value):
                self.check_invalid(b"path,type,content\n/bin,file," + value,
                                   "line 2", "/bin", "base64")

    def test_duplicate_paths_after_normalization(self):
        """Duplicate declarations identify both the later and earlier line."""
        cases = (
            b"/a,dir,\n/a,file,\n",
            b"/a/b,dir,\n/a//b/.,dir,\n",
            b"/,dir,\n/a/..,dir,\n",
        )
        for rows in cases:
            with self.subTest(rows=rows):
                self.check_invalid(b"path,type,content\n" + rows,
                                   "line 3", "duplicate of line 2")

    def test_parent_file_conflicts_in_either_order(self):
        """All file-as-parent conflicts fail before any image is returned."""
        cases = (
            (b"/a,file,\n/a/b,file,\n", "line 3", "declared line 2"),
            (b"/a/b,file,\n/a,file,\n", "line 2", "declared line 3"),
        )
        for rows, line, declared in cases:
            with self.subTest(rows=rows):
                self.check_invalid(b"path,type,content\n" + rows,
                                   line, "parent '/a' is a file", declared)

    def test_bad_csv_quotes(self):
        """Catch unclosed, misplaced and post-quote characters."""
        cases = (
            b'"/unterminated,file,\n',
            b'/a"b,file,\n',
            b'"/a"bad,file,\n',
        )
        for row in cases:
            with self.subTest(row=row):
                self.check_invalid(b"path,type,content\n" + row, "line 2")

    def test_multiline_record_line_number(self):
        """After a quoted multiline path errors name physical source lines."""
        payload = b'path,type,content\n"/a\nb",file,\n/bad,nope,\n'
        self.check_invalid(payload, "line 4", "/bad", "invalid type")

    def test_invalid_utf8_and_missing_file(self):
        """I/O and encoding problems become contextual ShellErrors."""
        self.check_invalid(b"path,type,content\n/x,file,\xff", "invalid UTF-8")
        absent = self.path.parent / "absent.csv"
        with self.assertRaises(ShellError) as exc:
            load_vfs(absent)
        self.assertIn(str(absent), str(exc.exception))
        self.assertIn("cannot read CSV", str(exc.exception))

    def test_source_unchanged_after_in_memory_changes(self):
        """Moving or deleting nodes never writes through to the image."""
        payload = b"path,type,content\n/dir/file,file,AA==\n/empty,dir,\n"
        image = load_vfs(self.save(payload))
        node = image.find("/dir").children.pop("file")
        node.name = "renamed"
        image.root.children[node.name] = node
        image.root.children.pop("empty")
        self.assertEqual(self.path.read_bytes(), payload)
        self.assertEqual(load_vfs(self.path).find("/dir/file").content, b"\0")


if __name__ == "__main__":
    unittest.main()

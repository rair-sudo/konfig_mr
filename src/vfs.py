"""In-memory virtual filesystem and atomic UTF-8 CSV loading.

Paths use POSIX separators. split_path normalizes lexically, while find and
lookup check each traversed component before processing `.` or `..`; `..` at
root stays at root. Errors identify the requested path and the failing
component. No method writes to the source CSV.
"""

import base64
import binascii
import csv
import io
from dataclasses import dataclass, field
from pathlib import Path
from threading import Lock

from src.errors import ShellError

_CSV_LOCK = Lock()


@dataclass
class Node:
    """A mutable file or directory; directory entries live only in memory."""

    name: str
    is_dir: bool
    content: bytes = b""
    children: dict[str, "Node"] = field(default_factory=dict)


def _path_parts(path: str, initial: list[str]) -> list[str]:
    """Normalize a nonempty path without accessing the filesystem."""
    if not isinstance(path, str) or not path or "\0" in path:
        raise ShellError(f"Invalid path: {path!r}")
    parts = [] if path.startswith("/") else list(initial)
    for part in path.split("/"):
        if part in ("", "."):
            continue
        if part == "..":
            if parts:
                parts.pop()
        else:
            parts.append(part)
    return parts


class Vfs:
    """Mutable tree with a root, current directory and optional image name.

    Empty Vfs instances have an empty name. Loaded images use the CSV basename.
    Root lookup returns (None, '/', root). A missing final component in lookup
    returns None; a missing or non-directory parent raises ShellError.
    """

    def __init__(self, name: str = "") -> None:
        """Create an empty tree rooted at '/' with cwd initially at root."""
        self.name = name
        self.root = Node("/", True)
        self.cwd: list[str] = []

    def cwd_path(self) -> str:
        """Return the absolute current-directory path."""
        return "/" + "/".join(self.cwd)

    def split_path(self, path: str) -> list[str]:
        """Return normalized absolute path components relative to cwd."""
        return _path_parts(path, self.cwd)

    def _step(self, nodes, parts, part, path, allow_missing):
        """Follow one component, permitting only a missing final component."""
        node = nodes[-1]
        if not node.is_dir:
            component = "/" + "/".join(parts)
            raise ShellError(f"Not a directory: {component!r} (path {path!r})")
        if part == ".":
            return False
        if part == "..":
            if parts:
                parts.pop()
                nodes.pop()
            return False
        child = node.children.get(part)
        if child is None:
            if allow_missing:
                return True
            component = "/" + "/".join(parts + [part])
            raise ShellError(
                f"No such file or directory: {component!r} (path {path!r})"
            )
        parts.append(part)
        nodes.append(child)
        return False

    def _trace(self, path, allow_missing):
        """Trace raw components, preserving checks before dots are resolved."""
        self.split_path(path)
        prefix = [] if path.startswith("/") else list(self.cwd)
        steps = prefix + [part for part in path.split("/") if part]
        nodes = [self.root]
        parts = []
        for index, part in enumerate(steps):
            last = index == len(steps) - 1
            missing = self._step(
                nodes, parts, part, path, allow_missing and last
            )
            if missing:
                return nodes[-1], part, None
        node = nodes[-1]
        if path.endswith("/") and not node.is_dir:
            component = "/" + "/".join(parts)
            raise ShellError(f"Not a directory: {component!r} (path {path!r})")
        if not parts:
            return None, "/", node
        return nodes[-2], parts[-1], node

    def find(self, path: str) -> Node:
        """Return a node or raise ShellError on a missing path or parent."""
        return self._trace(path, False)[2]

    def lookup(self, path: str) -> tuple[Node | None, str, Node | None]:
        """Return parent, name and optional node; require a directory parent."""
        return self._trace(path, True)


@dataclass(frozen=True)
class _Entry:
    """A validated CSV declaration and its source location."""

    path: str
    parts: tuple[str, ...]
    is_dir: bool
    content: bytes
    line: int


def _csv_error(source: Path, line: int, message: str) -> ShellError:
    """Create an error identifying an image and physical source line."""
    return ShellError(f"{source}: line {line}: {message}")


def _quote_state(
    quoted: bool, field_start: bool, next_char: str, source: Path, line: int
) -> tuple[bool, bool, bool]:
    """Update CSV quote state and indicate a doubled quote to skip."""
    if quoted and next_char == '"':
        return True, False, True
    if quoted:
        return False, False, False
    if field_start:
        return True, False, False
    raise _csv_error(source, line, "quote in unquoted field")


def _check_quotes(text: str, source: Path) -> None:
    """Reject quotes in unquoted fields, which csv.strict otherwise accepts."""
    quoted = False
    field_start = True
    index = 0
    line = 1
    while index < len(text):
        char = text[index]
        next_char = text[index + 1:index + 2]
        if char == '"':
            quoted, field_start, skip = _quote_state(
                quoted, field_start, next_char, source, line
            )
            if skip:
                index += 1
        elif not quoted:
            field_start = char in ",\r\n"
        if char == "\n" or (char == "\r" and next_char != "\n"):
            line += 1
        index += 1


def _next_row(reader: object, source: Path) -> tuple[int, list[str]] | None:
    """Read a CSV record and report its starting physical line on errors."""
    line = reader.line_num + 1
    try:
        return line, next(reader)
    except StopIteration:
        return None
    except csv.Error as error:
        raise _csv_error(source, line, f"malformed CSV: {error}") from error


def _decode_content(value: str, source: Path, line: int, path: str) -> bytes:
    """Decode canonical base64, rejecting invalid characters and padding."""
    try:
        encoded = value.encode("ascii")
        decoded = base64.b64decode(encoded, validate=True)
    except (UnicodeEncodeError, binascii.Error, ValueError) as error:
        raise _csv_error(
            source, line, f"path {path!r}: invalid base64"
        ) from error
    if base64.b64encode(decoded) != encoded:
        raise _csv_error(source, line, f"path {path!r}: non-canonical base64")
    return decoded


def _image_path(path: str, source: Path, line: int) -> tuple[str, ...]:
    """Validate and normalize an absolute path from an image declaration."""
    if not path.startswith("/"):
        raise _csv_error(source, line, f"path {path!r}: expected absolute path")
    if "\0" in path:
        raise _csv_error(source, line, f"path {path!r}: NUL in path")
    return tuple(_path_parts(path, []))


def _parse_entry(row: list[str], source: Path, line: int) -> _Entry:
    """Validate one declaration and decode a file's complete byte content."""
    expected_columns = 3
    if len(row) != expected_columns:
        raise _csv_error(
            source, line, f"expected 3 fields, got {len(row)}"
        )
    path, kind, value = row
    parts = _image_path(path, source, line)
    if kind not in ("dir", "file"):
        raise _csv_error(source, line, f"path {path!r}: invalid type {kind!r}")
    if not parts and kind != "dir":
        raise _csv_error(
            source, line, f"path {path!r}: root must be a directory"
        )
    if kind == "dir" and value:
        raise _csv_error(
            source, line, f"path {path!r}: directory content is not empty"
        )
    content = b""
    if kind == "file":
        content = _decode_content(value, source, line, path)
    return _Entry(path, parts, kind == "dir", content, line)


def _read_entries(text: str, source: Path) -> dict[tuple[str, ...], _Entry]:
    """Read the exact header and reject duplicate normalized paths."""
    _check_quotes(text, source)
    reader = csv.reader(io.StringIO(text, newline=""), strict=True)
    record = _next_row(reader, source)
    header = ["path", "type", "content"]
    if record is None or record[1] != header:
        raise _csv_error(source, 1, "expected header path,type,content")
    entries: dict[tuple[str, ...], _Entry] = {}
    while True:
        record = _next_row(reader, source)
        if record is None:
            break
        line, row = record
        entry = _parse_entry(row, source, line)
        previous = entries.get(entry.parts)
        if previous is not None:
            raise _csv_error(
                source, line,
                f"path {entry.path!r}: duplicate of line {previous.line}",
            )
        entries[entry.parts] = entry
    return entries


def _check_parents(
    entries: dict[tuple[str, ...], _Entry], source: Path
) -> None:
    """Reject a file used as a parent regardless of CSV record order."""
    for entry in entries.values():
        for end in range(1, len(entry.parts)):
            ancestor = entries.get(entry.parts[:end])
            if ancestor is not None and not ancestor.is_dir:
                component = "/" + "/".join(entry.parts[:end])
                raise _csv_error(
                    source, entry.line,
                    f"path {entry.path!r}: parent {component!r} is a file "
                    f"(declared line {ancestor.line})",
                )


def _make_tree(entries: dict[tuple[str, ...], _Entry], name: str) -> Vfs:
    """Create a fresh tree, inserting declared parents before descendants."""
    result = Vfs(name)
    for entry in sorted(entries.values(), key=lambda item: len(item.parts)):
        if not entry.parts:
            continue
        parent = result.root
        for part in entry.parts[:-1]:
            parent = parent.children.setdefault(part, Node(part, True))
        name = entry.parts[-1]
        parent.children[name] = Node(name, entry.is_dir, entry.content)
    return result


def load_vfs(path: str | Path) -> Vfs:
    """Load a UTF-8 CSV image atomically; the source is never modified.

    Rows have exactly path,type,content. Absolute paths are normalized; type
    is dir or file. Directory content must be empty; file content is canonical
    base64, including an empty string for an empty file. Explicit duplicate
    paths and file-as-parent conflicts are errors. Missing parents are created.
    Image, physical line and relevant paths are included in validation errors.
    """
    source = Path(path)
    try:
        data = source.read_bytes()
    except OSError as error:
        raise ShellError(
            f"{source}: cannot read CSV: {error.strerror}"
        ) from error
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ShellError(
            f"{source}: invalid UTF-8 at byte {error.start}"
        ) from error
    with _CSV_LOCK:
        limit = csv.field_size_limit()
        try:
            csv.field_size_limit(max(limit, len(text)))
            entries = _read_entries(text, source)
        finally:
            csv.field_size_limit(limit)
    _check_parents(entries, source)
    return _make_tree(entries, source.name)

"""Команды чтения VFS; текстовые данные декодируются как UTF-8 с заменой.

Вывод сохраняет завершающий перевод строки, когда его выдала бы команда.
Календарь использует воскресенье первым днём и годы от 1 до 9999.
"""

import calendar
from datetime import date

from src.errors import ShellError

SINGLE_OPERAND = 1
MONTH_YEAR_OPERANDS = 2
FIRST_YEAR = 1
LAST_YEAR = 9999
FIRST_MONTH = 1
LAST_MONTH = 12
DEFAULT_HEAD_LINES = 10


def _ls_options(args: list[str]) -> tuple[bool, bool, list[str]]:
    """Разбирает комбинированные флаги ls и пути после --."""
    long_format = False
    show_all = False
    paths = []
    options = True
    for arg in args:
        if options and arg == "--":
            options = False
        elif options and arg.startswith("-") and arg != "-":
            if any(flag not in "al" for flag in arg[1:]):
                raise ShellError(f"invalid option: '{arg}'")
            long_format |= "l" in arg
            show_all |= "a" in arg
        else:
            paths.append(arg)
    return long_format, show_all, paths or ["."]


def _long_entry(name: str, node) -> str:
    """Выводит тип и размер, не выдумывая отсутствующие в VFS метаданные."""
    kind = "d" if node.is_dir else "-"
    size = len(node.children) if node.is_dir else len(node.content)
    return f"{kind} {size:>6} {name}"


def _directory_entries(vfs, path: str, node, show_all: bool) -> list:
    """Возвращает отсортированные видимые записи, включая . и .. с -a."""
    entries = [(name, child) for name, child in node.children.items()
               if show_all or not name.startswith(".")]
    if show_all:
        parent = vfs.find(path.rstrip("/") + "/..")
        entries.extend([(".", node), ("..", parent)])
    return sorted(entries, key=lambda entry: entry[0])


def _ls_lines(entries: list, long_format: bool) -> list[str]:
    """Форматирует записи ls по одной на строку."""
    if long_format:
        return [_long_entry(name, node) for name, node in entries]
    return [name for name, _node in entries]


def _ls_nodes(vfs, paths: list[str]) -> tuple[list, list]:
    """Проверяет пути и разделяет файлы и каталоги для ls."""
    files = []
    directories = []
    for path in paths:
        node = vfs.find(path)
        if path.endswith("/") and not node.is_dir:
            raise ShellError(f"'{path}': Not a directory")
        if node.is_dir:
            directories.append((path, node))
        else:
            files.append((path, node))
    return files, directories


def ls(vfs, args: list[str]) -> str:
    """Показывает файлы и содержимое каталогов; поддерживает -a и -l."""
    long_format, show_all, paths = _ls_options(args)
    files, directories = _ls_nodes(vfs, paths)
    sections = []
    if files:
        sections.append("\n".join(_ls_lines(files, long_format)))
    for path, node in directories:
        entries = _directory_entries(vfs, path, node, show_all)
        lines = _ls_lines(entries, long_format)
        if len(paths) > SINGLE_OPERAND:
            lines.insert(0, f"{path}:")
        sections.append("\n".join(lines))
    result = "\n\n".join(section for section in sections if section)
    return result + "\n" if result else ""


def cd(vfs, args: list[str]) -> str:
    """Меняет рабочий каталог; без аргументов переходит в корень."""
    if args[:1] == ["--"]:
        args = args[1:]
    if len(args) > SINGLE_OPERAND:
        raise ShellError("too many arguments")
    path = args[0] if args else "/"
    node = vfs.find(path)
    if not node.is_dir:
        raise ShellError(f"'{path}': Not a directory")
    vfs.cwd = vfs.split_path(path)
    return ""


def _head_count(value: str) -> tuple[int, bool]:
    """Читает количество строк, в том числе отрицательный вариант GNU head."""
    digits = value[1:] if value.startswith(("-", "+")) else value
    if not digits or not digits.isascii() or not digits.isdigit():
        raise ShellError(f"invalid number of lines: '{value}'")
    try:
        count = int(digits)
    except ValueError as exc:
        raise ShellError(f"invalid number of lines: '{value}'") from exc
    return count, value.startswith("-")


def _head_option(args: list[str], index: int) -> tuple[int, bool, int]:
    """Читает одну опцию head вместе с её числовым аргументом."""
    arg = args[index]
    if arg == "-n":
        index += 1
        if index == len(args):
            raise ShellError("option requires an argument -- 'n'")
        count, exclude = _head_count(args[index])
        return count, exclude, index
    if arg.startswith("-n"):
        count, exclude = _head_count(arg[2:])
        return count, exclude, index
    raise ShellError(f"invalid option: '{arg}'")


def _head_options(args: list[str]) -> tuple[int, bool, list[str]]:
    """Разбирает -n N, -nN и пути, отделяемые через --."""
    count, exclude = DEFAULT_HEAD_LINES, False
    paths = []
    options = True
    index = 0
    while index < len(args):
        arg = args[index]
        if options and arg == "--":
            options = False
        elif options and arg.startswith("-"):
            count, exclude, index = _head_option(args, index)
        else:
            paths.append(arg)
        index += 1
    if not paths:
        raise ShellError("missing file operand (standard input is unavailable)")
    return count, exclude, paths


def _head_content(content: bytes, count: int, exclude: bool) -> str:
    """Считает только LF концом строки и декодирует результат с заменой."""
    parts = content.split(b"\n")
    lines = [part + b"\n" for part in parts[:-1]]
    if parts[-1]:
        lines.append(parts[-1])
    selected = lines[:max(0, len(lines) - count)] if exclude else lines[:count]
    return b"".join(selected).decode("utf-8", errors="replace")


def head(vfs, args: list[str]) -> str:
    """Выдаёт первые 10 или -n N строк указанных файлов VFS."""
    count, exclude, paths = _head_options(args)
    sections = []
    for path in paths:
        node = vfs.find(path)
        if path.endswith("/") and not node.is_dir:
            raise ShellError(f"'{path}': Not a directory")
        if node.is_dir:
            raise ShellError(f"'{path}': Is a directory")
        text = _head_content(node.content, count, exclude)
        if len(paths) > SINGLE_OPERAND:
            text = f"==> {path} <==\n" + text
        sections.append(text)
    multiple = len(paths) > SINGLE_OPERAND
    return "\n".join(sections) if multiple else sections[0]


def _calendar_numbers(args: list[str]) -> tuple[int | None, int]:
    """Проверяет MONTH YEAR или YEAR; допустимые годы от 1 до 9999."""
    if len(args) > MONTH_YEAR_OPERANDS:
        raise ShellError("expected [MONTH] YEAR")
    if not args:
        today = date.today()
        return today.month, today.year
    try:
        numbers = [int(arg) for arg in args]
    except ValueError as exc:
        raise ShellError("month and year must be integers") from exc
    has_month = len(numbers) == MONTH_YEAR_OPERANDS
    month, year = (numbers[0], numbers[1]) if has_month else (None, numbers[0])
    if not FIRST_YEAR <= year <= LAST_YEAR:
        raise ShellError("year must be between 1 and 9999")
    if month is not None and not FIRST_MONTH <= month <= LAST_MONTH:
        raise ShellError("month must be between 1 and 12")
    return month, year


def cal(vfs, args: list[str]) -> str:
    """Показывает текущий месяц, MONTH YEAR или весь YEAR."""
    del vfs
    month, year = _calendar_numbers(args)
    formatter = calendar.TextCalendar(firstweekday=calendar.SUNDAY)
    if month is not None:
        return formatter.formatmonth(year, month)
    return formatter.formatyear(year)

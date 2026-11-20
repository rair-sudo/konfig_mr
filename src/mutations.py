"""Команды изменения VFS, не затрагивающие реальную файловую систему.

При ошибке в нескольких операндах уже выполненные изменения сохраняются.
"""

from src.errors import ShellError

MIN_MOVE_OPERANDS = 2


def _operands(args: list[str]) -> list[str]:
    """Принимает пути и разделитель --, неподдерживаемые опции отклоняет."""
    options = True
    paths = []
    for arg in args:
        if options and arg == "--":
            options = False
        elif options and arg.startswith("-") and arg != "-":
            raise ShellError(f"invalid option: '{arg}'")
        else:
            paths.append(arg)
    return paths


def _absolute(parts: list[str]) -> str:
    """Возвращает абсолютное текстовое представление пути VFS."""
    return "/" + "/".join(parts)


def _locate(vfs, path: str):
    """Возвращает родителя, имя, узел или None и канонический путь."""
    if not path:
        raise ShellError("'': No such file or directory")
    parent, name, node = vfs.lookup(path)
    parts = vfs.split_path(path)
    return parent, name, node, parts


def _is_ancestor(parts: list[str], path: list[str]) -> bool:
    """Проверяет, совпадает ли путь с каталогом или лежит внутри него."""
    return path[:len(parts)] == parts


def _remove_directory(vfs, path: str) -> None:
    """Удаляет один пустой каталог, не затрагивая текущий путь."""
    parent, name, node, parts = _locate(vfs, path)
    if node is None:
        raise ShellError(
            f"failed to remove '{path}': No such file or directory")
    if not node.is_dir:
        raise ShellError(f"failed to remove '{path}': Not a directory")
    if parent is None or _is_ancestor(parts, vfs.cwd):
        raise ShellError(f"failed to remove '{path}': Directory is in use")
    if node.children:
        raise ShellError(f"failed to remove '{path}': Directory not empty")
    del parent.children[name]


def rmdir(vfs, args: list[str]) -> str:
    """Удаляет пустые каталоги по порядку; корень и cwd защищены."""
    paths = _operands(args)
    if not paths:
        raise ShellError("missing operand")
    for path in paths:
        _remove_directory(vfs, path)
    return ""


def _destination(vfs, path: str, source_name: str):
    """Определяет конечный путь с учётом существующего каталога."""
    parent, name, node, parts = _locate(vfs, path)
    if path.endswith("/") and (node is None or not node.is_dir):
        raise ShellError(f"'{path}': Not a directory")
    if node is not None and node.is_dir:
        parent = node
        name = source_name
        parts = parts + [source_name]
        node = parent.children.get(source_name)
    return parent, name, node, parts


def _validate_replacement(vfs, source, target, target_parts):
    """Запрещает несовместимую перезапись и удаление активного каталога."""
    if target is None:
        return
    if source.is_dir != target.is_dir:
        raise ShellError(
            "cannot overwrite a file with a directory or vice versa")
    if target.is_dir and target.children:
        raise ShellError("cannot overwrite a non-empty directory")
    if target.is_dir and _is_ancestor(target_parts, vfs.cwd):
        raise ShellError("cannot overwrite a directory in use")


def _validate_target(vfs, source, target, source_parts, target_parts):
    """Проверяет несовместимые перезаписи и перемещение в самого себя."""
    if source is target or source_parts == target_parts:
        raise ShellError("source and destination are the same")
    if source.is_dir and _is_ancestor(source_parts, target_parts):
        raise ShellError("cannot move a directory into itself")
    _validate_replacement(vfs, source, target, target_parts)


def _move_one(vfs, source_path: str, destination_path: str) -> None:
    """Атомарно перемещает один узел после всех проверок."""
    parent, name, source, source_parts = _locate(vfs, source_path)
    if source is None:
        raise ShellError(
            f"cannot stat '{source_path}': No such file or directory")
    if source_path.endswith("/") and not source.is_dir:
        raise ShellError(f"'{source_path}': Not a directory")
    if parent is None:
        raise ShellError("cannot move the root directory")
    target_parent, target_name, target, target_parts = _destination(
        vfs, destination_path, name)
    _validate_target(vfs, source, target, source_parts, target_parts)
    del parent.children[name]
    source.name = target_name
    target_parent.children[target_name] = source
    if source.is_dir and _is_ancestor(source_parts, vfs.cwd):
        vfs.cwd = target_parts + vfs.cwd[len(source_parts):]


def _absolute_destination(vfs, path: str) -> str:
    """Фиксирует путь назначения перед возможным перемещением cwd."""
    result = _absolute(vfs.split_path(path))
    if path.endswith("/") and result != "/":
        result += "/"
    return result


def mv(vfs, args: list[str]) -> str:
    """Переименовывает или перемещает файлы и каталоги в памяти VFS."""
    paths = _operands(args)
    if len(paths) < MIN_MOVE_OPERANDS:
        raise ShellError("missing file or destination operand")
    destination = paths[-1]
    _parent, _name, target, _parts = _locate(vfs, destination)
    if len(paths) > MIN_MOVE_OPERANDS:
        if target is None or not target.is_dir:
            raise ShellError(f"target '{destination}': Not a directory")
    destination = _absolute_destination(vfs, destination)
    for source in paths[:-1]:
        _move_one(vfs, source, destination)
    return ""

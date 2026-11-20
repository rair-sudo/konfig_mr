"""Разбор командной строки с поддержкой кавычек и экранирования."""

import shlex

from src.errors import ShellError


def parse_line(line: str) -> list[str]:
    """Возвращает команду и аргументы либо сообщает об ошибке кавычек."""
    try:
        return shlex.split(line, comments=False, posix=True)
    except ValueError as error:
        raise ShellError(f"синтаксическая ошибка: {error}") from error

"""Параметры командной строки эмулятора."""

import argparse
from dataclasses import dataclass


@dataclass(frozen=True)
class Config:
    """Пути, выбранные пользователем при запуске."""

    vfs: str | None = None
    script: str | None = None


def parse_args(argv: list[str] | None = None) -> Config:
    """Читает пути к CSV виртуальной системы и стартовому сценарию."""
    parser = argparse.ArgumentParser(description="Эмулятор UNIX-оболочки")
    parser.add_argument("--vfs", help="путь к CSV-файлу VFS")
    parser.add_argument("--script", help="путь к стартовому скрипту")
    args = parser.parse_args(argv)
    return Config(vfs=args.vfs, script=args.script)


def describe(config: Config) -> str:
    """Возвращает отладочную информацию обо всех параметрах."""
    vfs = config.vfs if config.vfs is not None else "не задан"
    script = config.script if config.script is not None else "не задан"
    return f"Конфигурация: --vfs={vfs}, --script={script}"

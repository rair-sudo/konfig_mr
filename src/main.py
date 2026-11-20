"""Точка входа CLI-эмулятора."""

from src.config import describe, parse_args
from src.errors import ShellError
from src.script import run_script
from src.shell import Shell
from src.vfs import Vfs, load_vfs


def main(argv: list[str] | None = None) -> int:
    """Показывает конфигурацию, загружает VFS и запускает оболочку."""
    config = parse_args(argv)
    shell = Shell()
    shell.write(describe(config))
    if config.vfs:
        try:
            shell.vfs = load_vfs(config.vfs)
        except ShellError as error:
            shell.write(f"VFS: {error}")
            shell.vfs = Vfs()
    if config.script:
        run_script(shell, config.script)
    if shell.running:
        shell.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

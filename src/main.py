"""Точка входа CLI-эмулятора."""

from src.config import describe, parse_args
from src.script import run_script
from src.shell import Shell


def main(argv: list[str] | None = None) -> int:
    """Показывает конфигурацию, запускает скрипт и интерактивный режим."""
    config = parse_args(argv)
    shell = Shell()
    shell.write(describe(config))
    if config.script:
        run_script(shell, config.script)
    if shell.running:
        shell.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Точка входа CLI-эмулятора."""

from src.shell import Shell


def main() -> int:
    """Запускает интерактивную оболочку."""
    Shell().run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

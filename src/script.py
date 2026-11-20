"""Запуск команд эмулятора из текстового файла."""

from pathlib import Path

from src.shell import Shell


def run_script(shell: Shell, path: str) -> bool:
    """Показывает ввод и вывод; после ошибки продолжает следующую строку."""
    try:
        lines = Path(path).read_text(encoding="utf-8-sig").splitlines()
    except (OSError, UnicodeError) as error:
        shell.write(f"script: {path}: {error}")
        return False
    success = True
    for number, line in enumerate(lines, start=1):
        if not shell.running:
            break
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        shell.write(f"{shell.prompt()}{line}")
        if not shell.execute(line):
            shell.write(f"script: {path}:{number}: ошибка выполнения")
            success = False
    return success

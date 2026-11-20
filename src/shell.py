"""Интерактивный цикл и отправка команд обработчикам."""

import getpass
import socket
import sys
from typing import TextIO

from src.errors import ShellError
from src.parser import parse_line


class Shell:
    """Минимальный прототип оболочки."""

    def __init__(self, output: TextIO | None = None):
        """Создаёт оболочку с выводом в консоль по умолчанию."""
        self.output = output if output is not None else sys.stdout
        self.running = True
        self.user = getpass.getuser()
        self.host = socket.gethostname()

    def prompt(self) -> str:
        """Формирует приглашение из настоящего пользователя и имени узла."""
        return f"{self.user}@{self.host}:~$ "

    def write(self, text: str) -> None:
        """Выводит непустой результат с завершающим переводом строки."""
        if text:
            print(text, file=self.output)

    def execute(self, line: str) -> bool:
        """Выполняет одну строку и возвращает признак успеха."""
        try:
            words = parse_line(line)
            if words:
                self.dispatch(words)
            return True
        except ShellError as error:
            self.write(str(error))
            return False

    def dispatch(self, words: list[str]) -> None:
        """Вызывает заглушку, выход или сообщает о неизвестной команде."""
        command, args = words[0], words[1:]
        if command in ("ls", "cd"):
            self.write(f"{command}: {args}")
        elif command == "exit":
            if args:
                raise ShellError("exit: лишние аргументы")
            self.running = False
        else:
            raise ShellError(f"{command}: command not found")

    def run(self, input_stream: TextIO | None = None) -> None:
        """Читает команды до exit или конца ввода."""
        stream = input_stream if input_stream is not None else sys.stdin
        while self.running:
            self.output.write(self.prompt())
            self.output.flush()
            try:
                line = stream.readline()
            except KeyboardInterrupt:
                self.write("")
                continue
            if not line:
                self.output.write("\n")
                break
            self.execute(line)

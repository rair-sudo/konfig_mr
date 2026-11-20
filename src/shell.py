"""Интерактивный цикл и отправка команд обработчикам."""

import getpass
import socket
import sys
from typing import TextIO

from src.commands import cal, cd, head, ls
from src.errors import ShellError
from src.parser import parse_line
from src.vfs import Vfs


class Shell:
    """Оболочка с виртуальной файловой системой в памяти."""

    def __init__(self, output: TextIO | None = None, vfs: Vfs | None = None):
        """Создаёт оболочку с выводом и файловой системой по умолчанию."""
        self.output = output if output is not None else sys.stdout
        self.vfs = vfs if vfs is not None else Vfs()
        self.running = True
        self.user = getpass.getuser()
        self.host = socket.gethostname()
        self.commands = {"ls": ls, "cd": cd, "head": head, "cal": cal}

    def prompt(self) -> str:
        """Формирует приглашение из данных ОС и текущего каталога VFS."""
        return f"{self.user}@{self.host}:{self.vfs.cwd_path()}$ "

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
        """Вызывает команду или сообщает о неизвестном имени."""
        command, args = words[0], words[1:]
        if command in self.commands:
            try:
                result = self.commands[command](self.vfs, args)
            except ShellError as error:
                raise ShellError(f"{command}: {error}") from error
            self.output.write(result)
        elif command == "vfsinfo":
            if args:
                raise ShellError("vfsinfo: лишние аргументы")
            self.write(self.vfs_info())
        elif command == "exit":
            if args:
                raise ShellError("exit: лишние аргументы")
            self.running = False
        else:
            raise ShellError(f"{command}: command not found")

    def vfs_info(self) -> str:
        """Возвращает имя VFS и число файлов и папок в памяти."""
        folders = files = 0
        stack = [self.vfs.root]
        while stack:
            node = stack.pop()
            for child in node.children.values():
                if child.is_dir:
                    folders += 1
                    stack.append(child)
                else:
                    files += 1
        name = self.vfs.name or "пустая"
        return f"VFS: {name}, папок: {folders}, файлов: {files}"

    def run(self, input_stream: TextIO | None = None) -> None:
        """Читает команды до exit или конца ввода."""
        stream = input_stream if input_stream is not None else sys.stdin
        while self.running:
            self.output.write(self.prompt())
            self.output.flush()
            try:
                line = stream.readline()
            except KeyboardInterrupt:
                self.output.write("\n")
                continue
            if not line:
                self.output.write("\n")
                break
            self.execute(line)

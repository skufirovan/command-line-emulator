import os
import tarfile
import json
import tkinter as tk
from tkinter import scrolledtext
from datetime import datetime
from pathlib import Path
import sys
import threading
import queue
import pytest

class ShellEmulator:
    def __init__(self, computer_name, archive_path, log_path, startup_script):
        self.computer_name = computer_name
        self.archive_path = archive_path
        self.log_path = log_path
        self.startup_script = startup_script
        self.current_dir = "/"
        self.filesystem = {}
        self.load_filesystem()
        self.init_log()

        self.command_queue = queue.Queue()
        self.running = True
        self.command_thread = threading.Thread(target=self.process_commands, daemon=True)
        self.command_thread.start()

    def load_filesystem(self):
        # Распаковываем tar-архив в виртуальную файловую систему
        with tarfile.open(self.archive_path, "r") as archive:
            for member in archive.getmembers():
                self.filesystem[member.name] = member

    def init_log(self):
        # Инициализация лог-файла JSON
        with open(self.log_path, "w") as log_file:
            json.dump({"session": []}, log_file)

    def log_action(self, command, result):
        # Запись команды и результата в лог-файл
        with open(self.log_path, "r+", encoding="utf-8") as log_file:
            log_data = json.load(log_file)
            log_data["session"].append({
                "time": datetime.now().isoformat(),
                "command": command,
                "result": result
            })
            log_file.seek(0)
            json.dump(log_data, log_file, indent=2, ensure_ascii=False)
            log_file.truncate()

    def process_commands(self):
        while self.running:
            try:
                command = self.command_queue.get(timeout=1)
                if command.strip().lower() == "exit":
                    self.running = False
                    result = "Выход из эмулятора"
                    self.log_action(command, result)
                    self.gui.after(0, self.gui.destroy())
                    break
                else:
                    result = self.execute_command(command)
                    self.output_text.insert(tk.END, f"{self.computer_name}@shell:~$ {command}\n{result}\n")
                    self.output_text.see(tk.END) # Autoscroll

            except queue.Empty:
                pass

    def execute_command(self, command):
        # Разбиваем команду на основную часть и аргументы
        parts = command.strip().split(maxsplit=1)
        cmd = parts[0]  # основная команда (например, ls, cd, rev)
        args = parts[1] if len(parts) > 1 else ""  # аргументы команды, если есть

        if cmd == "ls" and len(args) == 0: # Убрал лишнее условие len(args) == 0
            result = self.ls()
        elif cmd == "cd":
            result = self.cd(args)
        elif cmd == "tree" and len(args) == 0:
            result = self.tree()
        elif cmd == "rev":
            result = self.rev(args)
        else:
            result = "Неизвестная команда"
        
        self.log_action(command, result)
        return result

    def ls(self):
        # Команда ls: отображение содержимого текущей директории
        contents = [name for name in self.filesystem if name.startswith(self.current_dir)]
        return "\n".join(contents)

    def cd(self, path):
        # Команда cd: изменение текущей директории
        if path in self.filesystem:
            self.current_dir = path
            return f"Moved to {path}"
        else:
            return f"Directory {path} not found"

    def tree(self, path=None, prefix="", is_last=True):
        """Рекурсивное отображение дерева каталогов."""
        path = path or self.current_dir

        current_prefix = prefix + ("└── " if is_last else "├── ")

        if path == "/":
            result = "/\n"
        elif self.filesystem.get(path) and self.filesystem.get(path).isdir():
            result = f"{current_prefix}{os.path.basename(path)}/\n"
            items = []

            for item in self.filesystem:
                if os.path.dirname(item) == path and item != path:
                    items.append(item)

            items.sort(key=lambda x: not self.filesystem[x].isdir())


            for i, item in enumerate(items):
                is_last_item = (i == len(items) - 1)
                new_prefix = prefix + ("    " if is_last else "│   ")
                result += self.tree(item, new_prefix, is_last_item)
        elif path in self.filesystem: # если файл
            result = f"{current_prefix}{os.path.basename(path)}\n"
        else:
            return f"{current_prefix}No such file or directory: {path}\n" # если  path не найден

        return result

    def rev(self, arg):
        if arg in self.filesystem and self.filesystem[arg].isfile():
            try:
                # Извлекаем содержимое файла из архива
                with tarfile.open(self.archive_path, "r") as archive:
                    member = archive.getmember(arg)
                    f = archive.extractfile(member)
                    content = f.read().decode("utf-8") # Декодируем в строку, если нужно
                reversed_content = content[::-1]
                return reversed_content
            except Exception as e:
                return f"Ошибка при чтении файла: {e}"
        else:  # Если аргумент не файл в виртуальной ФС, переворачиваем его как строку
            return arg[::-1]

    def run_startup_script(self):
        # Выполнение команд из стартового скрипта, если он указан
        if self.startup_script:
            try:
                with open(self.startup_script, "r") as file:
                    commands = file.readlines()
                    for command in commands:
                        print(f"Запуск команды из стартового скрипта: {command.strip()}")
                        self.execute_command(command.strip())
            except FileNotFoundError:
                print("Стартовый скрипт не найден.")
        else:
            print("Стартовый скрипт не указан.")


    def start_gui(self):
        # Запуск GUI с использованием tkinter
        self.gui = tk.Tk()
        self.gui.title("Shell Emulator")
        
        label = tk.Label(self.gui, text=f"{self.computer_name}@shell:~$ ")
        label.pack()

        self.output_text = scrolledtext.ScrolledText(self.gui, wrap=tk.WORD, width=80, height=20)
        self.output_text.pack()
        
        self.command_entry = tk.Entry(self.gui, width=80)
        self.command_entry.bind("<Return>", self.on_enter)
        self.command_entry.pack()
        
        self.run_startup_script()
        self.gui.mainloop()
    
    def on_enter(self, event):
        command = self.command_entry.get()
        self.command_entry.delete(0, tk.END)
        self.command_queue.put(command) # Добавляем команду в очередь

@pytest.fixture
def emulator():
    """Фикстура для создания экземпляра эмулятора с готовым архивом."""
    archive_path = "root.tar"  #  Путь к вашему архиву
    log_path = "log.json" #  Путь к вашему лог-файлу.  Можно использовать tmp_path
    emulator = ShellEmulator("test_computer", archive_path, log_path, None)
    emulator.gui = tk.Tk() #  Инициализируем GUI в фикстуре
    emulator.gui.withdraw() # Скрываем главное окно
    return emulator

def test_ls(emulator, tmp_path):
    emulator.current_dir = "test_root" # Устанавливаем начальную директорию
    result = emulator.execute_command("ls")
    # Проверяем наличие файлов в выводе ls
    assert "test_root\n" in result
    assert "test_root/dir1\n" in result
    assert "test_root/dir1/file1.txt\n" in result
    assert "test_root/dir1/file2.txt\n" in result
    assert "test_root/dir2\n" in result
    assert "test_root/dir2/file3.txt\n" in result
    assert "test_root/file4.txt" in result

def test_cd(emulator):
    assert emulator.execute_command("cd dir1") == "Directory dir1 not found"
    assert emulator.execute_command("cd test_root/dir1") == "Moved to test_root/dir1"
    assert emulator.current_dir == "test_root/dir1"
    assert emulator.execute_command("cd test_root/file4.txt") == "Moved to test_root/file4.txt"
    assert emulator.current_dir == "test_root/file4.txt"


def test_exit(emulator, monkeypatch):
    original_destroy = emulator.gui.destroy  # Сохраняем оригинальный destroy()
    try:
        monkeypatch.setattr(emulator.gui, 'destroy', lambda *args: None)
        emulator.command_queue.put("exit")
        emulator.process_commands() # Выполняем команду в тестовом режиме
        assert emulator.running == False
    finally:
        emulator.gui.destroy = original_destroy


'''def test_exit(emulator, monkeypatch):
    # Создаем экземпляр Tk, если он еще не создан (например, в фикстуре)
    if not hasattr(emulator, "gui") or emulator.gui is None:
        emulator.gui = tk.Tk()
        emulator.gui.withdraw() # Скрываем окно, если оно не нужно

    # "Мокаем" метод destroy() экземпляра emulator.gui
    monkeypatch.setattr(emulator.gui, 'destroy', lambda *args: None)

    # Добавляем команду "exit" в очередь
    emulator.command_queue.put("exit")

    # Выполняем команды из очереди
    emulator.process_commands()

    # Проверяем, что эмулятор остановился
    assert emulator.running is False'''

def test_tree(emulator):
    emulator.current_dir = "test_root"
    result = emulator.execute_command("tree")
    # Проверяем наличие файлов и директорий в выводе tree
    assert "└── test_root/\n" in result
    assert "    ├── dir1/\n" in result
    assert "    │   ├── file1.txt\n" in result
    assert "    │   └── file2.txt\n" in result
    assert "    ├── dir2/\n" in result
    assert "    │   └── file2.txt\n" in result
    assert "    └── file4.txt\n" in result

    emulator.current_dir = "test_root/dir1"
    result = emulator.execute_command("tree")
    # Проверяем наличие файлов и директорий в выводе tree
    assert "└── dir1/\n" in result
    assert "    ├── file1.txt\n" in result
    assert "    └── file2.txt\n" in result


def test_rev(emulator, tmp_path):
    assert emulator.execute_command("rev hello") == "olleh"
    assert emulator.execute_command("rev 12345") == "54321"

    original_content = "Hello from file4"
    assert emulator.execute_command("rev test_root/file4.txt") == original_content[::-1]
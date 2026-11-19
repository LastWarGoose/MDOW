import os
import queue
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path

from app.models.task import AppError


def stop_process(process):
    if os.name == "nt":
        # /T includes the JS runtime or other children, /F makes cancellation bounded.
        try:
            subprocess.run(
                ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NO_WINDOW,
                timeout=10,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            process.kill()
    else:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    if process.poll() is None:
        process.kill()
    process.wait(timeout=10)


def worker_command(name):
    if getattr(sys, "frozen", False):
        return [sys.executable, f"--{name}-worker"]
    executable = Path(sys.executable)
    if executable.name.lower() == "pythonw.exe":
        executable = executable.with_name("python.exe")
    return [str(executable), "-m", f"app.adapters.{name}_worker"]


def run_process(args, cancel, *, timeout=1800, on_line=None, tick=None):
    """Drain bounded stdout while allowing cancellation and killing the process tree."""
    cancel.check()
    options = (
        {"creationflags": subprocess.CREATE_NO_WINDOW}
        if os.name == "nt"
        else {"start_new_session": True}
    )
    messages = queue.Queue(maxsize=512)
    stopped = threading.Event()
    try:
        process = subprocess.Popen(
            [str(v) for v in args],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            **options,
        )
    except OSError as exc:
        raise AppError("Не удалось запустить внешний инструмент. Проверьте установку.") from exc

    def read():
        try:
            while line := process.stdout.readline(1_000_001):
                if len(line) > 1_000_000:
                    break
                while not stopped.is_set():
                    try:
                        messages.put(line.decode("utf-8", errors="replace"), timeout=0.1)
                        break
                    except queue.Full:
                        pass
                if stopped.is_set():
                    break
        finally:
            stopped.set()

    reader = threading.Thread(target=read, daemon=True)
    reader.start()
    start = time.monotonic()
    output = []
    size = 0
    try:
        while process.poll() is None or not messages.empty() or not stopped.is_set():
            cancel.check()
            if time.monotonic() - start > timeout:
                raise AppError("Превышено время ожидания операции.")
            if tick:
                tick()
            try:
                line = messages.get(timeout=0.1)
            except queue.Empty:
                continue
            if on_line:
                on_line(line)
            else:
                size += len(line)
                if size > 4_000_000:
                    raise AppError("Инструмент вернул слишком большой ответ.")
                output.append(line)
        cancel.check()
        if process.wait() != 0:
            raise AppError("Обработка не удалась. Файл повреждён или формат не поддерживается.")
        return "".join(output)
    finally:
        if process.poll() is None:
            stop_process(process)
        stopped.set()
        reader.join(timeout=2)
        process.stdout.close()

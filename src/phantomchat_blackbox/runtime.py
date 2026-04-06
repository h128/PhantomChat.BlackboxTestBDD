from __future__ import annotations

import os
import socket
import subprocess
import threading
import time
from collections import deque

from phantomchat_blackbox.config import TestConfig


class ExternalSystemController:
    def __init__(self, config: TestConfig) -> None:
        self.config = config
        self.process: subprocess.Popen[str] | None = None
        self.output_lines: deque[str] = deque(maxlen=200)
        self._reader_thread: threading.Thread | None = None

    def start(self) -> None:
        if not self.config.server_command:
            return
        if self.process is not None:
            return

        popen_kwargs: dict[str, object] = {
            "cwd": str(self.config.server_workdir) if self.config.server_workdir else None,
            "shell": True,
            "stdout": subprocess.PIPE,
            "stderr": subprocess.STDOUT,
            "text": True,
        }
        if os.name == "nt":
            popen_kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP

        self.process = subprocess.Popen(self.config.server_command, **popen_kwargs)
        self._reader_thread = threading.Thread(target=self._capture_output, daemon=True)
        self._reader_thread.start()

        deadline = time.monotonic() + self.config.startup_timeout_seconds
        while time.monotonic() < deadline:
            if self.process.poll() is not None:
                raise RuntimeError(self._build_failure_message("The PhantomChat process exited before the test suite could connect."))
            if self._port_is_reachable(self.config.socket_host, self.config.socket_port):
                return
            time.sleep(0.25)

        raise RuntimeError(self._build_failure_message("Timed out waiting for the PhantomChat socket port to become reachable."))

    def stop(self) -> None:
        if self.process is None:
            return

        if self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=5)

        self.process = None

    def _capture_output(self) -> None:
        if self.process is None or self.process.stdout is None:
            return
        for line in self.process.stdout:
            self.output_lines.append(line.rstrip())

    def _build_failure_message(self, summary: str) -> str:
        last_lines = "\n".join(self.output_lines)
        if not last_lines:
            return summary
        return f"{summary}\n\nRecent process output:\n{last_lines}"

    @staticmethod
    def _port_is_reachable(host: str, port: int) -> bool:
        try:
            with socket.create_connection((host, port), timeout=1):
                return True
        except OSError:
            return False

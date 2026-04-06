from __future__ import annotations

import json
import ssl
import threading
import time
import uuid
from typing import Any, Callable

import websocket

from phantomchat_blackbox.protocol import SocketCommand


class PhantomSocketClient:
    def __init__(self, name: str, url: str, timeout_seconds: float, verify_tls: bool) -> None:
        self.name = name
        self.url = url
        self.timeout_seconds = timeout_seconds
        self.verify_tls = verify_tls
        self._socket: websocket.WebSocket | None = None
        self._messages: list[dict[str, Any]] = []
        self._condition = threading.Condition()
        self._receiver_thread: threading.Thread | None = None
        self._closing = False
        self._receive_error: Exception | None = None

    def connect(self) -> None:
        if self._socket is not None:
            return

        options: dict[str, Any] = {}
        if self.url.startswith("wss://") and not self.verify_tls:
            options["sslopt"] = {
                "cert_reqs": ssl.CERT_NONE,
                "check_hostname": False,
            }

        self._socket = websocket.create_connection(self.url, timeout=self.timeout_seconds, **options)
        self._socket.settimeout(0.5)
        self._receiver_thread = threading.Thread(target=self._receive_loop, daemon=True)
        self._receiver_thread.start()

    def close(self) -> None:
        self._closing = True
        if self._socket is not None:
            try:
                self._socket.close()
            except Exception:
                pass
            self._socket = None
        if self._receiver_thread is not None:
            self._receiver_thread.join(timeout=1)
            self._receiver_thread = None

    def send_command(self, command: SocketCommand, **payload: Any) -> dict[str, Any]:
        request_uuid = uuid.uuid4().hex
        message = {
            "request_uuid": request_uuid,
            "command": int(command),
            **payload,
        }
        self.send_json(message)
        return self.wait_for(
            predicate=lambda item: item.get("request_uuid") == request_uuid,
            description=f"response to request {request_uuid}",
        )

    def send_json(self, payload: dict[str, Any]) -> None:
        if self._socket is None:
            raise RuntimeError(f"Client '{self.name}' is not connected")
        self._socket.send(json.dumps(payload))

    def wait_for_event(
        self,
        event_name: str,
        predicate: Callable[[dict[str, Any]], bool] | None = None,
        timeout_seconds: float | None = None,
    ) -> dict[str, Any]:
        return self.wait_for(
            predicate=lambda item: item.get("event_name") == event_name and (predicate(item) if predicate else True),
            description=f"event '{event_name}'",
            timeout_seconds=timeout_seconds,
        )

    def wait_for(
        self,
        predicate: Callable[[dict[str, Any]], bool],
        description: str,
        timeout_seconds: float | None = None,
    ) -> dict[str, Any]:
        deadline = time.monotonic() + (timeout_seconds or self.timeout_seconds)
        with self._condition:
            while True:
                for index, message in enumerate(self._messages):
                    if predicate(message):
                        return self._messages.pop(index)

                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                self._condition.wait(timeout=min(remaining, 0.25))

        buffered = json.dumps(self._messages, indent=2, sort_keys=True)
        if self._receive_error is not None:
            raise AssertionError(
                f"Timed out waiting for {description} on client '{self.name}'. Receiver error: {self._receive_error}. Buffered messages: {buffered}"
            )
        raise AssertionError(f"Timed out waiting for {description} on client '{self.name}'. Buffered messages: {buffered}")

    def _receive_loop(self) -> None:
        while not self._closing and self._socket is not None:
            try:
                raw_message = self._socket.recv()
            except websocket.WebSocketTimeoutException:
                continue
            except websocket.WebSocketConnectionClosedException:
                break
            except Exception as exc:
                self._receive_error = exc
                break

            if raw_message is None:
                break
            if not isinstance(raw_message, str):
                continue

            try:
                parsed = json.loads(raw_message)
            except json.JSONDecodeError:
                parsed = {"raw_message": raw_message}

            with self._condition:
                self._messages.append(parsed)
                self._condition.notify_all()

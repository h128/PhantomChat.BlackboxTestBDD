from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse


def _get_env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _get_env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None:
        return default
    return float(raw)


@dataclass(slots=True)
class TestConfig:
    http_base_url: str
    websocket_url: str
    verify_tls: bool
    request_timeout_seconds: float
    event_timeout_seconds: float
    startup_timeout_seconds: float
    server_command: str | None
    server_workdir: Path | None

    @classmethod
    def from_env(cls) -> "TestConfig":
        server_workdir = os.getenv("PHANTOMCHAT_SERVER_WORKDIR")
        return cls(
            http_base_url=os.getenv("PHANTOMCHAT_HTTP_BASE_URL", "http://127.0.0.1:8080").rstrip("/"),
            websocket_url=os.getenv("PHANTOMCHAT_WS_URL", "ws://127.0.0.1:8080/room"),
            verify_tls=_get_env_bool("PHANTOMCHAT_VERIFY_TLS", False),
            request_timeout_seconds=_get_env_float("PHANTOMCHAT_REQUEST_TIMEOUT_SECONDS", 5.0),
            event_timeout_seconds=_get_env_float("PHANTOMCHAT_EVENT_TIMEOUT_SECONDS", 5.0),
            startup_timeout_seconds=_get_env_float("PHANTOMCHAT_STARTUP_TIMEOUT_SECONDS", 30.0),
            server_command=os.getenv("PHANTOMCHAT_SERVER_COMMAND"),
            server_workdir=Path(server_workdir) if server_workdir else None,
        )

    @property
    def socket_host(self) -> str:
        parsed = urlparse(self.websocket_url)
        if not parsed.hostname:
            raise ValueError(f"Invalid WebSocket URL: {self.websocket_url}")
        return parsed.hostname

    @property
    def socket_port(self) -> int:
        parsed = urlparse(self.websocket_url)
        if parsed.port is not None:
            return parsed.port
        if parsed.scheme == "wss":
            return 443
        if parsed.scheme == "ws":
            return 80
        raise ValueError(f"Unable to determine port for WebSocket URL: {self.websocket_url}")

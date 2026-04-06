from __future__ import annotations

import hashlib
import re
import uuid
from dataclasses import dataclass, field
from typing import Any

from phantomchat_blackbox.config import TestConfig
from phantomchat_blackbox.http_client import PhantomHttpClient
from phantomchat_blackbox.socket_client import PhantomSocketClient


def sanitize_identifier(value: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9_-]+", "-", value.strip()).strip("-")
    if not normalized:
        normalized = "user"
    return normalized[:64]


@dataclass(slots=True)
class TestWorld:
    config: TestConfig
    http: PhantomHttpClient = field(init=False)
    clients: dict[str, PhantomSocketClient] = field(default_factory=dict)
    room_aliases: dict[str, str] = field(default_factory=dict)
    last_socket_response: dict[str, dict[str, Any]] = field(default_factory=dict)
    last_socket_event: dict[str, dict[str, Any]] = field(default_factory=dict)
    last_http_response: Any | None = None
    last_downloaded_content: bytes | None = None

    def __post_init__(self) -> None:
        self.http = PhantomHttpClient(
            base_url=self.config.http_base_url,
            timeout_seconds=self.config.request_timeout_seconds,
            verify_tls=self.config.verify_tls,
        )

    def reset_for_scenario(self) -> None:
        self.room_aliases.clear()
        self.last_socket_response.clear()
        self.last_socket_event.clear()
        self.last_http_response = None
        self.last_downloaded_content = None

    def cleanup_scenario(self) -> None:
        for client in self.clients.values():
            client.close()
        self.clients.clear()
        self.reset_for_scenario()

    def close(self) -> None:
        self.cleanup_scenario()
        self.http.close()

    def create_client(self, name: str) -> PhantomSocketClient:
        client = self.clients.get(name)
        if client is None:
            client = PhantomSocketClient(
                name=name,
                url=self.config.websocket_url,
                timeout_seconds=self.config.event_timeout_seconds,
                verify_tls=self.config.verify_tls,
            )
            self.clients[name] = client
        return client

    def client_user_uuid(self, name: str) -> str:
        return sanitize_identifier(name)

    def client_public_key(self, name: str) -> str:
        # Use deterministic 32-byte hex key material so scenarios exercise a realistic
        # public-key shaped contract without coupling to a specific client implementation.
        return hashlib.sha256(name.encode("utf-8")).hexdigest()

    def create_unique_room(self, alias: str) -> str:
        room_name = f"bdd-{sanitize_identifier(alias).lower()}-{uuid.uuid4().hex[:8]}"
        if len(room_name) < 5:
            room_name = f"room-{uuid.uuid4().hex[:8]}"
        self.room_aliases[alias] = room_name
        return room_name

    def resolve_room(self, alias_or_name: str) -> str:
        return self.room_aliases.get(alias_or_name, alias_or_name)

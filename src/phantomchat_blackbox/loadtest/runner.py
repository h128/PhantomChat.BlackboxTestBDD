from __future__ import annotations

import asyncio
import json
import ssl
import time
import uuid
from collections import Counter
from dataclasses import asdict, dataclass, field
from statistics import mean
from typing import Any

import websockets
from websockets.exceptions import ConnectionClosed

from phantomchat_blackbox.crypto import ClientKeyMaterial
from phantomchat_blackbox.protocol import SocketCommand
from phantomchat_blackbox.world import sanitize_identifier

from phantomchat_blackbox.loadtest.config import LoadTestConfig


def _utc_timestamp() -> str:
    return time.strftime("%Y%m%d-%H%M%S", time.gmtime())


def _compact_exception(exc: BaseException) -> str:
    return f"{exc.__class__.__name__}: {exc}"


@dataclass(slots=True)
class ParticipantSpec:
    index: int
    room_index: int
    room_name: str
    user_name: str
    user_uuid: str
    display_name: str
    avatar_id: int
    public_key: str


@dataclass(slots=True)
class ParticipantState:
    spec: ParticipantSpec
    client: "AsyncPhantomLoadClient"
    connected: bool = False
    joined: bool = False
    join_response: dict[str, Any] | None = None
    connect_error: str | None = None
    join_error: str | None = None


@dataclass(slots=True)
class LoadTestMetrics:
    started_at: float = 0.0
    finished_at: float = 0.0
    connection_attempts: int = 0
    successful_connections: int = 0
    failed_connections: int = 0
    join_attempts: int = 0
    join_successes: int = 0
    join_failures: int = 0
    send_attempts: int = 0
    send_successes: int = 0
    send_failures: int = 0
    expected_receive_events: int = 0
    messages_received: int = 0
    disconnects: int = 0
    receiver_errors: int = 0
    rooms_with_traffic: int = 0
    joined_per_room: dict[str, int] = field(default_factory=dict)
    failure_reasons: Counter[str] = field(default_factory=Counter)
    send_ack_latency_ms: list[float] = field(default_factory=list)
    delivery_latency_ms: list[float] = field(default_factory=list)

    @property
    def elapsed_seconds(self) -> float:
        if self.finished_at <= self.started_at:
            return 0.0
        return self.finished_at - self.started_at

    @property
    def join_success_rate(self) -> float:
        if self.join_attempts == 0:
            return 0.0
        return self.join_successes / self.join_attempts

    @property
    def receive_delivery_ratio(self) -> float:
        if self.expected_receive_events == 0:
            return 0.0
        return self.messages_received / self.expected_receive_events

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["failure_reasons"] = dict(self.failure_reasons)
        payload["elapsed_seconds"] = self.elapsed_seconds
        payload["join_success_rate"] = self.join_success_rate
        payload["receive_delivery_ratio"] = self.receive_delivery_ratio
        return payload


@dataclass(slots=True)
class LoadTestResult:
    run_id: str
    target_url: str
    config: LoadTestConfig
    metrics: LoadTestMetrics
    room_names: list[str]
    joined_users: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "target_url": self.target_url,
            "config": self.config.to_dict(),
            "metrics": self.metrics.to_dict(),
            "room_names": self.room_names,
            "joined_users": self.joined_users,
        }


class AsyncPhantomLoadClient:
    def __init__(
        self,
        spec: ParticipantSpec,
        *,
        websocket_url: str,
        verify_tls: bool,
        connect_timeout_seconds: float,
        event_handler,
        disconnect_handler,
        receiver_error_handler,
    ) -> None:
        self.spec = spec
        self.websocket_url = websocket_url
        self.verify_tls = verify_tls
        self.connect_timeout_seconds = connect_timeout_seconds
        self._event_handler = event_handler
        self._disconnect_handler = disconnect_handler
        self._receiver_error_handler = receiver_error_handler
        self._connection: websockets.ClientConnection | None = None
        self._receiver_task: asyncio.Task[None] | None = None
        self._pending: dict[str, asyncio.Future[dict[str, Any]]] = {}
        self._send_lock = asyncio.Lock()
        self._closing = False

    async def connect(self) -> None:
        if self._connection is not None:
            return

        ssl_context: ssl.SSLContext | bool | None = None
        if self.websocket_url.startswith("wss://"):
            if self.verify_tls:
                ssl_context = ssl.create_default_context()
            else:
                ssl_context = ssl.create_default_context()
                ssl_context.check_hostname = False
                ssl_context.verify_mode = ssl.CERT_NONE

        self._connection = await websockets.connect(
            self.websocket_url,
            open_timeout=self.connect_timeout_seconds,
            ssl=ssl_context,
            max_queue=None,
        )
        self._receiver_task = asyncio.create_task(self._receive_loop())

    async def close(self) -> None:
        self._closing = True
        if self._connection is not None:
            await self._connection.close()
            self._connection = None
        if self._receiver_task is not None:
            await asyncio.gather(self._receiver_task, return_exceptions=True)
            self._receiver_task = None

    async def send_command(self, command: SocketCommand, timeout_seconds: float, **payload: Any) -> tuple[dict[str, Any], float, str]:
        if self._connection is None:
            raise RuntimeError(f"Client {self.spec.user_name} is not connected")

        request_uuid = uuid.uuid4().hex
        response_future: asyncio.Future[dict[str, Any]] = asyncio.get_running_loop().create_future()
        self._pending[request_uuid] = response_future
        message = {
            "request_uuid": request_uuid,
            "command": int(command),
            **payload,
        }

        started_at = time.perf_counter()
        try:
            async with self._send_lock:
                await self._connection.send(json.dumps(message, separators=(",", ":")))
            response = await asyncio.wait_for(response_future, timeout=timeout_seconds)
        finally:
            self._pending.pop(request_uuid, None)

        latency_ms = (time.perf_counter() - started_at) * 1000.0
        return response, latency_ms, request_uuid

    async def _receive_loop(self) -> None:
        try:
            assert self._connection is not None
            async for raw_message in self._connection:
                received_at = time.perf_counter()
                if not isinstance(raw_message, str):
                    continue
                try:
                    parsed = json.loads(raw_message)
                except json.JSONDecodeError:
                    parsed = {"raw_message": raw_message}

                request_uuid = parsed.get("request_uuid")
                future = self._pending.get(request_uuid) if isinstance(request_uuid, str) else None
                if future is not None and not future.done():
                    future.set_result(parsed)
                    continue

                self._event_handler(self.spec, parsed, received_at)
        except ConnectionClosed:
            pass
        except Exception as exc:
            if not self._closing:
                self._receiver_error_handler(self.spec, exc)
                for future in self._pending.values():
                    if not future.done():
                        future.set_exception(exc)
        finally:
            if not self._closing:
                self._disconnect_handler(self.spec)


class LoadTestRunner:
    def __init__(self, config: LoadTestConfig) -> None:
        self.config = config
        self.config.validate()
        self.run_id = f"load-{_utc_timestamp()}-{uuid.uuid4().hex[:6]}"
        self.metrics = LoadTestMetrics()
        self._participants: list[ParticipantState] = []
        self._room_names = [f"{sanitize_identifier(self.config.room_prefix).lower()}-{self.run_id}-{index + 1:02d}" for index in range(self.config.rooms)]
        self._sent_at: dict[str, float] = {}
        self._expected_fanout: dict[str, int] = {}

    async def run(self) -> LoadTestResult:
        self.metrics.started_at = time.perf_counter()
        self._participants = self._build_participants()
        try:
            await asyncio.gather(*(self._connect_and_join(participant) for participant in self._participants))

            joined = [participant for participant in self._participants if participant.joined]
            joined_per_room = Counter(participant.spec.room_name for participant in joined)
            self.metrics.joined_per_room = dict(sorted(joined_per_room.items()))
            self.metrics.rooms_with_traffic = sum(1 for count in joined_per_room.values() if count > 1)

            if joined:
                await asyncio.gather(*(self._send_messages(participant, joined_per_room[participant.spec.room_name]) for participant in joined))
                if self.config.receive_settle_seconds > 0:
                    await asyncio.sleep(self.config.receive_settle_seconds)

            return LoadTestResult(
                run_id=self.run_id,
                target_url=self.config.websocket_url,
                config=self.config,
                metrics=self.metrics,
                room_names=self._room_names,
                joined_users=[participant.spec.user_name for participant in joined],
            )
        finally:
            await asyncio.gather(*(participant.client.close() for participant in self._participants), return_exceptions=True)
            self.metrics.finished_at = time.perf_counter()

    def _build_participants(self) -> list[ParticipantState]:
        participants: list[ParticipantState] = []
        for index in range(self.config.users):
            room_index = index % self.config.rooms
            room_name = self._room_names[room_index]
            user_name = f"user-{index + 1:04d}"
            unique_name = f"{self.run_id}-{user_name}"
            key_material = ClientKeyMaterial.from_seed_text(unique_name)
            spec = ParticipantSpec(
                index=index,
                room_index=room_index,
                room_name=room_name,
                user_name=user_name,
                user_uuid=sanitize_identifier(unique_name),
                display_name=f"{self.config.display_name_prefix}-{index + 1:04d}",
                avatar_id=self.config.avatar_id_base + index,
                public_key=key_material.public_key_hex,
            )
            participants.append(
                ParticipantState(
                    spec=spec,
                    client=AsyncPhantomLoadClient(
                        spec,
                        websocket_url=self.config.websocket_url,
                        verify_tls=self.config.verify_tls,
                        connect_timeout_seconds=self.config.connect_timeout_seconds,
                        event_handler=self._handle_event,
                        disconnect_handler=self._handle_disconnect,
                        receiver_error_handler=self._handle_receiver_error,
                    ),
                )
            )
        return participants

    async def _connect_and_join(self, participant: ParticipantState) -> None:
        delay_seconds = self._ramp_delay_seconds(participant.spec.index)
        if delay_seconds > 0:
            await asyncio.sleep(delay_seconds)

        self.metrics.connection_attempts += 1
        try:
            await participant.client.connect()
        except Exception as exc:
            participant.connect_error = _compact_exception(exc)
            self.metrics.failed_connections += 1
            self.metrics.failure_reasons[f"connect:{exc.__class__.__name__}"] += 1
            return

        participant.connected = True
        self.metrics.successful_connections += 1
        self.metrics.join_attempts += 1

        try:
            response, _latency_ms, _request_uuid = await participant.client.send_command(
                SocketCommand.JOIN_OR_CREATE_ROOM,
                timeout_seconds=self.config.join_timeout_seconds,
                user_uuid=participant.spec.user_uuid,
                room_name=participant.spec.room_name,
                public_key=participant.spec.public_key,
                avatar_id=participant.spec.avatar_id,
                display_name=participant.spec.display_name,
            )
        except Exception as exc:
            participant.join_error = _compact_exception(exc)
            self.metrics.join_failures += 1
            self.metrics.failure_reasons[f"join:{exc.__class__.__name__}"] += 1
            return

        participant.join_response = response
        if response.get("status") == 0:
            participant.joined = True
            self.metrics.join_successes += 1
            return

        participant.join_error = str(response.get("message") or "unknown join failure")
        self.metrics.join_failures += 1
        failure_key = f"join-status:{response.get('status')}"
        self.metrics.failure_reasons[failure_key] += 1

    async def _send_messages(self, participant: ParticipantState, room_population: int) -> None:
        if room_population <= 0:
            return

        sends_completed = 0
        started_at = time.perf_counter()
        deadline = started_at + self.config.duration_seconds if self.config.duration_seconds is not None else None
        interval_seconds = 0.0 if self.config.message_rate == 0 else 1.0 / self.config.message_rate
        next_send_at = started_at

        while True:
            now = time.perf_counter()
            if deadline is not None and now >= deadline:
                break
            if self.config.messages_per_user is not None and sends_completed >= self.config.messages_per_user:
                break
            if interval_seconds > 0 and now < next_send_at:
                await asyncio.sleep(next_send_at - now)

            sends_completed += 1
            message = f"loadtest|{self.run_id}|u{participant.spec.index + 1:04d}|m{sends_completed:04d}|{uuid.uuid4().hex[:8]}"
            self.metrics.send_attempts += 1
            self._sent_at[message] = time.perf_counter()

            try:
                response, latency_ms, _request_uuid = await participant.client.send_command(
                    SocketCommand.SEND_MESSAGE,
                    timeout_seconds=self.config.send_timeout_seconds,
                    message=message,
                )
            except Exception as exc:
                self._sent_at.pop(message, None)
                self.metrics.send_failures += 1
                self.metrics.failure_reasons[f"send:{exc.__class__.__name__}"] += 1
            else:
                if response.get("status") == 0:
                    self.metrics.send_successes += 1
                    self.metrics.send_ack_latency_ms.append(latency_ms)
                    expected_recipients = max(room_population - 1, 0)
                    self._expected_fanout[message] = expected_recipients
                    self.metrics.expected_receive_events += expected_recipients
                else:
                    self._sent_at.pop(message, None)
                    self.metrics.send_failures += 1
                    failure_key = f"send-status:{response.get('status')}"
                    self.metrics.failure_reasons[failure_key] += 1

            if interval_seconds > 0:
                next_send_at = max(next_send_at + interval_seconds, time.perf_counter())

    def _handle_event(self, participant: ParticipantSpec, message: dict[str, Any], received_at: float) -> None:
        if message.get("event_name") != "NewMessageReceived":
            return

        payload = message.get("message")
        if not isinstance(payload, str):
            return
        if not payload.startswith(f"loadtest|{self.run_id}|"):
            return

        self.metrics.messages_received += 1
        sent_at = self._sent_at.get(payload)
        if sent_at is not None:
            self.metrics.delivery_latency_ms.append((received_at - sent_at) * 1000.0)

    def _handle_disconnect(self, participant: ParticipantSpec) -> None:
        self.metrics.disconnects += 1
        self.metrics.failure_reasons[f"disconnect:{participant.user_name}"] += 1

    def _handle_receiver_error(self, participant: ParticipantSpec, exc: BaseException) -> None:
        self.metrics.receiver_errors += 1
        self.metrics.failure_reasons[f"receiver:{exc.__class__.__name__}"] += 1

    def _ramp_delay_seconds(self, index: int) -> float:
        if self.config.ramp_up_seconds <= 0 or self.config.users <= 1:
            return 0.0
        return self.config.ramp_up_seconds * (index / (self.config.users - 1))


def latency_summary(values: list[float]) -> dict[str, float | int | None]:
    if not values:
        return {
            "count": 0,
            "min_ms": None,
            "avg_ms": None,
            "p50_ms": None,
            "p95_ms": None,
            "max_ms": None,
        }

    sorted_values = sorted(values)

    def percentile(rank: float) -> float:
        if len(sorted_values) == 1:
            return sorted_values[0]
        position = rank * (len(sorted_values) - 1)
        lower_index = int(position)
        upper_index = min(lower_index + 1, len(sorted_values) - 1)
        fraction = position - lower_index
        lower_value = sorted_values[lower_index]
        upper_value = sorted_values[upper_index]
        return lower_value + (upper_value - lower_value) * fraction

    return {
        "count": len(sorted_values),
        "min_ms": sorted_values[0],
        "avg_ms": mean(sorted_values),
        "p50_ms": percentile(0.50),
        "p95_ms": percentile(0.95),
        "max_ms": sorted_values[-1],
    }
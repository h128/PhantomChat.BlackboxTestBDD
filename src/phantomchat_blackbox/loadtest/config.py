from __future__ import annotations

from dataclasses import asdict, dataclass

from phantomchat_blackbox.config import TestConfig


@dataclass(slots=True)
class LoadTestConfig:
    websocket_url: str
    verify_tls: bool
    users: int
    rooms: int
    messages_per_user: int | None
    message_rate: float
    duration_seconds: float | None
    ramp_up_seconds: float
    connect_timeout_seconds: float
    join_timeout_seconds: float
    send_timeout_seconds: float
    receive_settle_seconds: float
    room_prefix: str
    display_name_prefix: str
    avatar_id_base: int

    @classmethod
    def from_test_config(
        cls,
        test_config: TestConfig,
        *,
        users: int,
        rooms: int,
        messages_per_user: int | None,
        message_rate: float,
        duration_seconds: float | None,
        ramp_up_seconds: float,
        connect_timeout_seconds: float | None,
        join_timeout_seconds: float | None,
        send_timeout_seconds: float | None,
        receive_settle_seconds: float,
        room_prefix: str,
        display_name_prefix: str,
        avatar_id_base: int,
    ) -> "LoadTestConfig":
        effective_messages_per_user = None if messages_per_user is not None and messages_per_user <= 0 else messages_per_user
        effective_duration_seconds = None if duration_seconds is not None and duration_seconds <= 0 else duration_seconds
        return cls(
            websocket_url=test_config.websocket_url,
            verify_tls=test_config.verify_tls,
            users=users,
            rooms=rooms,
            messages_per_user=effective_messages_per_user,
            message_rate=message_rate,
            duration_seconds=effective_duration_seconds,
            ramp_up_seconds=ramp_up_seconds,
            connect_timeout_seconds=connect_timeout_seconds or test_config.event_timeout_seconds,
            join_timeout_seconds=join_timeout_seconds or test_config.event_timeout_seconds,
            send_timeout_seconds=send_timeout_seconds or test_config.event_timeout_seconds,
            receive_settle_seconds=receive_settle_seconds,
            room_prefix=room_prefix,
            display_name_prefix=display_name_prefix,
            avatar_id_base=avatar_id_base,
        )

    def validate(self) -> None:
        if self.users <= 0:
            raise ValueError("users must be greater than zero")
        if self.rooms <= 0:
            raise ValueError("rooms must be greater than zero")
        if self.message_rate < 0:
            raise ValueError("message_rate cannot be negative")
        if self.messages_per_user is None and self.duration_seconds is None:
            raise ValueError("set messages_per_user, duration_seconds, or both")
        if self.messages_per_user is None and self.message_rate == 0:
            raise ValueError("message_rate must be greater than zero for duration-only runs")
        if self.connect_timeout_seconds <= 0:
            raise ValueError("connect_timeout_seconds must be greater than zero")
        if self.join_timeout_seconds <= 0:
            raise ValueError("join_timeout_seconds must be greater than zero")
        if self.send_timeout_seconds <= 0:
            raise ValueError("send_timeout_seconds must be greater than zero")
        if self.receive_settle_seconds < 0:
            raise ValueError("receive_settle_seconds cannot be negative")
        if self.ramp_up_seconds < 0:
            raise ValueError("ramp_up_seconds cannot be negative")

    def to_dict(self) -> dict[str, object]:
        return asdict(self)
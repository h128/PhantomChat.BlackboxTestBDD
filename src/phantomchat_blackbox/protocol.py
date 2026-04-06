from __future__ import annotations

from enum import IntEnum


class SocketCommand(IntEnum):
    JOIN_OR_CREATE_ROOM = 1
    SEND_MESSAGE = 2
    LEAVE_ROOM = 3
    SIGNAL_CALL = 4


class SignalCallAction(IntEnum):
    OFFER = 1
    ANSWER = 2
    REJECT = 3
    CANDIDATE = 4
    HANGUP = 5


def command_from_name(name: str) -> SocketCommand:
    normalized = name.strip().upper()
    return SocketCommand[normalized]


def signal_action_from_name(name: str) -> SignalCallAction:
    normalized = name.strip().upper()
    return SignalCallAction[normalized]

from __future__ import annotations

import json
import re
import uuid
from typing import Any

from behave import given, then, when

from phantomchat_blackbox.crypto import CryptoProtocolError
from phantomchat_blackbox.protocol import SignalCallAction, SocketCommand, signal_action_from_name


def _resolve_path(payload: dict[str, Any], path: str) -> Any:
    current: Any = payload
    for segment in path.split("."):
        if not isinstance(current, dict) or segment not in current:
            raise AssertionError(f"Expected path '{path}' to exist in payload: {payload}")
        current = current[segment]
    return current


def _convert_expected_value(world, field_name: str, raw_value: str) -> Any:
    text = raw_value.strip()

    if field_name == "action":
        try:
            return int(signal_action_from_name(text))
        except KeyError:
            pass

    if text in world.room_aliases:
        return world.resolve_room(text)

    if text in world.clients:
        return world.client_user_uuid(text)

    lowered = text.lower()
    if lowered == "true":
        return True
    if lowered == "false":
        return False
    if lowered.isdigit():
        return int(lowered)
    return text


def _assert_payload_contains(world, payload: dict[str, Any], rows) -> None:
    for row in rows:
        field_name = row["field"]
        expected_value = _convert_expected_value(world, field_name, row["value"])
        actual_value = _resolve_path(payload, field_name)

        if isinstance(actual_value, (list, set, tuple)):
            expected_items = {
                _convert_expected_value(world, field_name, item)
                for item in row["value"].split(",")
                if item.strip()
            }
            actual_items = set(actual_value)
            assert actual_items == expected_items, (
                f"Field '{field_name}' mismatch. Expected items {expected_items}, got {actual_items}."
            )
            continue

        assert actual_value == expected_value, (
            f"Field '{field_name}' mismatch. Expected {expected_value!r}, got {actual_value!r}."
        )


@given('a unique room alias "{alias}"')
@given('a fresh room called "{alias}"')
@given('another fresh room called "{alias}"')
def step_unique_room(context, alias: str) -> None:
    context.world.create_unique_room(alias)


@given('WebSocket client "{name}" is connected')
@given('"{name}" is connected')
def step_connect_client(context, name: str) -> None:
    client = context.world.create_client(name)
    client.connect()


@given('client "{name}" joins room "{room_alias}" with public key "{public_key}"')
@when('client "{name}" joins room "{room_alias}" with public key "{public_key}"')
@given('"{name}" joins room "{room_alias}" with key "{public_key}"')
@when('"{name}" joins room "{room_alias}" with key "{public_key}"')
def step_join_room(context, name: str, room_alias: str, public_key: str) -> None:
    client = context.world.create_client(name)
    response = client.send_command(
        SocketCommand.JOIN_OR_CREATE_ROOM,
        user_uuid=context.world.client_user_uuid(name),
        room_name=context.world.resolve_room(room_alias),
        public_key=public_key,
    )
    context.world.last_socket_response[name] = response


@given('client "{name}" joins room "{room_alias}" with a generated libsodium-style public key')
@when('client "{name}" joins room "{room_alias}" with a generated libsodium-style public key')
@given('"{name}" joins room "{room_alias}" with a valid key')
@when('"{name}" joins room "{room_alias}" with a valid key')
@given('"{name}" joins room "{room_alias}" with a generated key pair')
@when('"{name}" joins room "{room_alias}" with a generated key pair')
def step_join_room_with_generated_public_key(context, name: str, room_alias: str) -> None:
    step_join_room(context, name, room_alias, context.world.client_public_key(name))


@when('client "{name}" sends chat message "{message}"')
@when('"{name}" sends the message "{message}"')
def step_send_chat_message(context, name: str, message: str) -> None:
    client = context.world.create_client(name)
    response = client.send_command(SocketCommand.SEND_MESSAGE, message=message)
    context.world.last_socket_response[name] = response


@when('client "{name}" leaves the current room')
@when('"{name}" leaves the room')
def step_leave_room(context, name: str) -> None:
    client = context.world.create_client(name)
    request_uuid = uuid.uuid4().hex
    client.send_json(
        {
            "request_uuid": request_uuid,
            "command": int(SocketCommand.LEAVE_ROOM),
        }
    )
    response = client.wait_for(
        predicate=lambda item: item.get("status") is not None
        and item.get("event_name") is None
        and item.get("request_uuid") in {request_uuid, "", None},
        description=f"leave-room response for client '{name}'",
    )
    context.world.last_socket_response[name] = response


@when('client "{name}" sends signaling action "{action_name}" with JSON payload')
@when('"{name}" shares the call step "{action_name}" with details')
def step_send_signal(context, name: str, action_name: str) -> None:
    payload = json.loads(context.text or "{}")
    client = context.world.create_client(name)
    response = client.send_command(
        SocketCommand.SIGNAL_CALL,
        action=int(signal_action_from_name(action_name)),
        data=payload,
    )
    context.world.last_socket_response[name] = response


@then('the response for client "{name}" should contain')
@then('the reply for "{name}" should include')
def step_assert_response(context, name: str) -> None:
    payload = context.world.last_socket_response.get(name)
    if payload is None:
        raise AssertionError(f"No stored response found for client '{name}'")
    _assert_payload_contains(context.world, payload, context.table)


@then('client "{name}" should receive a "{event_name}" event containing')
def step_assert_event(context, name: str, event_name: str) -> None:
    client = context.world.create_client(name)
    event = client.wait_for_event(event_name, timeout_seconds=context.world.config.event_timeout_seconds)
    context.world.last_socket_event[name] = event
    _assert_payload_contains(context.world, event, context.table)


@then('"{name}" should be told that "{other_name}" joined room "{room_alias}"')
def step_assert_user_joined(context, name: str, other_name: str, room_alias: str) -> None:
    client = context.world.create_client(name)
    event = client.wait_for_event("UserEnteredRoom", timeout_seconds=context.world.config.event_timeout_seconds)
    context.world.last_socket_event[name] = event
    expected_room_name = context.world.resolve_room(room_alias)
    expected_user_uuid = context.world.client_user_uuid(other_name)
    assert event.get("room_name") == expected_room_name, (
        f"Expected join event room_name {expected_room_name!r}, got {event.get('room_name')!r}."
    )
    assert event.get("user_uuid") == expected_user_uuid, (
        f"Expected join event user_uuid {expected_user_uuid!r}, got {event.get('user_uuid')!r}."
    )


@then('"{name}" should receive the message "{message}" from "{sender_name}"')
def step_assert_message_received(context, name: str, message: str, sender_name: str) -> None:
    client = context.world.create_client(name)
    event = client.wait_for_event("NewMessageReceived", timeout_seconds=context.world.config.event_timeout_seconds)
    context.world.last_socket_event[name] = event
    expected_sender = context.world.client_user_uuid(sender_name)
    assert event.get("sender_uuid") == expected_sender, (
        f"Expected sender_uuid {expected_sender!r}, got {event.get('sender_uuid')!r}."
    )
    assert event.get("message") == message, (
        f"Expected message {message!r}, got {event.get('message')!r}."
    )


@then('"{name}" should be told that "{other_name}" left the room')
def step_assert_user_left(context, name: str, other_name: str) -> None:
    client = context.world.create_client(name)
    event = client.wait_for_event("LeaveRoom", timeout_seconds=context.world.config.event_timeout_seconds)
    context.world.last_socket_event[name] = event
    expected_user_uuid = context.world.client_user_uuid(other_name)
    assert event.get("user_uuid") == expected_user_uuid, (
        f"Expected leave event user_uuid {expected_user_uuid!r}, got {event.get('user_uuid')!r}."
    )


@then('"{name}" should receive the call details from "{sender_name}"')
def step_assert_call_details(context, name: str, sender_name: str) -> None:
    client = context.world.create_client(name)
    event = client.wait_for_event("SignalCallRelay", timeout_seconds=context.world.config.event_timeout_seconds)
    context.world.last_socket_event[name] = event
    expected_sender = context.world.client_user_uuid(sender_name)
    assert event.get("sender_uuid") == expected_sender, (
        f"Expected sender_uuid {expected_sender!r}, got {event.get('sender_uuid')!r}."
    )
    if context.table:
        _assert_payload_contains(context.world, event, context.table)


@then('the response field "{field_name}" for client "{name}" should match regex "{pattern}"')
@then('the reply field "{field_name}" for "{name}" should match regex "{pattern}"')
def step_assert_response_field_matches_regex(context, field_name: str, name: str, pattern: str) -> None:
    payload = context.world.last_socket_response.get(name)
    if payload is None:
        raise AssertionError(f"No stored response found for client '{name}'")
    actual_value = _resolve_path(payload, field_name)
    if not isinstance(actual_value, str):
        raise AssertionError(f"Field '{field_name}' is not a string and cannot be matched by regex: {actual_value!r}")
    if re.fullmatch(pattern, actual_value) is None:
        raise AssertionError(
            f"Field '{field_name}' value {actual_value!r} did not match regex {pattern!r}."
        )


@then('the response field "{field_name}" for client "{name}" should contain "{expected_text}"')
@then('the reply field "{field_name}" for "{name}" should mention "{expected_text}"')
def step_assert_response_field_contains_text(context, field_name: str, name: str, expected_text: str) -> None:
    payload = context.world.last_socket_response.get(name)
    if payload is None:
        raise AssertionError(f"No stored response found for client '{name}'")
    actual_value = _resolve_path(payload, field_name)
    if not isinstance(actual_value, str):
        raise AssertionError(f"Field '{field_name}' is not a string: {actual_value!r}")
    if expected_text not in actual_value:
        raise AssertionError(
            f"Field '{field_name}' value {actual_value!r} did not contain expected text {expected_text!r}."
        )


@then('the reply field "{field_name}" for "{name}" should be longer than {minimum_length:d} characters')
def step_assert_response_field_length(context, field_name: str, name: str, minimum_length: int) -> None:
    payload = context.world.last_socket_response.get(name)
    if payload is None:
        raise AssertionError(f"No stored response found for client '{name}'")
    actual_value = _resolve_path(payload, field_name)
    if not isinstance(actual_value, str):
        raise AssertionError(f"Field '{field_name}' is not a string: {actual_value!r}")
    if len(actual_value) <= minimum_length:
        raise AssertionError(
            f"Field '{field_name}' length {len(actual_value)} was not greater than {minimum_length}."
        )


@then('the response field "{field_name}" for clients "{left_name}" and "{right_name}" should be equal')
@then('the reply field "{field_name}" for "{left_name}" and "{right_name}" should be the same')
def step_assert_response_fields_equal(context, field_name: str, left_name: str, right_name: str) -> None:
    left_payload = context.world.last_socket_response.get(left_name)
    right_payload = context.world.last_socket_response.get(right_name)
    if left_payload is None or right_payload is None:
        raise AssertionError("Both clients must have stored responses before comparing response fields")
    left_value = _resolve_path(left_payload, field_name)
    right_value = _resolve_path(right_payload, field_name)
    assert left_value == right_value, (
        f"Field '{field_name}' mismatch. Expected equal values, got {left_value!r} and {right_value!r}."
    )


@then('the response field "{field_name}" for clients "{left_name}" and "{right_name}" should not be equal')
@then('the reply field "{field_name}" for "{left_name}" and "{right_name}" should be different')
def step_assert_response_fields_not_equal(context, field_name: str, left_name: str, right_name: str) -> None:
    left_payload = context.world.last_socket_response.get(left_name)
    right_payload = context.world.last_socket_response.get(right_name)
    if left_payload is None or right_payload is None:
        raise AssertionError("Both clients must have stored responses before comparing response fields")
    left_value = _resolve_path(left_payload, field_name)
    right_value = _resolve_path(right_payload, field_name)
    assert left_value != right_value, (
        f"Field '{field_name}' unexpectedly matched for both clients: {left_value!r}."
    )


@then('the response field "{field_name}" for client "{name}" should not be empty')
@then('the reply field "{field_name}" for "{name}" should not be empty')
def step_assert_response_field_not_empty(context, field_name: str, name: str) -> None:
    payload = context.world.last_socket_response.get(name)
    if payload is None:
        raise AssertionError(f"No stored response found for client '{name}'")
    actual_value = _resolve_path(payload, field_name)
    if actual_value in (None, "", [], {}):
        raise AssertionError(f"Field '{field_name}' was unexpectedly empty: {actual_value!r}")


@given('"{name}" should be able to open the room key from the reply')
@then('"{name}" should be able to open the room key from the reply')
def step_decrypt_room_key(context, name: str) -> None:
    try:
        context.world.decrypt_room_key_for_client(name)
    except CryptoProtocolError as exc:
        raise AssertionError(str(exc)) from exc


@then('the opened room key for "{name}" should match regex "{pattern}"')
def step_assert_decrypted_room_key_matches_regex(context, name: str, pattern: str) -> None:
    decrypted_room_key = context.world.last_decrypted_room_key.get(name)
    if decrypted_room_key is None:
        raise AssertionError(f"No decrypted room key has been stored for client '{name}'")
    if re.fullmatch(pattern, decrypted_room_key) is None:
        raise AssertionError(
            f"Opened room key value {decrypted_room_key!r} did not match regex {pattern!r}."
        )


@then('the opened room key for "{left_name}" and "{right_name}" should be the same')
def step_assert_decrypted_room_keys_equal(context, left_name: str, right_name: str) -> None:
    left_value = context.world.last_decrypted_room_key.get(left_name)
    right_value = context.world.last_decrypted_room_key.get(right_name)
    if left_value is None or right_value is None:
        raise AssertionError("Both clients must have decrypted room keys before comparing them")
    assert left_value == right_value, (
        f"Opened room keys differed unexpectedly: {left_value!r} and {right_value!r}."
    )


@then('the opened room key for "{left_name}" and "{right_name}" should be different')
def step_assert_decrypted_room_keys_not_equal(context, left_name: str, right_name: str) -> None:
    left_value = context.world.last_decrypted_room_key.get(left_name)
    right_value = context.world.last_decrypted_room_key.get(right_name)
    if left_value is None or right_value is None:
        raise AssertionError("Both clients must have decrypted room keys before comparing them")
    assert left_value != right_value, (
        f"Opened room keys matched unexpectedly: {left_value!r}."
    )


from __future__ import annotations

import json
import uuid

from behave import then, when

from phantomchat_blackbox.crypto import (
    CryptoProtocolError,
    open_encrypted_chat_message,
    open_encrypted_file_content,
    prepare_encrypted_chat_message,
    prepare_encrypted_file_content,
)
from phantomchat_blackbox.protocol import SocketCommand


def _room_key_for_client(context, name: str) -> str:
    room_key = context.world.last_decrypted_room_key.get(name)
    if room_key is None:
        room_key = context.world.decrypt_room_key_for_client(name)
    return room_key


@when('"{name}" sends the encrypted message "{plaintext}" using the room key')
def step_send_encrypted_message(context, name: str, plaintext: str) -> None:
    room_key = _room_key_for_client(context, name)
    prepared = prepare_encrypted_chat_message(plaintext, room_key)
    request_uuid = uuid.uuid4().hex
    payload = {
        "request_uuid": request_uuid,
        "command": int(SocketCommand.SEND_MESSAGE),
        "message": prepared.serialized_message,
    }
    client = context.world.create_client(name)
    context.world.last_socket_request[name] = payload
    client.send_json(payload)
    response = client.wait_for(
        predicate=lambda item: item.get("request_uuid") == request_uuid,
        description=f"encrypted-message response for client '{name}'",
    )
    context.world.last_socket_response[name] = response


@when('"{name}" sends a tampered encrypted message for "{plaintext}" using the room key')
def step_send_tampered_encrypted_message(context, name: str, plaintext: str) -> None:
    room_key = _room_key_for_client(context, name)
    prepared = prepare_encrypted_chat_message(plaintext, room_key)
    payload_data = json.loads(prepared.serialized_message)
    tampered_ciphertext = payload_data["ciphertext"]
    replacement = "0" if tampered_ciphertext[-1] != "0" else "1"
    payload_data["ciphertext"] = tampered_ciphertext[:-1] + replacement
    tampered_message = json.dumps(payload_data, separators=(",", ":"), sort_keys=True)
    request_uuid = uuid.uuid4().hex
    payload = {
        "request_uuid": request_uuid,
        "command": int(SocketCommand.SEND_MESSAGE),
        "message": tampered_message,
    }
    client = context.world.create_client(name)
    context.world.last_socket_request[name] = payload
    client.send_json(payload)
    response = client.wait_for(
        predicate=lambda item: item.get("request_uuid") == request_uuid,
        description=f"tampered-encrypted-message response for client '{name}'",
    )
    context.world.last_socket_response[name] = response


@then('the last sent chat payload for "{name}" should not contain "{plaintext}"')
def step_assert_last_sent_payload_not_plaintext(context, name: str, plaintext: str) -> None:
    payload = context.world.last_socket_request.get(name)
    if payload is None:
        raise AssertionError(f"No stored socket request found for client '{name}'")
    message = payload.get("message")
    if not isinstance(message, str):
        raise AssertionError(f"Stored socket request message was not a string: {message!r}")
    if plaintext in message:
        raise AssertionError(f"Encrypted chat payload unexpectedly contained plaintext {plaintext!r}: {message!r}")


@then('the reply field "{field_name}" for "{name}" should not mention "{unexpected_text}"')
def step_assert_response_field_does_not_contain_text(context, field_name: str, name: str, unexpected_text: str) -> None:
    payload = context.world.last_socket_response.get(name)
    if payload is None:
        raise AssertionError(f"No stored response found for client '{name}'")
    actual_value = payload
    for segment in field_name.split("."):
        if not isinstance(actual_value, dict) or segment not in actual_value:
            raise AssertionError(f"Expected path '{field_name}' to exist in payload: {payload}")
        actual_value = actual_value[segment]
    if not isinstance(actual_value, str):
        raise AssertionError(f"Field '{field_name}' is not a string: {actual_value!r}")
    if unexpected_text in actual_value:
        raise AssertionError(
            f"Field '{field_name}' unexpectedly contained text {unexpected_text!r}: {actual_value!r}"
        )


@then('"{name}" should receive an encrypted chat message from "{sender_name}" that opens to "{plaintext}"')
def step_assert_encrypted_chat_received(context, name: str, sender_name: str, plaintext: str) -> None:
    client = context.world.create_client(name)
    event = client.wait_for_event("NewMessageReceived", timeout_seconds=context.world.config.event_timeout_seconds)
    context.world.last_socket_event[name] = event
    expected_sender = context.world.client_user_uuid(sender_name)
    if event.get("sender_uuid") != expected_sender:
        raise AssertionError(
            f"Expected sender_uuid {expected_sender!r}, got {event.get('sender_uuid')!r}."
        )
    message = event.get("message")
    if not isinstance(message, str):
        raise AssertionError(f"Encrypted message payload was not a string: {message!r}")
    opened = open_encrypted_chat_message(message, _room_key_for_client(context, name))
    if opened != plaintext:
        raise AssertionError(f"Expected opened plaintext {plaintext!r}, got {opened!r}")


@then('the received encrypted chat payload for "{name}" should not contain "{plaintext}"')
def step_assert_received_payload_not_plaintext(context, name: str, plaintext: str) -> None:
    event = context.world.last_socket_event.get(name)
    if event is None:
        raise AssertionError(f"No stored socket event found for client '{name}'")
    message = event.get("message")
    if not isinstance(message, str):
        raise AssertionError(f"Encrypted message payload was not a string: {message!r}")
    if plaintext in message:
        raise AssertionError(f"Received encrypted payload unexpectedly contained plaintext {plaintext!r}: {message!r}")


@then('"{name}" should receive an encrypted chat message from "{sender_name}" that cannot be opened')
def step_assert_encrypted_chat_cannot_open(context, name: str, sender_name: str) -> None:
    client = context.world.create_client(name)
    event = client.wait_for_event("NewMessageReceived", timeout_seconds=context.world.config.event_timeout_seconds)
    context.world.last_socket_event[name] = event
    expected_sender = context.world.client_user_uuid(sender_name)
    if event.get("sender_uuid") != expected_sender:
        raise AssertionError(
            f"Expected sender_uuid {expected_sender!r}, got {event.get('sender_uuid')!r}."
        )
    message = event.get("message")
    if not isinstance(message, str):
        raise AssertionError(f"Encrypted message payload was not a string: {message!r}")
    try:
        open_encrypted_chat_message(message, _room_key_for_client(context, name))
    except CryptoProtocolError:
        return
    raise AssertionError("Encrypted chat payload unexpectedly opened successfully")


@when('"{user_name}" uploads encrypted file "{filename}" to room "{room_alias}" with content')
def step_upload_encrypted_file(context, user_name: str, filename: str, room_alias: str) -> None:
    plaintext = (context.text or "").encode("utf-8")
    prepared = prepare_encrypted_file_content(plaintext, _room_key_for_client(context, user_name))
    context.world.last_uploaded_content = prepared.ciphertext
    context.world.last_http_request_headers = {
        "x-room-name": context.world.resolve_room(room_alias),
        "x-user-uuid": context.world.client_user_uuid(user_name),
    }
    response = context.world.http.upload_document(
        filename=filename,
        room_name=context.world.resolve_room(room_alias),
        user_uuid=context.world.client_user_uuid(user_name),
        content=prepared.ciphertext,
    )
    context.world.last_http_response = response


@then('the uploaded file bytes should not equal')
def step_assert_uploaded_bytes_not_equal(context) -> None:
    unexpected = (context.text or "").encode("utf-8")
    actual = context.world.last_uploaded_content
    if actual is None:
        raise AssertionError("No uploaded file bytes have been stored")
    if actual == unexpected:
        raise AssertionError("Uploaded bytes unexpectedly matched the plaintext input")


@then('the downloaded file bytes should not equal')
def step_assert_downloaded_bytes_not_equal(context) -> None:
    unexpected = (context.text or "").encode("utf-8")
    actual = context.world.last_downloaded_content
    if actual is None:
        raise AssertionError("No downloaded file bytes have been stored")
    if actual == unexpected:
        raise AssertionError("Downloaded bytes unexpectedly matched the plaintext input")


@then('the downloaded encrypted file should open to')
def step_assert_downloaded_file_opens_to(context) -> None:
    expected = (context.text or "").encode("utf-8")
    ciphertext = context.world.last_downloaded_content
    if ciphertext is None:
        raise AssertionError("No downloaded file bytes have been stored")
    if not context.world.last_decrypted_room_key:
        raise AssertionError("No opened room key is available for decrypting the downloaded file")
    room_key = next(iter(context.world.last_decrypted_room_key.values()))
    opened = open_encrypted_file_content(ciphertext, room_key)
    if opened != expected:
        raise AssertionError(f"Expected decrypted downloaded content {expected!r}, got {opened!r}")
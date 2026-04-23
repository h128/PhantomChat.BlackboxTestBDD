from __future__ import annotations

import uuid

from behave import when

from phantomchat_blackbox.protocol import SocketCommand


@when('"{name}" attempts to join with these raw fields:')
def step_attempt_join_with_raw_fields(context, name: str) -> None:
    client = context.world.create_client(name)
    request_uuid = uuid.uuid4().hex
    payload = {
        "request_uuid": request_uuid,
        "command": int(SocketCommand.JOIN_OR_CREATE_ROOM),
        **{row["field"]: row["value"] for row in context.table},
    }
    client.send_json(payload)
    # Some validation errors (e.g. missing fields) cause the server to reply with
    # "request_uuid": "unknown" because parsing fails before the uuid is extracted.
    response = client.wait_for(
        predicate=lambda item: (
            item.get("request_uuid") in {request_uuid, "unknown"}
            and item.get("event_name") is None
        ),
        description=f"join-validation response for client '{name}'",
    )
    context.world.last_socket_response[name] = response

from __future__ import annotations

from behave import then, when


@when('user "{user_name}" uploads file "{filename}" to room "{room_alias}" with content')
@when('"{user_name}" uploads file "{filename}" to room "{room_alias}" with content')
@when('"{user_name}" tries to upload file "{filename}" to room "{room_alias}" with content')
def step_upload_file(context, user_name: str, filename: str, room_alias: str) -> None:
    content = (context.text or "").encode("utf-8")
    response = context.world.http.upload_document(
        filename=filename,
        room_name=context.world.resolve_room(room_alias),
        user_uuid=context.world.client_user_uuid(user_name),
        content=content,
    )
    context.world.last_http_response = response


@when('the file "{filename}" is downloaded from room "{room_alias}"')
@when('"{filename}" is downloaded from room "{room_alias}"')
def step_download_file(context, filename: str, room_alias: str) -> None:
    response = context.world.http.download_document(
        room_name=context.world.resolve_room(room_alias),
        filename=filename,
    )
    context.world.last_http_response = response
    context.world.last_downloaded_content = response.content


@then('the last HTTP response should have status {status:d}')
@then('the request should finish with status {status:d}')
def step_assert_http_status(context, status: int) -> None:
    response = context.world.last_http_response
    if response is None:
        raise AssertionError("No HTTP response has been stored")
    assert response.status_code == status, (
        f"Expected HTTP status {status}, got {response.status_code}. Body: {response.text}"
    )


@then('the last HTTP response body should contain "{text}"')
@then('the last web reply should mention "{text}"')
def step_assert_http_body(context, text: str) -> None:
    response = context.world.last_http_response
    if response is None:
        raise AssertionError("No HTTP response has been stored")
    assert text in response.text, f"Expected to find '{text}' in HTTP response body: {response.text}"


@then('the downloaded content should equal')
@then('the downloaded file should equal')
def step_assert_downloaded_content(context) -> None:
    expected = (context.text or "").encode("utf-8")
    actual = context.world.last_downloaded_content
    if actual is None:
        raise AssertionError("No downloaded content has been stored")
    assert actual == expected, f"Downloaded content mismatch. Expected {expected!r}, got {actual!r}"


@then('"{name}" should be told that "{user_name}" uploaded "{filename}"')
def step_assert_file_uploaded_event(context, name: str, user_name: str, filename: str) -> None:
    client = context.world.create_client(name)
    event = client.wait_for_event("FileUploaded", timeout_seconds=context.world.config.event_timeout_seconds)
    context.world.last_socket_event[name] = event
    expected_user_uuid = context.world.client_user_uuid(user_name)
    assert event.get("file_name") == filename, (
        f"Expected file_name {filename!r}, got {event.get('file_name')!r}."
    )
    assert event.get("user_uuid") == expected_user_uuid, (
        f"Expected user_uuid {expected_user_uuid!r}, got {event.get('user_uuid')!r}."
    )
    assert event.get("poster") is False, (
        f"Expected poster to be False, got {event.get('poster')!r}."
    )

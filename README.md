# PhantomChat Black-Box BDD Tests

This repository contains a Python + Behave black-box integration test suite for PhantomChat. The suite interacts with the system only through public interfaces:

- WebSocket at `/room`
- REST upload endpoint at `/upload-document/:filename`
- REST download endpoint at `/download-document/:room/:filename`

The scenarios were derived from the current backend and frontend contracts in the sibling repositories, but the tests do not import or call internal application code.

## What is covered

The initial suite focuses on stable, externally visible behavior:

- room creation and join flow over WebSocket
- chat message delivery and server-side validation
- explicit leave notifications
- authenticated file upload and download over REST
- file upload broadcast events over WebSocket
- call signaling relay over WebSocket for future WebRTC scenarios
- crypto-handshake contract checks for client public keys and server-returned room key material

## Project structure

```text
features/
  environment.py
  chat_room.feature
  file_transfer.feature
  call_signaling.feature
  steps/
    connection_steps.py
    http_steps.py
src/phantomchat_blackbox/
  config.py
  http_client.py
  protocol.py
  runtime.py
  socket_client.py
  webrtc.py
  world.py
```

## Prerequisites

- Python 3.11+
- a reachable PhantomChat backend
- optional: a command that starts the backend as an external process

## Local execution

1. Create and activate a virtual environment.
2. Install the project in editable mode.
3. Configure the system under test through environment variables.
4. Run Behave.

Example PowerShell session:

```powershell
Set-Location "C:\Programming\My source\PhantomChat.BlackboxTestBDD"
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e .

$Env:PHANTOMCHAT_HTTP_BASE_URL = "http://127.0.0.1:8080"
$Env:PHANTOMCHAT_WS_URL = "ws://127.0.0.1:8080/room"
python -m behave
```

If you want the suite to start the backend process for you, set:

- `PHANTOMCHAT_SERVER_COMMAND`
- `PHANTOMCHAT_SERVER_WORKDIR`

The suite will treat that process as an external dependency and wait until the configured port is reachable.

## Configuration

Supported environment variables:

- `PHANTOMCHAT_HTTP_BASE_URL`
- `PHANTOMCHAT_WS_URL`
- `PHANTOMCHAT_VERIFY_TLS`
- `PHANTOMCHAT_REQUEST_TIMEOUT_SECONDS`
- `PHANTOMCHAT_EVENT_TIMEOUT_SECONDS`
- `PHANTOMCHAT_STARTUP_TIMEOUT_SECONDS`
- `PHANTOMCHAT_SERVER_COMMAND`
- `PHANTOMCHAT_SERVER_WORKDIR`

Defaults target a local backend at `http://127.0.0.1:8080` and `ws://127.0.0.1:8080/room`.

## CI/CD

The repository includes a GitHub Actions workflow at [.github/workflows/bdd.yml](.github/workflows/bdd.yml).

It is structured in two layers:

- `validate-suite`: always verifies that the project installs and the Behave suite parses via `--dry-run`
- `run-blackbox-tests`: runs the real integration suite when repository variables `PHANTOMCHAT_HTTP_BASE_URL` and `PHANTOMCHAT_WS_URL` are configured

This keeps the test project continuously valid even when no dedicated test environment is available, while still supporting real black-box execution in CI once a target environment exists.

For other CI systems, the command is the same:

```bash
python -m pip install -e .
python -m behave --junit --junit-directory test-results
```

## Notes from repository analysis

The current contract inferred from the application repositories is:

- backend default listen port: `8080`
- WebSocket endpoint: `/room`
- socket commands:
  - `1`: join or create room
  - `2`: send chat message
  - `3`: leave room
  - `4`: relay call signaling
- upload requires headers:
  - `x-room-name`
  - `x-user-uuid`
- join responses currently expose a `room_key` field that the frontend treats as opaque key material for file encryption
- join requests currently include a `public_key` field, but the present public protocol does not expose enough information to prove whether the server encrypted any returned secret specifically to that public key

The suite intentionally validates those behaviors from the wire, not through direct code reuse.

## Current crypto coverage

The suite now validates the highest-value crypto-related behavior that is observable black-box today:

- a client can submit well-formed public-key shaped material during room join
- malformed public-key material is rejected at the protocol boundary
- room join returns non-empty opaque key material in `room_key`
- the returned `room_key` is stable for multiple members of the same room
- different rooms receive different `room_key` values
- the key material matches the current libsodium-style hex contract observed in the implementation direction

What the suite does not currently prove:

- that the server encrypts any payload with the caller's public key
- that `room_key` is an encrypted room secret rather than a raw room public key or shared secret string
- which exact libsodium primitive is used on the server side

Those properties are not fully observable through the current public API because the join response does not expose a decryptable envelope plus a separate server public key in a way a black-box client can verify end-to-end.

## Future extension for RTCPeerConnection scenarios

The current call scenarios stop at signaling relay, which is the right black-box boundary for the server today. For end-to-end media negotiation later, the project is prepared in two ways:

- the protocol and signaling assertions are isolated from feature steps, so WebRTC-specific flows can be layered in without rewriting the suite
- an optional `webrtc` extra is declared for `aiortc`, allowing future Python-based peer connection harnesses without changing the base test dependencies

The next step for richer call coverage would be to add a dedicated peer connection adapter that:

- creates offers and answers with `aiortc`
- feeds ICE candidates through the existing signaling steps
- asserts connection state transitions and optional media/data-channel exchange

## Future extension for full crypto verification

If the public protocol evolves to return both:

- a server room public key, and
- an encrypted room secret or envelope addressed to the caller's public key,

then this suite should add end-to-end cryptographic verification with a Python libsodium-compatible client harness. At that point a black-box scenario can generate a real key pair, join a room, decrypt the returned envelope, and verify the decrypted secret is consistent across participants without inspecting server internals.

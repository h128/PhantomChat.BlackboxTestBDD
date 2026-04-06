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
- run commands from the repository root
- for live execution, a PhantomChat backend that exposes both:
  - an HTTP base URL for file upload and download
  - a WebSocket endpoint compatible with the room protocol used by these scenarios
- optional: a shell command that starts the backend as an external process

## Environment setup

Create a virtual environment and install the suite in editable mode.

PowerShell:

```powershell
Set-Location "C:\Programming\My source\PhantomChat.BlackboxTestBDD"
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e .
```

Bash:

```bash
cd /path/to/PhantomChat.BlackboxTestBDD
python -m venv .venv
source .venv/Scripts/activate
python -m pip install --upgrade pip
python -m pip install -e .
```

## Environment variables

The suite reads configuration only from environment variables. `.env.example` is a reference file; it is not loaded automatically.

Supported variables:

- `PHANTOMCHAT_HTTP_BASE_URL`
- `PHANTOMCHAT_WS_URL`
- `PHANTOMCHAT_VERIFY_TLS`
- `PHANTOMCHAT_REQUEST_TIMEOUT_SECONDS`
- `PHANTOMCHAT_EVENT_TIMEOUT_SECONDS`
- `PHANTOMCHAT_STARTUP_TIMEOUT_SECONDS`
- `PHANTOMCHAT_SERVER_COMMAND`
- `PHANTOMCHAT_SERVER_WORKDIR`

Default values target a local backend at `http://127.0.0.1:8080` and `ws://127.0.0.1:8080/room`.

PowerShell example:

```powershell
$Env:PHANTOMCHAT_HTTP_BASE_URL = "http://127.0.0.1:8080"
$Env:PHANTOMCHAT_WS_URL = "ws://127.0.0.1:8080/room"
$Env:PHANTOMCHAT_VERIFY_TLS = "false"
```

Bash example:

```bash
export PHANTOMCHAT_HTTP_BASE_URL="http://127.0.0.1:8080"
export PHANTOMCHAT_WS_URL="ws://127.0.0.1:8080/room"
export PHANTOMCHAT_VERIFY_TLS="false"
```

## Local execution

Use these commands from the repository root after activating the virtual environment.

Validate feature parsing and step bindings without requiring a backend:

```bash
python -m behave --dry-run
```

Run one feature file:

```bash
python -m behave features/chat_room.feature -f progress
```

Run a single scenario by line number:

```bash
python -m behave features/chat_room.feature:4
```

Run the full suite:

```bash
python -m behave -f progress
```

Run a feature while overriding the target backend through environment variables:

```powershell
$Env:PHANTOMCHAT_HTTP_BASE_URL = "https://your-backend.example"
$Env:PHANTOMCHAT_WS_URL = "wss://your-backend.example/room"
python -m behave features/file_transfer.feature -f progress
```

Notes:

- `--dry-run` is the safest first check and does not require a running backend.
- live runs require both the HTTP and WebSocket endpoints to match the PhantomChat contract.
- if you only want machine-readable test output, use `--junit --junit-directory test-results`.

## Optional backend startup from the test suite

If you prefer the suite to boot the backend process for you, set `PHANTOMCHAT_SERVER_COMMAND`. Set `PHANTOMCHAT_SERVER_WORKDIR` as well when the backend must start from a specific directory.

```powershell
$Env:PHANTOMCHAT_HTTP_BASE_URL = "http://127.0.0.1:8080"
$Env:PHANTOMCHAT_WS_URL = "ws://127.0.0.1:8080/room"
$Env:PHANTOMCHAT_SERVER_COMMAND = ".\\path\\to\\start-backend.cmd"
$Env:PHANTOMCHAT_SERVER_WORKDIR = "C:\path\to\backend"
python -m behave -f progress
```

The test harness waits until the configured WebSocket host and port become reachable before scenarios start.

## CI execution

The repository includes a GitHub Actions workflow at [.github/workflows/bdd.yml](.github/workflows/bdd.yml).

It runs in two stages:

- `validate-suite` always installs the project and runs `python -m behave --dry-run`
- `run-blackbox-tests` runs the live suite only when `PHANTOMCHAT_HTTP_BASE_URL` and `PHANTOMCHAT_WS_URL` are configured in repository variables

That split keeps CI useful even when no shared integration environment is available.

For other CI systems, use the same pattern:

```bash
python -m pip install --upgrade pip
python -m pip install -e .
python -m behave --dry-run
python -m behave --junit --junit-directory test-results
```

## Troubleshooting

- If `python -m behave --dry-run` passes but live runs fail immediately, verify that `PHANTOMCHAT_HTTP_BASE_URL` and `PHANTOMCHAT_WS_URL` point to the same PhantomChat deployment.
- If the WebSocket step fails with a 404 during the handshake, the target server is reachable but `PHANTOMCHAT_WS_URL` is not the correct WebSocket endpoint for that environment.
- If you are testing against HTTPS or WSS with a valid certificate, set `PHANTOMCHAT_VERIFY_TLS=true`.

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

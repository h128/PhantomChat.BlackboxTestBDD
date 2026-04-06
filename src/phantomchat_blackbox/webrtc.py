from __future__ import annotations

from typing import Any, Protocol


class PeerConnectionAdapter(Protocol):
    def create_offer_payload(self) -> dict[str, Any]:
        """Return a payload compatible with PhantomChat's signaling envelope."""

    def apply_answer_payload(self, payload: dict[str, Any]) -> None:
        """Apply a remote answer received through the signaling channel."""

    def add_ice_candidate_payload(self, payload: dict[str, Any]) -> None:
        """Apply a remote ICE candidate received through the signaling channel."""


def aiortc_available() -> bool:
    try:
        import aiortc  # noqa: F401
    except ImportError:
        return False
    return True


def require_aiortc() -> None:
    if aiortc_available():
        return
    raise RuntimeError(
        "aiortc is not installed. Install the optional WebRTC support with 'python -m pip install -e .[webrtc]'."
    )

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from typing import Any

from nacl.bindings import crypto_box_NONCEBYTES
from nacl.encoding import HexEncoder
from nacl.exceptions import CryptoError
from nacl.public import Box, PrivateKey, PublicKey


HEX_PATTERN = re.compile(r"^[0-9a-f]+$")


class CryptoProtocolError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class ClientKeyMaterial:
    private_key: PrivateKey
    public_key: PublicKey

    @classmethod
    def from_seed_text(cls, seed_text: str) -> "ClientKeyMaterial":
        seed = hashlib.sha256(seed_text.encode("utf-8")).digest()
        private_key = PrivateKey(seed)
        return cls(private_key=private_key, public_key=private_key.public_key)

    @property
    def public_key_hex(self) -> str:
        return self.public_key.encode(encoder=HexEncoder).decode("ascii")

    @property
    def private_key_hex(self) -> str:
        return self.private_key.encode(encoder=HexEncoder).decode("ascii")


@dataclass(frozen=True, slots=True)
class JoinRoomKeyEnvelope:
    ciphertext_hex: str
    server_public_key_hex: str
    nonce: bytes = field(default_factory=lambda: bytes(crypto_box_NONCEBYTES))


@dataclass(frozen=True, slots=True)
class FutureAesMessageContract:
    message_field: str = "message"
    required_fields: tuple[str, ...] = ("algorithm", "nonce", "ciphertext")


def parse_join_room_key_envelope(payload: dict[str, Any]) -> JoinRoomKeyEnvelope:
    ciphertext_hex = _require_hex_field(payload, "room_key")
    server_public_key_hex = _require_hex_field(payload, "server_pub_key")
    return JoinRoomKeyEnvelope(
        ciphertext_hex=ciphertext_hex,
        server_public_key_hex=server_public_key_hex,
    )


def decrypt_join_room_key(payload: dict[str, Any], key_material: ClientKeyMaterial) -> str:
    envelope = parse_join_room_key_envelope(payload)
    box = Box(
        key_material.private_key,
        PublicKey(envelope.server_public_key_hex, encoder=HexEncoder),
    )
    try:
        plaintext = box.decrypt(bytes.fromhex(envelope.ciphertext_hex), nonce=envelope.nonce)
    except CryptoError as exc:
        raise CryptoProtocolError("Unable to decrypt room_key with the provided client key material") from exc

    try:
        decoded = plaintext.decode("ascii")
    except UnicodeDecodeError as exc:
        raise CryptoProtocolError("Decrypted room_key was not ASCII text") from exc

    if not HEX_PATTERN.fullmatch(decoded):
        raise CryptoProtocolError(f"Decrypted room_key was not hex text: {decoded!r}")
    return decoded


def require_future_aes_message_contract(payload: dict[str, Any]) -> FutureAesMessageContract:
    message_value = payload.get("message")
    if not isinstance(message_value, dict):
        raise CryptoProtocolError(
            "Chat encryption cannot be validated black-box yet because the public message field is still plain text "
            "and does not expose an AES envelope."
        )

    missing_fields = [field_name for field_name in ("algorithm", "nonce", "ciphertext") if field_name not in message_value]
    if missing_fields:
        missing_text = ", ".join(missing_fields)
        raise CryptoProtocolError(f"Chat encryption envelope is missing required field(s): {missing_text}")
    return FutureAesMessageContract()


def _require_hex_field(payload: dict[str, Any], field_name: str) -> str:
    value = payload.get(field_name)
    if not isinstance(value, str) or not value:
        raise CryptoProtocolError(f"Expected non-empty string field '{field_name}' in payload: {payload}")
    if not HEX_PATTERN.fullmatch(value):
        raise CryptoProtocolError(f"Field '{field_name}' was not lowercase hex: {value!r}")
    if len(value) % 2 != 0:
        raise CryptoProtocolError(f"Field '{field_name}' must contain an even number of hex characters: {value!r}")
    return value
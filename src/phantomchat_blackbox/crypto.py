from __future__ import annotations

import json
import hashlib
import re
from dataclasses import dataclass, field
from typing import Any

from nacl import hash as nacl_hash
from nacl.bindings import crypto_box_NONCEBYTES
from nacl.encoding import HexEncoder, RawEncoder
from nacl.exceptions import CryptoError
from nacl.secret import SecretBox
from nacl.utils import random as nacl_random
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


@dataclass(frozen=True, slots=True)
class EncryptedChatEnvelope:
    algorithm: str
    nonce: str
    ciphertext: str
    key_derivation: str = "blake2b-room-key-v1"
    payload_encoding: str = "hex"
    version: int = 1


@dataclass(frozen=True, slots=True)
class PreparedEncryptedChatMessage:
    plaintext: str
    serialized_message: str
    envelope: EncryptedChatEnvelope


@dataclass(frozen=True, slots=True)
class PreparedEncryptedFile:
    plaintext: bytes
    ciphertext: bytes
    nonce: bytes
    key_derivation: str = "blake2b-room-key-v1"
    transport_encoding: str = "nonce-prefixed-binary"


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


def derive_secretbox_key(room_key: str) -> bytes:
    if not HEX_PATTERN.fullmatch(room_key) or len(room_key) != 64:
        raise CryptoProtocolError(f"room_key must be a 64-character hex string, got {room_key!r}")
    return nacl_hash.blake2b(
        room_key.encode("utf-8"),
        digest_size=SecretBox.KEY_SIZE,
        encoder=RawEncoder,
    )


def prepare_encrypted_chat_message(plaintext: str, room_key: str) -> PreparedEncryptedChatMessage:
    if not plaintext:
        raise CryptoProtocolError("Encrypted chat plaintext cannot be empty")

    box = SecretBox(derive_secretbox_key(room_key))
    nonce = nacl_random(SecretBox.NONCE_SIZE)
    ciphertext = box.encrypt(plaintext.encode("utf-8"), nonce).ciphertext
    envelope = EncryptedChatEnvelope(
        algorithm="secretbox",
        nonce=nonce.hex(),
        ciphertext=ciphertext.hex(),
    )
    serialized_message = json.dumps(
        {
            "algorithm": envelope.algorithm,
            "ciphertext": envelope.ciphertext,
            "key_derivation": envelope.key_derivation,
            "nonce": envelope.nonce,
            "payload_encoding": envelope.payload_encoding,
            "version": envelope.version,
        },
        separators=(",", ":"),
        sort_keys=True,
    )
    return PreparedEncryptedChatMessage(
        plaintext=plaintext,
        serialized_message=serialized_message,
        envelope=envelope,
    )


def open_encrypted_chat_message(serialized_message: str, room_key: str) -> str:
    try:
        payload = json.loads(serialized_message)
    except json.JSONDecodeError as exc:
        raise CryptoProtocolError("Encrypted chat message was not valid JSON") from exc

    required_fields = {
        "algorithm",
        "ciphertext",
        "key_derivation",
        "nonce",
        "payload_encoding",
        "version",
    }
    missing = sorted(required_fields - payload.keys())
    if missing:
        raise CryptoProtocolError(f"Encrypted chat message is missing field(s): {', '.join(missing)}")

    if payload["algorithm"] != "secretbox":
        raise CryptoProtocolError("Encrypted chat message algorithm must be 'secretbox'")
    if payload["key_derivation"] != "blake2b-room-key-v1":
        raise CryptoProtocolError("Encrypted chat message key_derivation must be 'blake2b-room-key-v1'")
    if payload["payload_encoding"] != "hex":
        raise CryptoProtocolError("Encrypted chat message payload_encoding must be 'hex'")
    if payload["version"] != 1:
        raise CryptoProtocolError("Encrypted chat message version must be 1")

    nonce_hex = _require_hex_field(payload, "nonce")
    ciphertext_hex = _require_hex_field(payload, "ciphertext")
    if len(nonce_hex) != SecretBox.NONCE_SIZE * 2:
        raise CryptoProtocolError("Encrypted chat message nonce length was invalid")

    box = SecretBox(derive_secretbox_key(room_key))
    try:
        plaintext = box.decrypt(bytes.fromhex(ciphertext_hex), bytes.fromhex(nonce_hex))
    except CryptoError as exc:
        raise CryptoProtocolError("Encrypted chat message could not be opened with the room key") from exc
    return plaintext.decode("utf-8")


def prepare_encrypted_file_content(plaintext: bytes, room_key: str) -> PreparedEncryptedFile:
    box = SecretBox(derive_secretbox_key(room_key))
    nonce = nacl_random(SecretBox.NONCE_SIZE)
    ciphertext = box.encrypt(plaintext, nonce)
    return PreparedEncryptedFile(
        plaintext=plaintext,
        ciphertext=bytes(ciphertext),
        nonce=nonce,
    )


def open_encrypted_file_content(ciphertext: bytes, room_key: str) -> bytes:
    if len(ciphertext) <= SecretBox.NONCE_SIZE:
        raise CryptoProtocolError("Encrypted file content was too short to contain nonce-prefixed ciphertext")

    nonce = ciphertext[: SecretBox.NONCE_SIZE]
    actual_ciphertext = ciphertext[SecretBox.NONCE_SIZE :]
    box = SecretBox(derive_secretbox_key(room_key))
    try:
        return box.decrypt(actual_ciphertext, nonce)
    except CryptoError as exc:
        raise CryptoProtocolError("Encrypted file content could not be opened with the room key") from exc
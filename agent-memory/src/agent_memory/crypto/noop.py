"""NoopEncryptionProvider — passthrough encryption for development and tests.

WARNING: Does NOT encrypt data. For production use, configure AESGCMEncryptionProvider.
"""

from __future__ import annotations

import base64

from agent_memory.ports.encryption import EncryptionContext, EncryptionProvider


class NoopEncryptionProvider(EncryptionProvider):
    """No-op encryption provider.

    Encrypt and decrypt are passthrough operations.
    The ciphertext is the base64-encoded plaintext (no actual encryption).
    For development and testing only.
    """

    async def encrypt(
        self,
        plaintext: bytes,
        *,
        context: EncryptionContext,
    ) -> "EncryptedPayload":
        """Return plaintext as ciphertext with no actual encryption.

        Uses base64 encoding as a transparent wrapper so the round-trip
        behaves like an encryption provider at the API level.
        """
        from agent_memory.ports.encryption import EncryptedPayload

        return EncryptedPayload(
            ciphertext=base64.b64encode(plaintext),
            algorithm="noop",
            key_id="noop",
        )

    async def decrypt(
        self,
        payload: "EncryptedPayload",
        *,
        context: EncryptionContext,
    ) -> bytes:
        """Return the original plaintext by decoding base64."""
        return base64.b64decode(payload.ciphertext)
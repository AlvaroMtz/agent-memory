"""AESGCMEncryptionProvider — AES-256-GCM encryption for production.

Uses the `cryptography` library (hazmat primitives).
Key derivation from a config-provided key using HKDF-SHA256.
"""

from __future__ import annotations

import base64
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives import hashes

from agent_memory.ports.encryption import EncryptionContext, EncryptedPayload


class AESGCMEncryptionProvider:
    """AES-256-GCM encryption provider.

    Encrypts plaintext bytes with AES-256-GCM using a key derived from
    a config-provided key material. Each encryption generates a fresh
    12-byte nonce. The ciphertext includes the nonce and authentication tag.
    """

    KEY_LENGTH = 32  # AES-256
    NONCE_LENGTH = 12  # GCM standard

    def __init__(self, key_material: str | bytes) -> None:
        """Initialize with a config-provided key material.

        Args:
            key_material: A string or bytes used as input to HKDF key derivation.
                          In production, this should be a securely stored key
                          (e.g., from environment variable or secrets manager).
        """
        if isinstance(key_material, str):
            key_material = key_material.encode("utf-8")

        if not key_material:
            raise ValueError("key_material must be non-empty")

        # Derive a 256-bit key from the key material using HKDF-SHA256
        self._key: bytes = HKDF(
            algorithm=hashes.SHA256(),
            length=self.KEY_LENGTH,
            salt=None,
            info=b"agent-memory-aes-gcm-v1",
        ).derive(key_material)

        self._cipher = AESGCM(self._key)

    async def encrypt(
        self,
        plaintext: bytes,
        *,
        context: EncryptionContext,
    ) -> EncryptedPayload:
        """Encrypt plaintext bytes using AES-256-GCM.

        Generates a fresh 12-byte random nonce per encryption.
        The nonce is prepended to the AAD-then-ciphertext structure.

        Args:
            plaintext: Data to encrypt.
            context: Encryption context (tenant_id, purpose, key_id).

        Returns:
            EncryptedPayload with ciphertext, nonce, and algorithm metadata.
        """
        nonce = os.urandom(self.NONCE_LENGTH)
        additional_data = context.tenant_id.encode("utf-8") if context.tenant_id else None

        ciphertext = self._cipher.encrypt(nonce, plaintext, additional_data)

        return EncryptedPayload(
            ciphertext=ciphertext,
            nonce=nonce,
            algorithm="aes-256-gcm",
            key_id=context.key_id,
        )

    async def decrypt(
        self,
        payload: EncryptedPayload,
        *,
        context: EncryptionContext,
    ) -> bytes:
        """Decrypt an AES-256-GCM encrypted payload.

        Args:
            payload: Encrypted payload with ciphertext, nonce.
            context: Encryption context (tenant_id for AAD verification).

        Returns:
            Decrypted plaintext bytes.

        Raises:
            cryptography.exceptions.InvalidTag: If the authentication tag
                is invalid (data integrity compromised or wrong key).
        """
        nonce = payload.nonce
        if nonce is None:
            nonce = payload.ciphertext[: self.NONCE_LENGTH]
            ciphertext = payload.ciphertext[self.NONCE_LENGTH :]
        else:
            ciphertext = payload.ciphertext

        additional_data = context.tenant_id.encode("utf-8") if context.tenant_id else None

        return self._cipher.decrypt(nonce, ciphertext, additional_data)
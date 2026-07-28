"""EncryptionProvider port — abstract interface for encrypting and decrypting data."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from pydantic import BaseModel

from agent_memory.context import MemoryContext


class EncryptionContext(BaseModel):
    """Context for encryption/decryption operations.

    Keys are selected externally — the context identifies which key to use.
    """

    tenant_id: str
    purpose: str | None = None
    key_id: str | None = None


class EncryptedPayload(BaseModel):
    """Encrypted data with metadata needed for decryption."""

    ciphertext: bytes
    nonce: bytes | None = None
    tag: bytes | None = None
    key_id: str | None = None
    algorithm: str = "unknown"


@runtime_checkable
class EncryptionProvider(Protocol):
    """Port for encrypting and decrypting memory content.

    Implementations:
    - NoopEncryptionProvider: passes through plaintext (dev/tests only)
    - AESGCMEncryptionProvider: production-grade encryption
    """

    async def encrypt(
        self,
        plaintext: bytes,
        *,
        context: EncryptionContext,
    ) -> EncryptedPayload:
        """Encrypt plaintext bytes.

        Args:
            plaintext: Data to encrypt (e.g., memory value, evidence).
            context: Encryption context for key selection.

        Returns:
            Encrypted payload with ciphertext and metadata.
        """
        ...

    async def decrypt(
        self,
        payload: EncryptedPayload,
        *,
        context: EncryptionContext,
    ) -> bytes:
        """Decrypt an encrypted payload.

        Args:
            payload: Encrypted data with metadata.
            context: Encryption context for key selection.

        Returns:
            Decrypted plaintext bytes.
        """
        ...


class EncryptionProviderFactory(Protocol):
    """Factory for creating EncryptionProvider instances."""

    def create(self, **kwargs) -> EncryptionProvider:
        """Create an EncryptionProvider instance."""
        ...
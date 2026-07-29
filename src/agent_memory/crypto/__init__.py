"""Built-in encryption providers and plugin factories."""

from __future__ import annotations

from agent_memory.crypto.aes_gcm import AESGCMEncryptionProvider
from agent_memory.crypto.noop import NoopEncryptionProvider


class NoopEncryptionFactory:
    """Factory for development/test no-op encryption."""

    def create(self) -> NoopEncryptionProvider:
        return NoopEncryptionProvider()


class AESGCMEncryptionFactory:
    """Factory for AES-GCM encryption."""

    def create(self, key_material: str | bytes) -> AESGCMEncryptionProvider:
        return AESGCMEncryptionProvider(key_material=key_material)


__all__ = [
    "AESGCMEncryptionFactory",
    "AESGCMEncryptionProvider",
    "NoopEncryptionFactory",
    "NoopEncryptionProvider",
]

"""Tests for encryption providers."""

from __future__ import annotations

import pytest

pytest.importorskip("cryptography")

from cryptography.exceptions import InvalidTag

from agent_memory.crypto.aes_gcm import AESGCMEncryptionProvider
from agent_memory.crypto.noop import NoopEncryptionProvider
from agent_memory.ports.encryption import EncryptedPayload, EncryptionContext


@pytest.mark.asyncio
async def test_noop_encryption_round_trip() -> None:
    provider = NoopEncryptionProvider()
    context = EncryptionContext(tenant_id="tenant-a", purpose="testing", key_id="noop")

    payload = await provider.encrypt(b"hello", context=context)
    plaintext = await provider.decrypt(payload, context=context)

    assert payload.algorithm == "noop"
    assert payload.key_id == "noop"
    assert plaintext == b"hello"


def test_aes_gcm_rejects_empty_key_material() -> None:
    with pytest.raises(ValueError, match="key_material must be non-empty"):
        AESGCMEncryptionProvider("")


@pytest.mark.asyncio
async def test_aes_gcm_round_trip() -> None:
    provider = AESGCMEncryptionProvider("test-key-material")
    context = EncryptionContext(tenant_id="tenant-a", purpose="testing", key_id="key-1")

    payload = await provider.encrypt(b"secret", context=context)
    plaintext = await provider.decrypt(payload, context=context)

    assert payload.algorithm == "aes-256-gcm"
    assert payload.key_id == "key-1"
    assert payload.ciphertext != b"secret"
    assert plaintext == b"secret"


@pytest.mark.asyncio
async def test_aes_gcm_binds_ciphertext_to_tenant_context() -> None:
    provider = AESGCMEncryptionProvider(b"test-key-material")
    tenant_a = EncryptionContext(tenant_id="tenant-a")
    tenant_b = EncryptionContext(tenant_id="tenant-b")

    payload = await provider.encrypt(b"secret", context=tenant_a)

    with pytest.raises(InvalidTag):
        await provider.decrypt(payload, context=tenant_b)


@pytest.mark.asyncio
async def test_aes_gcm_can_decrypt_payload_with_embedded_nonce() -> None:
    provider = AESGCMEncryptionProvider("test-key-material")
    context = EncryptionContext(tenant_id="tenant-a")
    payload = await provider.encrypt(b"secret", context=context)
    legacy_payload = EncryptedPayload(
        ciphertext=payload.nonce + payload.ciphertext,
        nonce=None,
        algorithm=payload.algorithm,
        key_id=payload.key_id,
    )

    plaintext = await provider.decrypt(legacy_payload, context=context)

    assert plaintext == b"secret"
